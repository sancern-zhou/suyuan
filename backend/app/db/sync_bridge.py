"""Bridge synchronous callers to the application's async database session.

Scheduled-task storage exposes a synchronous API, while the application owns
an async SQLAlchemy session factory.  The bridge keeps those interfaces
separate and runs database coroutines in a small resident thread pool.

Each pool thread owns a private event loop and a pooled engine: asyncpg
forbids sharing connections across event loops, so both the loop and the
engine are thread-local and connections are reused for the thread's lifetime.
This avoids a fresh asyncpg handshake per query (~200ms on this host, the
dominant cost of every scheduled-task management request) and bounds the
connection storm when fetchers write in bursts.

Deadlock note: ``run_db`` dispatches to the pool.  A coroutine running on a
pool thread that synchronously calls ``run_db`` again occupies its thread and
needs another pool thread; keep the pool larger than the possible nesting
depth (currently one level, see tests/scheduled_tasks/test_runtime_monitor_tool.py).
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Awaitable, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session_database import SESSION_DATABASE_URL


T = TypeVar("T")

# 6 个常驻线程 × 每线程 2 连接 + 2 overflow，最坏 ~24 连接，远低于 PG 默认
# max_connections；同时容纳 1 层嵌套 run_db 的场景。
_DB_POOL_SIZE = 6

_pool = ThreadPoolExecutor(
    max_workers=_DB_POOL_SIZE,
    thread_name_prefix="scheduled-task-db",
)
_local = threading.local()   # per-thread: loop, engine
_registry_lock = threading.Lock()
_loops: list[asyncio.AbstractEventLoop] = []
_engines: list = []


def _thread_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.loop = loop
        with _registry_lock:
            _loops.append(loop)
    return loop


def _thread_engine():
    engine = getattr(_local, "engine", None)
    if engine is None:
        engine = create_async_engine(
            SESSION_DATABASE_URL,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
        )
        _local.engine = engine
        # 引擎挂在所属循环上，退出清理时按循环取回，避免与循环登记顺序错位。
        _thread_loop().bridge_engine = engine
        with _registry_lock:
            _engines.append(engine)
    return engine


@asynccontextmanager
async def bridge_session():
    """Yield a session bound to the current thread's resident pooled engine."""
    session_factory = async_sessionmaker(_thread_engine(), expire_on_commit=False)
    async with session_factory() as session:
        yield session


def _run_on_pool_thread(coro: Awaitable[T]) -> T:
    # run_until_complete 可在同一常驻 loop 上反复调用；loop 与引擎均按
    # 线程缓存，池线程复用时连接直接复用。（不能 run_coroutine_threadsafe：
    # 它要求 loop 已在 run_forever，本设计里 loop 只在任务期间运行。）
    return _thread_loop().run_until_complete(coro)


def run_db(coro: Awaitable[T]) -> T:
    """Run a database coroutine from synchronous scheduled-task code.

    ``ScheduledTaskService`` is called from both startup code and async
    scheduler callbacks.  ``asyncio.run`` is valid only when no loop is
    running, so callbacks with an active loop are dispatched to the resident
    pool threads, where engines and connections are cached per thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    return _pool.submit(_run_on_pool_thread, coro).result()


def _shutdown_db_bridge() -> None:
    # 进程退出兜底：借池线程在其 loop 上 dispose 引擎；连接随进程退出由
    # OS/PG 回收，dispose 失败不阻断退出。
    with _registry_lock:
        loops = list(_loops)
        _loops.clear()
        _engines.clear()
    for loop in loops:
        engine = getattr(loop, "bridge_engine", None)
        if engine is None:
            continue
        try:
            _pool.submit(
                lambda l=loop, e=engine: l.run_until_complete(e.dispose())
            ).result(timeout=5)
        except Exception:  # noqa: BLE001 - 退出路径不再抛错
            pass
    _pool.shutdown(wait=False)


atexit.register(_shutdown_db_bridge)
