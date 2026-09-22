"""Bridge synchronous callers to the application's async database session.

Scheduled-task storage exposes a synchronous API, while the application owns
an async SQLAlchemy session factory.  The bridge keeps those interfaces
separate and runs database coroutines in a short-lived event loop when the
caller is already inside the worker's event loop.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import Thread
from typing import Awaitable, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session_database import SESSION_DATABASE_URL


T = TypeVar("T")


@asynccontextmanager
async def bridge_session():
    """Yield the application's async database session factory."""
    # The bridge may run in a helper thread when the caller already owns an
    # asyncio loop.  Use a thread-local engine so asyncpg connections are not
    # reused across event loops.
    engine = create_async_engine(SESSION_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


def run_db(coro: Awaitable[T]) -> T:
    """Run a database coroutine from synchronous scheduled-task code.

    ``ScheduledTaskService`` is called from both startup code and async
    scheduler callbacks.  ``asyncio.run`` is valid only when no loop is
    running, so callbacks with an active loop use a dedicated thread and
    propagate the result or exception back to the caller.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[T] = []
    error: list[BaseException] = []

    def _run() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # propagate database errors unchanged
            error.append(exc)

    thread = Thread(target=_run, name="scheduled-task-db", daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
