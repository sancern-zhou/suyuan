"""PostgreSQL advisory lock helpers for session-scoped agent runs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import asyncio
import hashlib
import time
from typing import AsyncIterator

import structlog
from sqlalchemy import text

from app.db.database import engine

logger = structlog.get_logger()


@dataclass
class _HeldSession:
    session_id: str
    task: asyncio.Task
    active: bool = True


_held_sessions: ContextVar[tuple[_HeldSession, ...]] = ContextVar("agent_session_locks", default=())


class SessionRunConflict(RuntimeError):
    """Another process is already executing this conversation turn."""


def serialize_agent_session(function):
    """Guard non-HTTP callers too; route guards also cover their final saves."""
    @wraps(function)
    async def stream(self, user_query, session_id=None, *args, **kwargs):
        session_id = session_id or self._generate_session_id()
        async with session_advisory_lock(session_id):
            gen = function(self, user_query, session_id, *args, **kwargs)
            try:
                async for event in gen:
                    yield event
            finally:
                await gen.aclose()
    return stream


def _session_lock_key(session_id: str) -> int:
    digest = hashlib.sha256(session_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _pool_status() -> dict:
    pool = engine.pool
    return {
        "pool_status": pool.status(),
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
    }


@asynccontextmanager
async def session_advisory_lock(session_id: str, *, wait_timeout: float = 0) -> AsyncIterator[None]:
    """Serialize work for one session_id across uvicorn workers.

    Different session IDs map to different advisory lock keys, so unrelated
    users remain concurrent. The DB connection is held while the lock is held;
    use this only around the full read-run-write lifecycle for a single agent
    conversation turn.
    """
    # Contexts propagate to child tasks; only the actual owning task may
    # re-enter. A subagent must not inherit permission to run the same session.
    owner_task = asyncio.current_task()
    held = tuple(item for item in _held_sessions.get() if item.active)
    if any(item.session_id == session_id and item.task is owner_task for item in held):
        yield
        return
    key = _session_lock_key(session_id)
    wait_started = time.monotonic()
    async with engine.connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
        logger.info("session_advisory_lock_waiting", session_id=session_id, **_pool_status())
        deadline = time.monotonic() + max(0, wait_timeout)
        while True:
            acquired = await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if acquired.scalar():
                break
            if time.monotonic() >= deadline:
                raise SessionRunConflict("session_run_in_progress")
            await asyncio.sleep(min(0.05, max(0, deadline - time.monotonic())))
        acquired_at = time.monotonic()
        logger.info(
            "session_advisory_lock_acquired",
            session_id=session_id,
            wait_ms=round((acquired_at - wait_started) * 1000, 2),
            **_pool_status(),
        )
        ownership = _HeldSession(session_id, owner_task)
        _held_sessions.set(held + (ownership,))
        try:
            yield
        finally:
            # Detached-stream cleanup may close the generator in another task.
            # A shared lease marks the original context stale without resetting
            # a ContextVar token from a different context.
            ownership.active = False
            _held_sessions.set(tuple(item for item in _held_sessions.get() if item.active))
            try:
                unlock_result = await conn.execute(
                    text("SELECT pg_advisory_unlock(:key) AS unlocked"),
                    {"key": key},
                )
                if not unlock_result.scalar():
                    await conn.invalidate()
            except BaseException:
                # Never return a connection holding a session lock to the pool.
                await conn.invalidate()
                raise
            logger.info(
                "session_advisory_lock_released",
                session_id=session_id,
                held_ms=round((time.monotonic() - acquired_at) * 1000, 2),
                **_pool_status(),
            )
