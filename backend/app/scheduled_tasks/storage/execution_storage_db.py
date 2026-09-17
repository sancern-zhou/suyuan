"""PostgreSQL-backed scheduled task execution history.

设计要点：
- 对外保持与 :class:`ExecutionStorage` 完全一致的同步接口，服务层与执行器零改动；
- 仅在 app.worker 单写者进程内使用，通过常驻后台事件循环线程驱动 asyncpg；
- 使用独立的小连接池引擎，避免与主业务引擎跨事件循环共享连接；
- 全量保留历史记录，不做任何条数或时间清理（旧 JSON 存储的 50 条上限在此废止）；
- 首次启用时一次性导入旧 ``executions.json`` 存量记录，旧文件保持原样仅作数据来源；
- 任何数据库故障在构造阶段直接抛错暴露，不回退 JSON 存储。
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

import structlog
from sqlalchemy import Integer, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.database import build_async_database_url
from app.db.models.scheduled_task_models import ScheduledTaskExecutionDB
from app.utils.path_config import get_data_registry

from ..models.execution import ExecutionStatus, TaskExecution
from .execution_storage import ExecutionStorage

logger = structlog.get_logger()

_DB_CALL_TIMEOUT_SECONDS = 30.0


class _LoopRunner:
    """Daemon thread owning a persistent event loop for DB calls."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                assert self._loop is not None
                return self._loop
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name="scheduled-execution-db",
                daemon=True,
            )
            self._thread.start()
            return self._loop

    def run(self, coro, timeout: float = _DB_CALL_TIMEOUT_SECONDS) -> Any:
        loop = self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)


_runner = _LoopRunner()
_engine = None
_engine_lock = threading.Lock()


def _get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = create_async_engine(
                build_async_database_url(),
                echo=False,
                pool_size=2,
                max_overflow=3,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_timeout=30,
            )
        return _engine


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _row_values(execution: TaskExecution) -> dict[str, Any]:
    return {
        "execution_id": execution.execution_id,
        "task_id": execution.task_id,
        "task_name": execution.task_name,
        "session_id": execution.session_id,
        "status": execution.status.value if isinstance(execution.status, ExecutionStatus) else str(execution.status),
        "started_at": _naive(execution.started_at),
        "completed_at": _naive(execution.completed_at),
        "duration_seconds": execution.duration_seconds,
        "current_step_index": execution.current_step_index,
        "total_steps": execution.total_steps,
        "completed_steps": execution.completed_steps,
        "failed_steps": execution.failed_steps,
        "trigger_type": execution.trigger_type,
        "scheduled_time": _naive(execution.scheduled_time),
        "event_id": execution.event_id,
        "event_type": execution.event_type,
        "event_attributes": execution.event_attributes or {},
        "delivery_results": execution.delivery_results or [],
        "steps": [step.model_dump(mode="json") for step in execution.steps],
        "error_message": execution.error_message,
    }


def _to_execution(row) -> TaskExecution:
    data = {
        column.name: row[column.name]
        for column in ScheduledTaskExecutionDB.__table__.columns
        if column.name not in {"created_at", "updated_at"}
    }
    return TaskExecution.model_validate(data)


async def _check_connectivity() -> None:
    engine = _get_engine()
    async with engine.connect() as conn:
        from sqlalchemy import text

        await conn.execute(text("SELECT 1"))


async def _ensure_table() -> None:
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ScheduledTaskExecutionDB.__table__.create(
                sync_conn, checkfirst=True
            )
        )


async def _count_all() -> int:
    engine = _get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(select(func.count()).select_from(ScheduledTaskExecutionDB))
        return int(result.scalar() or 0)


async def _import_legacy_rows(rows: List[dict[str, Any]]) -> int:
    if not rows:
        return 0
    engine = _get_engine()
    imported = 0
    skipped = []
    async with engine.begin() as conn:
        for item in rows:
            try:
                execution = TaskExecution.model_validate(item)
            except Exception:  # noqa: BLE001 - 单条脏数据记录后跳过，不阻断整体导入
                skipped.append(str(item.get("execution_id")))
                continue
            statement = (
                insert(ScheduledTaskExecutionDB)
                .values(**_row_values(execution))
                .on_conflict_do_nothing(index_elements=["execution_id"])
            )
            await conn.execute(statement)
            imported += 1
    if skipped:
        logger.warning(
            "scheduled_execution_legacy_rows_skipped",
            count=len(skipped),
            execution_ids=skipped[:20],
        )
    return imported


