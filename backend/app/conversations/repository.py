"""PostgreSQL persistence for conversation ownership records."""

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.database import async_session

from .models import ConversationCatalogDB
from .schemas import ConversationCatalogRecord, ConversationSource


class ConversationCatalogRepository:
    @staticmethod
    def _record(row: ConversationCatalogDB) -> ConversationCatalogRecord:
        return ConversationCatalogRecord.model_validate(
            {
                column.name: getattr(row, column.name)
                for column in ConversationCatalogDB.__table__.columns
            }
        )

    async def get(self, session_id: str) -> ConversationCatalogRecord | None:
        async with async_session() as session:
            row = await session.get(ConversationCatalogDB, session_id)
            return self._record(row) if row else None

    async def upsert(
        self, record: ConversationCatalogRecord
    ) -> ConversationCatalogRecord:
        values = record.model_dump(mode="python")
        statement = (
            insert(ConversationCatalogDB)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[ConversationCatalogDB.session_id],
                set_={
                    "mode": values["mode"],
                    "title": values["title"],
                    "updated_at": values["updated_at"],
                },
            )
        )
        async with async_session() as session:
            await session.execute(statement)
            await session.commit()
        stored = await self.get(record.session_id)
        if stored is None:
            raise RuntimeError("catalog_upsert_failed")
        return stored

    async def delete(self, session_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                delete(ConversationCatalogDB).where(
                    ConversationCatalogDB.session_id == session_id
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def list_visible(
        self,
        *,
        user_id: str | None,
        limit: int,
        offset: int,
        source: ConversationSource | None = None,
    ) -> list[ConversationCatalogRecord]:
        statement = select(ConversationCatalogDB)
        if user_id is not None:
            statement = statement.where(
                ConversationCatalogDB.owner_user_id == user_id
            )
        if source is not None:
            statement = statement.where(ConversationCatalogDB.source == source.value)
        statement = (
            statement.order_by(ConversationCatalogDB.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        async with async_session() as session:
            rows = (await session.execute(statement)).scalars().all()
            return [self._record(row) for row in rows]

    async def count_visible(self, *, user_id: str | None) -> int:
        statement = select(func.count()).select_from(ConversationCatalogDB)
        if user_id is not None:
            statement = statement.where(
                ConversationCatalogDB.owner_user_id == user_id
            )
        async with async_session() as session:
            return int((await session.scalar(statement)) or 0)

    async def touch(self, session_id: str, *, title: str | None = None) -> bool:
        values: dict[str, object] = {"updated_at": datetime.utcnow()}
        if title is not None:
            values["title"] = title
        async with async_session() as session:
            result = await session.execute(
                update(ConversationCatalogDB)
                .where(ConversationCatalogDB.session_id == session_id)
                .values(**values)
            )
            await session.commit()
            return result.rowcount > 0
