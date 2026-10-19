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
import pytest_asyncio


@pytest_asyncio.fixture
async def app_transcript_db(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.agent import session as session_module
    from app.agent.session.session_manager_db import SessionManagerDB
    from app.db.models_session import SessionDB, SessionMessageDB
    from app.db.session_repository import SessionRepository

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'transcripts.db'}")
    async with engine.begin() as conn:
        for model in (SessionDB, SessionMessageDB):
            await conn.run_sync(model.__table__.create)
    manager = SessionManagerDB()
    manager.repository = SessionRepository()
    manager.repository.engine = engine
    monkeypatch.setattr(manager.repository, "_pool_status", lambda: {})
    monkeypatch.setattr(session_module, "get_session_manager", lambda: manager)
    yield manager
    await engine.dispose()


@pytest.fixture
def social_mapping_db():
    """Execute actual mapping/report SQL in an isolated database without services."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.social.models import SocialSessionMapping
    from app.social.report_models import SocialReportResult
    engine = create_engine("sqlite:///:memory:")
    SocialSessionMapping.__table__.create(engine)
    SocialReportResult.__table__.create(engine)

    @asynccontextmanager
    async def factory():
        with Session(engine, expire_on_commit=False) as session:
            class Adapter:
                async def execute(self, *args, **kwargs):
                    return session.execute(*args, **kwargs)
                async def get(self, *args, **kwargs):
                    return session.get(*args, **kwargs)
                async def commit(self):
                    session.commit()
            yield Adapter()

    yield factory
    engine.dispose()


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