class ExecutionStorageDB(ExecutionStorage):
    """Execution history in PostgreSQL with unlimited retention."""

    def __init__(self, *, legacy_file: Path | None = None, import_legacy: bool = True):
        # 不调用父类构造：JSON 文件不再是本存储的后端。
        self.legacy_file = legacy_file or (
            get_data_registry() / "scheduled_tasks" / "executions.json"
        )
        _runner.run(_check_connectivity())
        _runner.run(_ensure_table())
        if import_legacy:
            self._import_legacy_once()

    # -- 内部同步门面 -------------------------------------------------

    @staticmethod
    def _run(coro, timeout: float = _DB_CALL_TIMEOUT_SECONDS) -> Any:
        return _runner.run(coro, timeout=timeout)

    def _import_legacy_once(self) -> None:
        if self._run(_count_all()) > 0:
            return
        if not self.legacy_file.is_file():
            return
        rows = json.loads(self.legacy_file.read_text(encoding="utf-8"))
        imported = self._run(_import_legacy_rows(rows))
        if imported:
            logger.info(
                "scheduled_execution_legacy_imported",
                count=imported,
                source=str(self.legacy_file),
            )

    # -- 写接口 -------------------------------------------------------

    def create(self, execution: TaskExecution) -> TaskExecution:
        values = _row_values(execution)

        async def _create() -> None:
            engine = _get_engine()
            async with engine.begin() as conn:
                await conn.execute(
                    insert(ScheduledTaskExecutionDB)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=["execution_id"])
                )

        self._run(_create())
        return execution

    def update(self, execution: TaskExecution) -> TaskExecution:
        values = _row_values(execution)

        async def _update() -> None:
            engine = _get_engine()
            async with engine.begin() as conn:
                await conn.execute(
                    insert(ScheduledTaskExecutionDB)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["execution_id"],
                        set_={
                            key: value
                            for key, value in values.items()
                            if key != "execution_id"
                        },
                    )
                )

        self._run(_update())
        return execution

    # -- 读接口 -------------------------------------------------------

    def get(self, execution_id: str) -> Optional[TaskExecution]:
        async def _get() -> Optional[TaskExecution]:
            engine = _get_engine()
            statement = select(ScheduledTaskExecutionDB).where(
                ScheduledTaskExecutionDB.execution_id == execution_id
            )
            async with engine.begin() as conn:
                row = (await conn.execute(statement)).mappings().first()
                return _to_execution(row) if row is not None else None

        return self._run(_get())

    def _list_statement_filters(self, task_id: Optional[str], status: Optional[ExecutionStatus]):
        filters = []
        if task_id:
            filters.append(ScheduledTaskExecutionDB.task_id == task_id)
        if status:
            filters.append(ScheduledTaskExecutionDB.status == status.value)
        return filters

    def list_by_task(
        self,
        task_id: str,
        limit: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> List[TaskExecution]:
        async def _list() -> List[TaskExecution]:
            engine = _get_engine()
            statement = (
                select(ScheduledTaskExecutionDB)
                .where(*self._list_statement_filters(task_id, status))
                .order_by(
                    ScheduledTaskExecutionDB.started_at.desc(),
                    ScheduledTaskExecutionDB.execution_id.desc(),
                )
                .limit(limit)
            )
            async with engine.begin() as conn:
                rows = (await conn.execute(statement)).mappings().all()
                return [_to_execution(row) for row in rows]

        return self._run(_list())

    def list_by_task_page(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> tuple[List[TaskExecution], int]:
        async def _list_page() -> tuple[List[TaskExecution], int]:
            engine = _get_engine()
            filters = self._list_statement_filters(task_id, status)
            count_statement = (
                select(func.count()).select_from(ScheduledTaskExecutionDB).where(*filters)
            )
            list_statement = (
                select(ScheduledTaskExecutionDB)
                .where(*filters)
                .order_by(
                    ScheduledTaskExecutionDB.started_at.desc(),
                    ScheduledTaskExecutionDB.execution_id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            async with engine.begin() as conn:
                total = int((await conn.execute(count_statement)).scalar() or 0)
                rows = (await conn.execute(list_statement)).mappings().all()
                return [_to_execution(row) for row in rows], total

        return self._run(_list_page())

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[ExecutionStatus] = None,
    ) -> List[TaskExecution]:
        async def _list() -> List[TaskExecution]:
            engine = _get_engine()
            statement = (
                select(ScheduledTaskExecutionDB)
                .where(*self._list_statement_filters(None, status))
                .order_by(
                    ScheduledTaskExecutionDB.started_at.desc(),
                    ScheduledTaskExecutionDB.execution_id.desc(),
                )
                .limit(limit)
            )
            async with engine.begin() as conn:
                rows = (await conn.execute(statement)).mappings().all()
                return [_to_execution(row) for row in rows]

        return self._run(_list())

    def list_recent_page(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> tuple[List[TaskExecution], int]:
        async def _list_page() -> tuple[List[TaskExecution], int]:
            engine = _get_engine()
            filters = self._list_statement_filters(None, status)
            count_statement = (
                select(func.count()).select_from(ScheduledTaskExecutionDB).where(*filters)
            )
            list_statement = (
                select(ScheduledTaskExecutionDB)
                .where(*filters)
                .order_by(
                    ScheduledTaskExecutionDB.started_at.desc(),
                    ScheduledTaskExecutionDB.execution_id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            async with engine.begin() as conn:
                total = int((await conn.execute(count_statement)).scalar() or 0)
                rows = (await conn.execute(list_statement)).mappings().all()
                return [_to_execution(row) for row in rows], total

        return self._run(_list_page())

    def get_running_executions(self) -> List[TaskExecution]:
        async def _running() -> List[TaskExecution]:
            engine = _get_engine()
            statement = select(ScheduledTaskExecutionDB).where(
                ScheduledTaskExecutionDB.status == ExecutionStatus.RUNNING.value
            )
            async with engine.begin() as conn:
                rows = (await conn.execute(statement)).mappings().all()
                return [_to_execution(row) for row in rows]

        return self._run(_running())

    def delete_by_task(self, task_id: str) -> int:
        async def _delete() -> int:
            engine = _get_engine()
            async with engine.begin() as conn:
                result = await conn.execute(
                    delete(ScheduledTaskExecutionDB).where(
                        ScheduledTaskExecutionDB.task_id == task_id
                    )
                )
                return int(result.rowcount or 0)

        return self._run(_delete())

    def get_statistics(self, task_id: Optional[str] = None, days: int = 7) -> dict:
        cutoff = datetime.now() - timedelta(days=days)

        async def _stats() -> dict:
            engine = _get_engine()
            filters = [
                ScheduledTaskExecutionDB.started_at >= cutoff,
            ]
            if task_id:
                filters.append(ScheduledTaskExecutionDB.task_id == task_id)
            base = select(
                func.count().label("total"),
                func.sum(
                    func.cast(
                        ScheduledTaskExecutionDB.status == ExecutionStatus.SUCCESS.value,
                        Integer,
                    )
                ).label("success"),
                func.sum(
                    func.cast(
                        ScheduledTaskExecutionDB.status == ExecutionStatus.FAILED.value,
                        Integer,
                    )
                ).label("failed"),
                func.sum(
                    func.cast(
                        ScheduledTaskExecutionDB.status == ExecutionStatus.RUNNING.value,
                        Integer,
                    )
                ).label("running"),
                func.avg(ScheduledTaskExecutionDB.duration_seconds).label("avg_duration"),
            ).where(*filters)
            async with engine.begin() as conn:
                row = (await conn.execute(base)).one()
            total = int(row.total or 0)
            success = int(row.success or 0)
            failed = int(row.failed or 0)
            running = int(row.running or 0)
            avg_duration = float(row.avg_duration or 0)
            return {
                "total": total,
                "success": success,
                "failed": failed,
                "running": running,
                "success_rate": success / total if total > 0 else 0,
                "avg_duration_seconds": avg_duration,
                "period_days": days,
            }

        return self._run(_stats())
