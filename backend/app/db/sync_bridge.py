"""Sync facade over the async engine via a dedicated background event loop.

Service-layer code (task reviews, smart events, scheduled-task storage) exposes
synchronous signatures that tools, fetchers and tests call directly. This
bridge runs a private event loop on a daemon thread with its own engine so
those synchronous call sites can reach the database without blocking (or
belonging to) the main application loop.

Two databases back the facade: the business database (``DATABASE_URL``) used by
task reviews and smart events, and the session database (``SESSION_DATABASE_URL``,
which falls back to ``DATABASE_URL``) that owns sessions and scheduled-task
executions.  Each has its own bridge engine because asyncpg connections cannot
be shared across event loops.
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Awaitable, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import DATABASE_URL
from app.db.session_database import SESSION_DATABASE_URL

T = TypeVar("T")

_state: dict = {"loop": None, "session_factory": None, "session_db_factory": None}
_guard = threading.Lock()


def _ensure_loop() -> None:
    if _state["loop"] is not None:
        return
    with _guard:
        if _state["loop"] is not None:
            return
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True, name="db-sync-bridge")
        thread.start()
        engine = create_async_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        session_engine = create_async_engine(
            SESSION_DATABASE_URL,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _state["loop"] = loop
        _state["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
        _state["session_db_factory"] = async_sessionmaker(session_engine, expire_on_commit=False)


def run_db(coro, timeout: float = 120.0):
    """Run an async DB coroutine on the bridge loop and return its result."""
    _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _state["loop"])
    return future.result(timeout=timeout)


async def run_db_async(coro, timeout: float = 30.0):
    """Await a bridge-loop DB coroutine from any event loop without blocking it.

    All bridge sessions (and their pooled connections) belong to the bridge
    loop, so coroutines using ``bridge_session`` must execute there even when
    awaited from the application loop.
    """
    _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _state["loop"])
    return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)


@asynccontextmanager
async def bridge_session():
    """Yield an AsyncSession bound to the bridge loop for the business database."""
    _ensure_loop()
    async with _state["session_factory"]() as session:
        yield session


@asynccontextmanager
async def session_db_session():
    """Yield an AsyncSession bound to the bridge loop for the session database."""
    _ensure_loop()
    async with _state["session_db_factory"]() as session:
        yield session
