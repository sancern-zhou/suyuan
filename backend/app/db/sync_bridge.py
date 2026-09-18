"""Dedicated event-loop bridge for synchronous database call sites.

Some facades (scheduled task execution storage, one-off migration scripts)
expose synchronous APIs but need async SQLAlchemy sessions. ``asyncio.run()``
per call would rebuild an engine pool every time and cannot be used from
threads that already run their own event loop (web/worker processes). This
module therefore owns:

* one daemon thread with a persistent asyncio loop, and
* one small async engine dedicated to that loop,

so every bridged coroutine and every pooled connection live on the same
loop. The main application engine is intentionally NOT shared: pooled
connections must never cross event loops.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager

import structlog

logger = structlog.get_logger()


class _BridgeLoop:
    """Persistent background event loop owned by this process."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started = threading.Event()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._started.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def get(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                self._thread = threading.Thread(
                    target=self._run, name="db-sync-bridge", daemon=True
                )
                self._thread.start()
                self._started.wait()
            assert self._loop is not None
            return self._loop


_bridge = _BridgeLoop()

_engine = None
_session_factory = None
_schema_lock = threading.Lock()
_schema_ready = threading.Event()


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.db.database import DATABASE_URL

        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        logger.info(
            "sync_bridge_engine_created",
            database_url=DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "",
        )
    return _session_factory


async def _ensure_schema() -> None:
    """Create the scheduled execution table on the bridge engine."""
    from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB

    factory = _get_session_factory()
    async with factory() as session:
        conn = await session.connection()
        await conn.run_sync(ScheduledTaskExecutionDB.__table__.create, checkfirst=True)
        await session.commit()


@asynccontextmanager
async def bridge_session():
    """Yield an async session bound to the bridge engine/loop."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


def run_db(coro):
    """Run *coro* on the bridge loop and return its result.

    Callable from any thread, including threads that run their own asyncio
    loop; the caller blocks until the coroutine finishes. Exceptions raised
    inside the coroutine propagate to the caller.
    """
    loop = _bridge.get()
    with _schema_lock:
        if not _schema_ready.is_set():
            asyncio.run_coroutine_threadsafe(_ensure_schema(), loop).result()
            _schema_ready.set()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
