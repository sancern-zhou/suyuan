"""源码修复授权（白名单目录 + 任务 tag + git 快照）。

默认 `backend/app`、`config`、`deploy` 等目录被
`path_config.is_agent_protected_write_path` 明确禁止 AI 写入——这是既有
安全边界。本模块提供**受控例外**：仅当全部条件满足时放行对白名单子目录
的写入：

1. 定时任务上下文，且任务 tags 含 "source-repair"（任务级显式授权）；
2. 目标路径在 settings.source_repair_allowed_dirs 白名单内（CSV，项目
   相对路径；默认为空=整体关闭）；
3. 本次执行已取得 git 快照（首次写入前自动向维护守护进程申请；快照
   不可得则拒绝——不可回滚的源码修改不被允许）；
4. 仍然禁止 .env*、config/、deploy/、alembic/ 等敏感面（即使白名单
   配置失误，敏感根依旧硬拒绝）。

快照 ID 以 execution 为键存 Redis，同一次执行内的后续写入复用同一快照
（回滚回到修复前基线，而非中间态）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import structlog

from app.utils.path_config import PROJECT_ROOT, is_agent_sensitive_path

logger = structlog.get_logger(__name__)

SOURCE_REPAIR_TAG = "source-repair"
# 无论白名单怎么配，这些敏感面永不可写（第二道硬边界）。
_HARD_DENIED_PREFIXES = ("backend/.env", "backend/config", "backend/alembic", "deploy/", ".github/", "scripts/")


def _allowed_dirs() -> list[Path]:
    from config.settings import settings

    raw = str(
        os.getenv("SOURCE_REPAIR_ALLOWED_DIRS")
        or getattr(settings, "source_repair_allowed_dirs", "")
        or ""
    )
    dirs = []
    for item in raw.split(","):
        item = item.strip().strip("/").replace("\\", "/")
        if not item:
            continue
        candidate = (PROJECT_ROOT / item).resolve()
        dirs.append(candidate)
    return dirs


def _snapshot_key(execution_id: str) -> str:
    return f"monitor:srcsnapshot:{execution_id}"


async def ensure_source_repair_authorized(context, path) -> tuple[bool, str, Optional[str]]:
    """校验一次源码写入是否被授权。

    返回 (authorized, 说明, snapshot_id)。snapshot_id 非空时调用方应
    随 restart 请求回传，供守护进程失败自动回滚。
    """
    scheduled = getattr(context, "scheduled_task_context", None)
    if not (isinstance(scheduled, dict) and scheduled.get("task_id")):
        return False, "非定时任务上下文，禁止修改源码", None

    tags = scheduled.get("task_tags") or []
    # task context 目前不带 tags——从 prompt 无法可信取 tags，回落到
    # runtime_metadata.scheduled_task（executor._runtime_metadata 同源）。
    meta = getattr(context, "runtime_metadata", None) or {}
    meta_task = meta.get("scheduled_task") or {}
    tags = list(meta_task.get("tags") or tags)
    if SOURCE_REPAIR_TAG not in tags:
        return False, "任务未标记 source-repair，禁止修改源码", None

    resolved = Path(path).resolve()
    allowed = _allowed_dirs()
    if not allowed:
        return False, "源码修复白名单为空（整体关闭）", None
    if not any(resolved.is_relative_to(d) for d in allowed):
        rel = os.path.relpath(resolved, PROJECT_ROOT).replace("\\", "/")
        return False, f"目标不在源码修复白名单内：{rel}", None

    rel = os.path.relpath(resolved, PROJECT_ROOT).replace("\\", "/")
    if rel.startswith(_HARD_DENIED_PREFIXES) or is_agent_sensitive_path(resolved):
        return False, f"敏感路径永不可写：{rel}", None

    # 快照：同一次执行复用
    execution_id = str(scheduled.get("execution_id") or scheduled.get("task_id") or "run")
    snapshot_id = await _get_or_create_snapshot(execution_id)
    if not snapshot_id:
        return False, "git 快照不可得（维护守护进程未就绪），拒绝不可回滚的源码修改", None
    return True, "authorized", snapshot_id


async def _get_or_create_snapshot(execution_id: str) -> Optional[str]:
    from app.monitoring.anomaly_emitter import get_redis_client
    from app.tools.runtime_monitor.service_ops import acquire_source_snapshot

    try:
        client = get_redis_client()
        existing = await client.get(_snapshot_key(execution_id))
        if existing:
            return str(existing)
        result = acquire_source_snapshot(label=f"source-repair:{execution_id}")
        if not result.get("success"):
            return None
        snapshot_id = str(result.get("snapshot_id") or "")
        if snapshot_id:
            await client.set(
                _snapshot_key(execution_id), snapshot_id, ex=3600
            )
        return snapshot_id or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("source_repair_snapshot_error", error=str(exc))
        return None
