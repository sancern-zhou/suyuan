"""Atomic PostgreSQL repository for shared session resource manifests."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.resources.manifest import merge_resource_refs
from app.agent.resources.models import SessionResourceRef
from app.db.database import engine
from app.db.models_session import SessionResourceManifestDB


class SessionResourceRepository:
    def __init__(self, db_engine=None) -> None:
        self.engine = db_engine or engine

    @staticmethod
    def _manifest(session_id: str, refs: list[dict], version: int):
        from app.agent.resources.service import SessionResourceManifest

        return SessionResourceManifest(
            session_id=session_id,
            refs=[SessionResourceRef.model_validate(ref) for ref in refs],
            version=version,
        )

    async def load(self, session_id: str):
        async with AsyncSession(self.engine) as session:
            row = await session.get(SessionResourceManifestDB, session_id)
            if row is None:
                return self._manifest(session_id, [], 0)
            return self._manifest(session_id, row.resource_refs or [], row.version)

    async def merge(self, session_id: str, incoming: list[SessionResourceRef]):
        if not incoming:
            return await self.load(session_id)
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                await session.execute(
                    insert(SessionResourceManifestDB)
                    .values(session_id=session_id, resource_refs=[], version=0)
                    .on_conflict_do_nothing(index_elements=[SessionResourceManifestDB.session_id])
                )
                result = await session.execute(
                    select(SessionResourceManifestDB)
                    .where(SessionResourceManifestDB.session_id == session_id)
                    .with_for_update()
                )
                row = result.scalar_one()
                existing = [
                    SessionResourceRef.model_validate(item)
                    for item in (row.resource_refs or [])
                ]
                merged = merge_resource_refs(existing, incoming)
                row.resource_refs = [ref.model_dump(mode="json") for ref in merged]
                row.version += 1
                row.updated_at = datetime.utcnow()
                version = row.version
            return self._manifest(session_id, [ref.model_dump(mode="json") for ref in merged], version)

    async def delete(self, session_id: str) -> bool:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                delete(SessionResourceManifestDB).where(
                    SessionResourceManifestDB.session_id == session_id
                )
            )
            await session.commit()
            return bool(result.rowcount)
