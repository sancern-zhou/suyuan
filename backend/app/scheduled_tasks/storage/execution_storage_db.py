"""Database-backed scheduled task execution storage.

Drop-in replacement for :class:`ExecutionStorage` that persists each
execution as its own row instead of rewriting a single ``executions.json``
file. This removes the global 50-record cap and makes concurrent access from
the web and worker processes safe.

The public interface is intentionally synchronous (matching the legacy file
store); database work is dispatched through the async session factory owned
by :mod:`app.db.sync_bridge` or an injected factory for tests.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from ..models.execution import ExecutionStatus, TaskExecution


def execution_db_enabled() -> bool:
    """Whether scheduled executions should use the database backend.

    ``SCHEDULED_TASK_EXECUTION_STORAGE=file`` forces the legacy JSON store
    (used by the test suite); otherwise the database is used whenever a
    ``DATABASE_URL`` is configured.
    """
    configured = os.getenv("SCHEDULED_TASK_EXECUTION_STORAGE")
    if configured:
        return configured.strip().lower() != "file"
    return bool(os.getenv("DATABASE_URL"))


class DatabaseExecutionStorage:
    """Persist :class:`TaskExecution` records in PostgreSQL."""

    def __init__(self, session_factory=None, runner=None):
        self._session_factory = session_factory
        self._runner = runner

    # -- infrastructure -------------------------------------------------
    @asynccontextmanager
    async def _session(self):
        if self._session_factory is not None:
            async with self._session_factory() as session:
                yield session
        else:
            from app.db.sync_bridge import bridge_session

            async with bridge_session() as session:
                yield session

    def _run(self, coro):
        if self._runner is not None:
            return self._runner(coro)
        from app.db.sync_bridge import run_db

        return run_db(coro)

    @staticmethod
    def _row_values(execution: TaskExecution) -> dict:
        now = datetime.now()
        return {
            "task_id": execution.task_id,
            "task_name": execution.task_name,
            "session_id": execution.session_id,
            "status": execution.status.value,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "duration_seconds": execution.duration_seconds,
            "trigger_type": execution.trigger_type,
            "event_id": execution.event_id,
            "event_type": execution.event_type,
            "total_steps": execution.total_steps,
            "completed_steps": execution.completed_steps,
            "failed_steps": execution.failed_steps,
            "error_message": execution.error_message,
            "data": execution.model_dump(mode="json"),
            "updated_at": now,
        }

    # -- write paths ----------------------------------------------------
    def create(self, execution: TaskExecution) -> TaskExecution:
        self._run(self._upsert(execution, require_existing=False))
        return execution

    def update(self, execution: TaskExecution) -> TaskExecution:
        self._run(self._upsert(execution, require_existing=True))
        return execution

    async def _upsert(self, execution: TaskExecution, *, require_existing: bool):
        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        async with self._session() as session:
            row = await session.get(ScheduledTaskExecutionDB, execution.execution_id)
            if row is None:
                if require_existing:
                    raise ValueError(
                        f"Execution {execution.execution_id} not found"
                    )
                row = ScheduledTaskExecutionDB(
                    execution_id=execution.execution_id,
                    created_at=datetime.now(),
                )
                session.add(row)
            for key, value in self._row_values(execution).items():
                setattr(row, key, value)
            await session.commit()

    def delete_by_task(self, task_id: str) -> int:
        return self._run(self._delete_by_task(task_id))

    async def _delete_by_task(self, task_id: str) -> int:
        from sqlalchemy import delete

        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        async with self._session() as session:
            result = await session.execute(
                delete(ScheduledTaskExecutionDB).where(
                    ScheduledTaskExecutionDB.task_id == task_id
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    # -- read paths -----------------------------------------------------
    def get(self, execution_id: str) -> Optional[TaskExecution]:
        return self._run(self._get(execution_id))

    async def _get(self, execution_id: str) -> Optional[TaskExecution]:
        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        async with self._session() as session:
            row = await session.get(ScheduledTaskExecutionDB, execution_id)
            return TaskExecution(**row.data) if row is not None else None

    def list_by_task(
        self,
        task_id: str,
        limit: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> List[TaskExecution]:
        records, _ = self._run(
            self._query_page(task_id=task_id, offset=0, limit=limit, status=status)
        )
        return records

    def list_by_task_page(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> tuple[List[TaskExecution], int]:
        offset = max(page - 1, 0) * page_size
        return self._run(
            self._query_page(
                task_id=task_id,
                offset=offset,
                limit=page_size,
                status=status,
                with_total=True,
            )
        )

    def list_recent(
        self,
        limit: int = 20,
        status: Optional[ExecutionStatus] = None,
    ) -> List[TaskExecution]:
        records, _ = self._run(
            self._query_page(task_id=None, offset=0, limit=limit, status=status)
        )
        return records

    def list_recent_page(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[ExecutionStatus] = None,
    ) -> tuple[List[TaskExecution], int]:
        offset = max(page - 1, 0) * page_size
        return self._run(
            self._query_page(
                task_id=None,
                offset=offset,
                limit=page_size,
                status=status,
                with_total=True,
            )
        )

    async def _query_page(
        self,
        task_id: Optional[str],
        offset: int,
        limit: int,
        status: Optional[ExecutionStatus],
        with_total: bool = False,
    ) -> tuple[List[TaskExecution], int]:
        from sqlalchemy import func, select

        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        conditions = []
        if task_id is not None:
            conditions.append(ScheduledTaskExecutionDB.task_id == task_id)
        if status is not None:
            conditions.append(ScheduledTaskExecutionDB.status == status.value)

        async with self._session() as session:
            stmt = (
                select(ScheduledTaskExecutionDB)
                .where(*conditions)
                .order_by(ScheduledTaskExecutionDB.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            records = [TaskExecution(**row.data) for row in rows]

            total = len(records)
            if with_total:
                count_stmt = select(func.count()).select_from(
                    ScheduledTaskExecutionDB
                )
                if conditions:
                    count_stmt = count_stmt.where(*conditions)
                total = int((await session.execute(count_stmt)).scalar() or 0)
        return records, total

    def get_running_executions(self) -> List[TaskExecution]:
        return self._run(self._get_running())

    async def _get_running(self) -> List[TaskExecution]:
        from sqlalchemy import select

        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        async with self._session() as session:
            stmt = select(ScheduledTaskExecutionDB).where(
                ScheduledTaskExecutionDB.status == ExecutionStatus.RUNNING.value
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [TaskExecution(**row.data) for row in rows]

    # -- statistics -----------------------------------------------------
    def get_statistics(self, task_id: Optional[str] = None, days: int = 7) -> dict:
        return self._run(self._get_statistics(task_id, days))

    async def _get_statistics(self, task_id: Optional[str], days: int) -> dict:
        from sqlalchemy import func, select

        from app.db.models.scheduled_task_execution_db import (
            ScheduledTaskExecutionDB,
        )

        cutoff = datetime.now() - timedelta(days=days)
        conditions = [ScheduledTaskExecutionDB.started_at >= cutoff]
        if task_id:
            conditions.append(ScheduledTaskExecutionDB.task_id == task_id)

        async with self._session() as session:
            status_stmt = (
                select(
                    ScheduledTaskExecutionDB.status,
                    func.count(),
                )
                .where(*conditions)
                .group_by(ScheduledTaskExecutionDB.status)
            )
            counts = {
                str(status): int(count)
                for status, count in (await session.execute(status_stmt)).all()
            }

            duration_stmt = select(func.avg(ScheduledTaskExecutionDB.duration_seconds)).where(
                *conditions,
                ScheduledTaskExecutionDB.duration_seconds.isnot(None),
            )
            avg_duration = float(
                (await session.execute(duration_stmt)).scalar() or 0.0
            )

        total = sum(counts.values())
        success = counts.get(ExecutionStatus.SUCCESS.value, 0)
        failed = counts.get(ExecutionStatus.FAILED.value, 0)
        running = counts.get(ExecutionStatus.RUNNING.value, 0)

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "running": running,
            "success_rate": success / total if total > 0 else 0,
            "avg_duration_seconds": avg_duration,
            "period_days": days,
        }
