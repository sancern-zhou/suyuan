"""对话模式长期记忆的查看与编辑 API。

每个对话模式（assistant/query/knowledge/expert/...）在
DATA_REGISTRY/memory/{mode}/ 下持有独立记忆目录（模式内所有用户共享）：
    MEMORY.md          主长期记忆（后台整合 Agent 每 50 轮对话后自动改写）
    USER.md            用户档案
    memory_meta.json   人工编辑版本元信息（仅由本 API 维护，用于乐观锁）

注意：后台整合直接改写 MEMORY.md，不经过 meta 版本号；PUT 额外用
expected_mtime_ns 对比文件 mtime，防止人工编辑覆盖整合结果。
社交模式（social/enforcement_exam）按用户隔离存储，不属于本 API 范畴。
"""

import fcntl
import json
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.utils.path_config import get_memory_dir

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/agent/memory", tags=["agent-memory"])

# 社交模式记忆按用户隔离（social/memory/{user_id}/），不提供模式级编辑入口
SOCIAL_MEMORY_MODES = {"social", "enforcement_exam"}

MAX_MEMORY_CHARS = 100_000


class ModeMemoryResponse(BaseModel):
    mode: str
    memory: str
    meta: dict


class UpdateModeMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, description="记忆 Markdown 全文")
    expected_version: int = Field(..., ge=0, description="编辑时读取到的记忆版本")
    expected_mtime_ns: Optional[Union[int, str]] = Field(
        default=None,
        description=(
            "编辑时读取到的 MEMORY.md mtime_ns（检测后台整合改动）。"
            "纳秒时间戳超出 JS Number 安全整数范围，GET 以字符串返回；"
            "此处同样接受字符串或整数"
        ),
    )


class MemoryVersionConflictError(RuntimeError):
    """Raised when a memory update was based on a stale version or stale file."""


def _safe_mode(mode: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", str(mode)).strip("_")
    if not safe:
        raise HTTPException(status_code=400, detail="无效的模式标识")
    if safe in SOCIAL_MEMORY_MODES:
        raise HTTPException(status_code=400, detail="社交模式记忆按用户隔离，不支持模式级查看/编辑")
    return safe


class ModeMemoryStorage:
    """单个模式长期记忆的文件存储（含人工编辑版本元信息）"""

    def __init__(self, mode: str, base_dir: Path | None = None):
        self.mode = mode
        base = Path(base_dir) if base_dir else get_memory_dir()
        self.mode_dir = base / mode
        self.memory_file = self.mode_dir / "MEMORY.md"
        self.meta_file = self.mode_dir / "memory_meta.json"
        self.lock_file = self.mode_dir / ".memory.lock"

    @contextmanager
    def _lock(self):
        self.mode_dir.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _memory_mtime_ns_unlocked(self) -> int:
        try:
            return self.memory_file.stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    def read(self) -> ModeMemoryResponse:
        self._ensure_files()
        return ModeMemoryResponse(
            mode=self.mode,
            memory=self._read_memory_unlocked(),
            meta=self._read_meta_unlocked(),
        )

    def write(
        self,
        content: str,
        expected_version: int,
        expected_mtime_ns: Optional[Union[int, str]],
    ) -> ModeMemoryResponse:
        content = content.strip()
        if not content:
            raise HTTPException(status_code=422, detail="记忆内容不能为空")
        if len(content) > MAX_MEMORY_CHARS:
            raise HTTPException(status_code=422, detail=f"记忆内容过长（上限 {MAX_MEMORY_CHARS} 字符）")
        try:
            normalized_mtime_ns = (
                int(str(expected_mtime_ns)) if expected_mtime_ns is not None else None
            )
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail="无效的 expected_mtime_ns") from e
        with self._lock():
            meta = self._read_meta_unlocked()
            current_version = int(meta.get("version", 0))
            if current_version != expected_version:
                raise MemoryVersionConflictError(
                    f"记忆版本已从 {expected_version} 变为 {current_version}"
                )
            current_mtime = self._memory_mtime_ns_unlocked()
            if normalized_mtime_ns is not None and current_mtime != normalized_mtime_ns:
                raise MemoryVersionConflictError(
                    "记忆文件已被后台整合等其他操作更新，请重新加载后再编辑"
                )
            tmp = self.memory_file.with_suffix(".md.tmp")
            tmp.write_text(content + "\n", encoding="utf-8")
            tmp.replace(self.memory_file)
            self._write_meta_unlocked(
                {
                    **meta,
                    "version": current_version + 1,
                    "updated_at": datetime.now().isoformat(),
                    "last_editor": "manual",
                }
            )
        return self.read()

    def _ensure_files(self) -> None:
        """与 MemoryStore._init_files 保持一致的初始模板（仅缺失时创建）"""
        self.mode_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self.memory_file.write_text(
                "# 长期记忆 (MEMORY.md)\n\n此文件存储用户的偏好、领域知识和重要结论。\n\n"
                "## 用户偏好\n\n## 领域知识\n\n## 历史结论\n",
                encoding="utf-8",
            )

    def _read_memory_unlocked(self) -> str:
        try:
            return self.memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _read_meta_unlocked(self) -> dict:
        meta: dict = {}
        try:
            meta = json.loads(self.meta_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("version", 0)
        # 纳秒时间戳超出 JS Number.MAX_SAFE_INTEGER，JSON 数字经前端解析会丢失
        # 精度导致乐观锁永远冲突；以字符串下发/回传保证无损。
        meta["file_mtime_ns"] = str(self._memory_mtime_ns_unlocked())
        return meta

    def _write_meta_unlocked(self, meta: dict) -> None:
        tmp = self.meta_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self.meta_file)


def _get_storage(mode: str) -> ModeMemoryStorage:
    return ModeMemoryStorage(_safe_mode(mode))


@router.get("/{mode}", response_model=ModeMemoryResponse)
async def get_mode_memory(
    mode: str,
    user: CurrentUser = Depends(require_current_user),
):
    """查看指定对话模式的长期记忆（MEMORY.md 全文与版本元信息）"""
    try:
        return _get_storage(mode).read()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{mode}", response_model=ModeMemoryResponse)
async def update_mode_memory(
    mode: str,
    request: UpdateModeMemoryRequest,
    user: CurrentUser = Depends(require_current_user),
):
    """人工编辑指定对话模式的长期记忆（乐观锁：版本号 + 文件 mtime 双重校验）"""
    storage = _get_storage(mode)
    try:
        response = storage.write(
            request.content,
            expected_version=request.expected_version,
            expected_mtime_ns=request.expected_mtime_ns,
        )
        logger.info(
            "mode_memory_manual_update",
            mode=response.mode,
            version=response.meta.get("version"),
            user=getattr(user, "username", None) or getattr(user, "user_id", None),
        )
        return response
    except MemoryVersionConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "memory_version_conflict", "message": str(e)},
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
