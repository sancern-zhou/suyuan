"""Database-backed storage for structured scheduled task results.

One row per execution in ``scheduled_task_results``. Intentionally
synchronous (matching :class:`~app.scheduled_tasks.storage.execution_storage_db.
DatabaseExecutionStorage`); database work is dispatched through
:mod:`app.db.sync_bridge` or an injected factory for tests.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Tuple

from ..models.result import TaskResult


def task_result_db_enabled() -> bool:
    """Whether structured task results should be persisted to the database.

    ``SCHEDULED_TASK_RESULT_STORAGE=off`` disables writes (unit tests); the
    database is used whenever a ``DATABASE_URL`` is configured.
    """
    configured = os.getenv("SCHEDULED_TASK_RESULT_STORAGE")
    if configured:
        return configured.strip().lower() != "off"
    return bool(os.getenv("DATABASE_URL"))


class DatabaseTaskResultStorage:
    """Persist :class:`TaskResult` records in PostgreSQL."""

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

    # -- write paths ----------------------------------------------------
    def upsert(self, result: TaskResult) -> TaskResult:
        self._run(self._upsert(result))
        return result

    async def _upsert(self, result: TaskResult):
        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        async with self._session() as session:
            row = await session.get(ScheduledTaskResultDB, result.execution_id)
            now = datetime.now()
            if row is None:
                row = ScheduledTaskResultDB(
                    execution_id=result.execution_id,
                    created_at=now,
                )
                session.add(row)
            for key, value in self._row_values(result, now).items():
                setattr(row, key, value)
            await session.commit()

    @staticmethod
    def _row_values(result: TaskResult, now: datetime) -> dict:
        return {
            "task_id": result.task_id,
            "task_name": result.task_name,
            "session_id": result.session_id,
            "status": result.status,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "city": result.city,
            "station_id": result.station_id,
            "station_name": result.station_name,
            "pollutant": result.pollutant,
            "conclusion": result.conclusion,
            "conclusion_source": result.conclusion_source,
            "findings": result.findings,
            "image_paths": result.image_paths,
            "document_paths": result.document_paths,
            "evidence_package_paths": result.evidence_package_paths,
            "report_refs": result.report_refs,
            "broadcast_message": result.broadcast_message,
            "broadcast_image_paths": result.broadcast_image_paths,
            "trigger_type": result.trigger_type,
            "event_id": result.event_id,
            "event_type": result.event_type,
            "extra": result.extra,
            "updated_at": now,
        }

    def delete_by_task(self, task_id: str) -> int:
        return self._run(self._delete_by_task(task_id))

    async def _delete_by_task(self, task_id: str) -> int:
        from sqlalchemy import delete

        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        async with self._session() as session:
            result = await session.execute(
                delete(ScheduledTaskResultDB).where(
                    ScheduledTaskResultDB.task_id == task_id
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    # -- read paths -----------------------------------------------------
    def get(self, execution_id: str) -> Optional[TaskResult]:
        return self._run(self._get(execution_id))

    async def _get(self, execution_id: str) -> Optional[TaskResult]:
        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        async with self._session() as session:
            row = await session.get(ScheduledTaskResultDB, execution_id)
            return self._to_result(row) if row is not None else None

    def query_page(
        self,
        *,
        task_id: Optional[str] = None,
        task_ids: Optional[List[str]] = None,
        city: Optional[str] = None,
        station_id: Optional[str] = None,
        pollutant: Optional[str] = None,
        status: Optional[str] = None,
        started_after: Optional[datetime] = None,
        started_before: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[TaskResult], int]:
        offset = max(page - 1, 0) * page_size
        return self._run(
            self._query_page(
                task_id=task_id,
                task_ids=task_ids,
                city=city,
                station_id=station_id,
                pollutant=pollutant,
                status=status,
                started_after=started_after,
                started_before=started_before,
                offset=offset,
                limit=page_size,
            )
        )

    async def _query_page(
        self,
        *,
        task_id: Optional[str],
        task_ids: Optional[List[str]],
        city: Optional[str],
        station_id: Optional[str],
        pollutant: Optional[str],
        status: Optional[str],
        started_after: Optional[datetime],
        started_before: Optional[datetime],
        offset: int,
        limit: int,
    ) -> Tuple[List[TaskResult], int]:
        from sqlalchemy import func, select

        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        conditions = self._conditions(
            ScheduledTaskResultDB,
            task_id=task_id,
            task_ids=task_ids,
            city=city,
            station_id=station_id,
            pollutant=pollutant,
            status=status,
            started_after=started_after,
            started_before=started_before,
        )

        async with self._session() as session:
            stmt = (
                select(ScheduledTaskResultDB)
                .where(*conditions)
                .order_by(ScheduledTaskResultDB.completed_at.desc().nullslast())
                .offset(offset)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            records = [self._to_result(row) for row in rows]

            count_stmt = select(func.count()).select_from(ScheduledTaskResultDB)
            if conditions:
                count_stmt = count_stmt.where(*conditions)
            total = int((await session.execute(count_stmt)).scalar() or 0)
        return records, total

    def facets(
        self,
        *,
        task_id: Optional[str] = None,
        task_ids: Optional[List[str]] = None,
    ) -> dict:
        """Distinct station/pollutant values for filter dropdowns."""
        return self._run(self._facets(task_id=task_id, task_ids=task_ids))

    async def _facets(
        self,
        *,
        task_id: Optional[str],
        task_ids: Optional[List[str]],
    ) -> dict:
        from sqlalchemy import func, select

        from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB

        conditions = []
        if task_id:
            conditions.append(ScheduledTaskResultDB.task_id == task_id)
        if task_ids:
            conditions.append(ScheduledTaskResultDB.task_id.in_(list(task_ids)))

        stations: dict[str, dict] = {}
        pollutants: list[str] = []
        async with self._session() as session:
            station_stmt = select(
                ScheduledTaskResultDB.station_id,
                func.max(ScheduledTaskResultDB.station_name),
            ).where(
                ScheduledTaskResultDB.station_id.isnot(None),
                ScheduledTaskResultDB.station_id != "",
                *conditions,
            ).group_by(ScheduledTaskResultDB.station_id)
            for station_id, station_name in (await session.execute(station_stmt)).all():
                stations[str(station_id)] = {
                    "station_id": str(station_id),
                    "station_name": str(station_name) if station_name else "",
                }

            pollutant_stmt = select(
                ScheduledTaskResultDB.pollutant
            ).where(
                ScheduledTaskResultDB.pollutant.isnot(None),
                ScheduledTaskResultDB.pollutant != "",
                *conditions,
            ).distinct()
            pollutants = [
                str(value)
                for value in (await session.execute(pollutant_stmt)).scalars().all()
            ]
        return {
            "stations": [stations[key] for key in sorted(stations)],
            "pollutants": sorted(pollutants),
        }

    @staticmethod
    def _conditions(
        model,
        *,
        task_id: Optional[str],
        task_ids: Optional[List[str]] = None,
        city: Optional[str],
        station_id: Optional[str],
        pollutant: Optional[str],
        status: Optional[str],
        started_after: Optional[datetime],
        started_before: Optional[datetime],
    ) -> list:
        conditions = []
        if task_id:
            conditions.append(model.task_id == task_id)
        if task_ids:
            conditions.append(model.task_id.in_(list(task_ids)))
        if city:
            conditions.append(model.city == city)
        if station_id:
            conditions.append(model.station_id == station_id)
        if pollutant:
            conditions.append(model.pollutant == pollutant)
        if status:
            conditions.append(model.status == status)
        if started_after is not None:
            conditions.append(model.completed_at >= started_after)
        if started_before is not None:
            conditions.append(model.completed_at <= started_before)
        return conditions

    @staticmethod
    def _to_result(row) -> TaskResult:
        return TaskResult(
            execution_id=row.execution_id,
            task_id=row.task_id,
            task_name=row.task_name,
            session_id=row.session_id,
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            city=row.city,
            station_id=row.station_id,
            station_name=row.station_name,
            pollutant=row.pollutant,
            conclusion=row.conclusion,
            conclusion_source=row.conclusion_source,
            findings=row.findings or [],
            image_paths=row.image_paths or [],
            document_paths=row.document_paths or [],
            evidence_package_paths=row.evidence_package_paths or [],
            report_refs=row.report_refs or [],
            broadcast_message=row.broadcast_message,
            broadcast_image_paths=row.broadcast_image_paths or [],
            trigger_type=row.trigger_type,
            event_id=row.event_id,
            event_type=row.event_type,
            extra=row.extra or {},
        )
