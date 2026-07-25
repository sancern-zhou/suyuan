"""Transactional repository for current session resource rows."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import ResourceBatchResult, ResourceCounts, ResourcePage, StoredResource
from app.db.database import engine
from app.db.models_session import SessionResourceDB, SessionResourceVersionDB


def _stored(row: SessionResourceDB) -> StoredResource:
    return StoredResource(
        session_id=row.session_id,
        resource_key=row.resource_key,
        resource_id=row.resource_id,
        kind=row.kind,
        role=row.role,
        label=row.label,
        locator=row.locator or {},
        presentation_type=row.presentation_type,
        presentation=row.presentation,
        metadata=row.resource_metadata or {},
        tool_name=row.tool_name,
        run_id=row.run_id,
        turn_sequence=row.turn_sequence,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SessionResourcesRepository:
    def __init__(self, db_engine=None):
        self.engine = db_engine or engine

    async def upsert(
        self,
        session_id: str,
        run_id: str,
        resources: list[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourceBatchResult:
        async with AsyncSession(self.engine) as db:
            async with db.begin():
                version_insert = insert(SessionResourceVersionDB).values(
                    session_id=session_id, version=0
                ).on_conflict_do_nothing(index_elements=[SessionResourceVersionDB.session_id])
                await db.execute(version_insert)
                version_result = await db.execute(
                    select(SessionResourceVersionDB)
                    .where(SessionResourceVersionDB.session_id == session_id)
                    .with_for_update()
                )
                version_row = version_result.scalar_one()
                if resources:
                    now = datetime.utcnow()
                    for declaration in resources:
                        stored = StoredResource.from_declaration(
                            session_id, run_id, declaration, turn_sequence=turn_sequence
                        )
                        values = {
                            "session_id": stored.session_id,
                            "resource_key": stored.resource_key,
                            "resource_id": stored.resource_id,
                            "kind": stored.kind,
                            "role": stored.role,
                            "logical_key": declaration.logical_key,
                            "label": stored.label,
                            "locator": stored.locator,
                            "presentation_type": stored.presentation_type,
                            "presentation": stored.presentation,
                            "resource_metadata": stored.metadata,
                            "tool_name": stored.tool_name,
                            "run_id": stored.run_id,
                            "turn_sequence": stored.turn_sequence,
                            "status": stored.status,
                            "updated_at": now,
                        }
                        statement = insert(SessionResourceDB).values(**values)
                        update_values = {**values, "metadata": stored.metadata}
                        update_values.pop("resource_metadata", None)
                        statement = statement.on_conflict_do_update(
                            index_elements=[SessionResourceDB.session_id, SessionResourceDB.resource_key],
                            set_={**update_values, "created_at": SessionResourceDB.created_at},
                        )
                        await db.execute(statement)
                    version_row.version += 1
                    version_row.updated_at = now
                rows = await db.execute(
                    select(SessionResourceDB)
                    .where(SessionResourceDB.session_id == session_id)
                    .order_by(SessionResourceDB.created_at, SessionResourceDB.resource_key)
                )
                result_version = version_row.version
                stored_rows = [_stored(row) for row in rows.scalars().all()]
            return ResourceBatchResult(result_version, stored_rows)

    async def list(
        self,
        session_id: str,
        *,
        kind: str | None = None,
        presentation_type: str | None = None,
        role: str | None = None,
        status: str = "active",
        limit: int = 100,
        cursor: str | None = None,
    ) -> ResourcePage:
        async with AsyncSession(self.engine) as db:
            statement = select(SessionResourceDB).where(SessionResourceDB.session_id == session_id)
            if kind:
                statement = statement.where(SessionResourceDB.kind == kind)
            if presentation_type:
                statement = statement.where(SessionResourceDB.presentation_type == presentation_type)
            if role:
                statement = statement.where(SessionResourceDB.role == role)
            if status:
                statement = statement.where(SessionResourceDB.status == status)
            statement = statement.order_by(SessionResourceDB.created_at, SessionResourceDB.resource_key)
            if cursor:
                statement = statement.offset(int(cursor))
            statement = statement.limit(limit + 1)
            rows = list((await db.execute(statement)).scalars().all())
            next_cursor = str((int(cursor or 0) + limit)) if len(rows) > limit else None
            return ResourcePage([_stored(row) for row in rows[:limit]], next_cursor)

    async def counts(self, session_id: str) -> ResourceCounts:
        page = await self.list(session_id, status=None, limit=100000)
        return ResourceCounts(
            total=len(page.resources),
            documents=sum(row.presentation_type == "document" for row in page.resources),
            visualizations=sum(row.presentation_type == "visualization" for row in page.resources),
            files=sum(row.kind in {"file", "artifact"} for row in page.resources),
        )

    async def delete_resource(self, session_id: str, resource_key: str) -> bool:
        async with AsyncSession(self.engine) as db:
            result = await db.execute(delete(SessionResourceDB).where(
                SessionResourceDB.session_id == session_id,
                SessionResourceDB.resource_key == resource_key,
            ))
            await db.commit()
            return bool(result.rowcount)

    async def delete_session(self, session_id: str) -> bool:
        async with AsyncSession(self.engine) as db:
            result = await db.execute(delete(SessionResourceDB).where(SessionResourceDB.session_id == session_id))
            await db.execute(delete(SessionResourceVersionDB).where(SessionResourceVersionDB.session_id == session_id))
            await db.commit()
            return bool(result.rowcount)
