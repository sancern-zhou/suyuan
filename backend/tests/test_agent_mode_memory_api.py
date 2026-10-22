"""对话模式长期记忆查看/编辑 API 测试（隔离存储，不触碰真实 registry）"""
import sys
import re
import tempfile
import shutil
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent_memory_routes import ModeMemoryStorage, MemoryVersionConflictError, router
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser

_ADMIN = CurrentUser(
    id="admin-1", username="admin", display_name="管理员", is_admin=True
)


def _storage_factory(temp_dir):
    def _factory(mode: str) -> ModeMemoryStorage:
        return ModeMemoryStorage(mode, base_dir=temp_dir)

    return _factory


@contextmanager
def _client(temp_dir) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: _ADMIN
    with patch(
        "app.api.agent_memory_routes.ModeMemoryStorage",
        _storage_factory(temp_dir),
    ):
        yield TestClient(app)


def test_mode_memory_roundtrip_with_optimistic_lock():
    temp_dir = tempfile.mkdtemp()
    try:
        with _client(temp_dir) as client:
            # 首次读取：自动创建默认模板，版本为 0
            resp = client.get("/api/agent/memory/query")
            assert resp.status_code == 200
            body = resp.json()
            assert body["mode"] == "query"
            assert "长期记忆" in body["memory"]
            assert body["meta"]["version"] == 0

            version = body["meta"]["version"]
            mtime_ns = body["meta"]["file_mtime_ns"]
            # mtime_ns 超出 JS 安全整数范围，必须以字符串下发避免前端精度丢失
            assert isinstance(mtime_ns, str)

            # 人工编辑：版本 +1，标记 manual
            resp = client.put(
                "/api/agent/memory/query",
                json={
                    "content": "# 长期记忆\n\n## 用户偏好\n- 喜欢表格输出",
                    "expected_version": version,
                    "expected_mtime_ns": mtime_ns,
                },
            )
            assert resp.status_code == 200
            updated = resp.json()
            assert updated["meta"]["version"] == 1
            assert updated["meta"]["last_editor"] == "manual"
            assert "表格输出" in updated["memory"]

            # 旧版本提交 → 409
            resp = client.put(
                "/api/agent/memory/query",
                json={
                    "content": "过期内容",
                    "expected_version": 0,
                    "expected_mtime_ns": mtime_ns,
                },
            )
            assert resp.status_code == 409
            assert resp.json()["detail"]["code"] == "memory_version_conflict"

            # 新版本但 mtime 过期（模拟后台整合已改写文件）→ 409
            storage = ModeMemoryStorage("query", base_dir=temp_dir)
            storage.memory_file.write_text("后台整合改写", encoding="utf-8")
            # 显式改 mtime：避免与上一步写入落在文件系统时间戳粒度窗口内导致偶发相同 mtime
            import os as _os

            _st = storage.memory_file.stat()
            _os.utime(storage.memory_file, ns=(_st.st_mtime_ns - 1_000_000_000,) * 2)
            resp = client.put(
                "/api/agent/memory/query",
                json={
                    "content": "人工编辑内容",
                    "expected_version": updated["meta"]["version"],
                    "expected_mtime_ns": mtime_ns,
                },
            )
            assert resp.status_code == 409

            # 重新读取后可正常保存
            fresh = client.get("/api/agent/memory/query").json()
            resp = client.put(
                "/api/agent/memory/query",
                json={
                    "content": "人工编辑内容",
                    "expected_version": fresh["meta"]["version"],
                    "expected_mtime_ns": fresh["meta"]["file_mtime_ns"],
                },
            )
            assert resp.status_code == 200

            # 空内容 → 422
            fresh = client.get("/api/agent/memory/query").json()
            resp = client.put(
                "/api/agent/memory/query",
                json={
                    "content": "   ",
                    "expected_version": fresh["meta"]["version"],
                },
            )
            assert resp.status_code == 422
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_mode_memory_rejects_social_and_invalid_modes():
    temp_dir = tempfile.mkdtemp()
    try:
        with _client(temp_dir) as client:
            for mode in ("social", "enforcement_exam"):
                resp = client.get(f"/api/agent/memory/{mode}")
                assert resp.status_code == 400

            # 路径穿越被拦截/净化：路由不匹配（404）或净化后不产生目录逃逸
            resp = client.get("/api/agent/memory/%2E%2E%2Fescape")
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                escaped = ModeMemoryStorage("escape", base_dir=temp_dir)
                assert escaped.mode_dir.parent == Path(temp_dir)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # 含斜杠/冒号/点号的模式名无法通过路由（404），净化函数兜底保证单层安全目录名
    from app.api.agent_memory_routes import _safe_mode

    sanitized = _safe_mode("query:/../../escape")
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", sanitized)
    assert "/" not in sanitized and "\\" not in sanitized


def test_write_accepts_int_mtime_ns():
    """expected_mtime_ns 兼容整数（旧客户端/服务端内部调用直接传 stat 值）"""
    temp_dir = tempfile.mkdtemp()
    try:
        storage = ModeMemoryStorage("expert", base_dir=temp_dir)
        storage.write("第一版", expected_version=0, expected_mtime_ns=None)
        mtime_ns = storage._memory_mtime_ns_unlocked()
        assert isinstance(mtime_ns, int)
        storage.write("第二版", expected_version=1, expected_mtime_ns=mtime_ns)
        assert "第二版" in storage.read().memory
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_write_rejects_stale_version():
    temp_dir = tempfile.mkdtemp()
    try:
        storage = ModeMemoryStorage("expert", base_dir=temp_dir)
        storage.write("第一版", expected_version=0, expected_mtime_ns=None)
        try:
            storage.write("第二版", expected_version=0, expected_mtime_ns=None)
            assert False, "should raise"
        except MemoryVersionConflictError:
            pass
        assert "第一版" in storage.read().memory
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
