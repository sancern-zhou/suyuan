# -*- coding: utf-8 -*-
"""测试套件公共配置。

Windows 本地开发环境没有 fcntl（Unix 专用），而 app.services 等模块在
顶层无条件导入它；此处仅在真实 fcntl 不可用时注入无操作替身，
Linux/CI 上不受影响。
"""
from __future__ import annotations

import sys
import types

try:
    import fcntl  # noqa: F401
except ImportError:  # pragma: no cover - 仅 Windows 本地测试路径
    _fcntl_stub = types.ModuleType("fcntl")
    _fcntl_stub.LOCK_EX = 2
    _fcntl_stub.LOCK_SH = 1
    _fcntl_stub.LOCK_UN = 8
    _fcntl_stub.flock = lambda *args, **kwargs: None
    sys.modules["fcntl"] = _fcntl_stub


from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
import pytest


@pytest.fixture
def fake_lock_db(monkeypatch):
    """Model PostgreSQL session locks with one new connection per checkout."""
    import app.agent.runtime.session_advisory_lock as module
    locked, connections = set(), []

    class Connection:
        key = None
        invalidated = False
        unlock_error = False
        async def execution_options(self, **kwargs): return self
        async def execute(self, statement, params):
            key = params["key"]
            if "pg_try_advisory_lock" in str(statement):
                acquired = key not in locked
                if acquired:
                    locked.add(key)
                    self.key = key
                return NS(scalar=lambda: acquired)
            if self.unlock_error:
                raise RuntimeError("unlock connection failure")
            unlocked = self.key == key and key in locked
            if unlocked:
                locked.remove(key)
                self.key = None
            return NS(scalar=lambda: unlocked)
        async def invalidate(self):
            self.invalidated = True
            if self.key is not None:
                locked.discard(self.key)
                self.key = None

    @asynccontextmanager
    async def connect():
        conn = Connection()
        connections.append(conn)
        yield conn

    monkeypatch.setattr(module, "engine", NS(connect=connect))
    monkeypatch.setattr(module, "_pool_status", lambda: {})
    return NS(locked=locked, connections=connections)
