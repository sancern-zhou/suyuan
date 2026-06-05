"""PostgreSQL advisory lock helpers for session-scoped agent runs."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import time
from typing import AsyncIterator

import structlog
from sqlalchemy import text

from app.db.database import engine

logger = structlog.get_logger()


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
async def session_advisory_lock(session_id: str) -> AsyncIterator[None]:
    """Serialize work for one session_id across uvicorn workers.

    Different session IDs map to different advisory lock keys, so unrelated
    users remain concurrent. The DB connection is held while the lock is held;
    use this only around the full read-run-write lifecycle for a single agent
    conversation turn.
    """
    key = _session_lock_key(session_id)
    wait_started = time.monotonic()
    async with engine.connect() as conn:
        logger.info("session_advisory_lock_waiting", session_id=session_id, **_pool_status())
        await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        acquired_at = time.monotonic()
        logger.info(
            "session_advisory_lock_acquired",
            session_id=session_id,
            wait_ms=round((acquired_at - wait_started) * 1000, 2),
            **_pool_status(),
        )
        try:
            yield
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            logger.info(
                "session_advisory_lock_released",
                session_id=session_id,
                held_ms=round((time.monotonic() - acquired_at) * 1000, 2),
                **_pool_status(),
            )
