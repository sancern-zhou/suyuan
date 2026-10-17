"""Database-owned social mappings, shared by all web and worker processes."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.session_database import session_async_session
from app.social.models import SocialSessionMapping as Mapping


class SessionMapper:
    def __init__(self, db_manager=None):
        self.db_manager = db_manager or session_async_session

    @staticmethod
    def new_session_id(mode: str = "assistant") -> str:
        return f"{mode}_session_{int(datetime.now().timestamp() * 1000)}_{secrets.token_hex(6)}"

    @staticmethod
    def _expired(cutoff):
        return (~Mapping.social_user_id.startswith("app:")) & (Mapping.last_used <= cutoff)

    async def load(self) -> None:
        """Check readiness without caching a snapshot or falling back to files."""
        async with self.db_manager() as db:
            await db.execute(select(Mapping.social_user_id).limit(1))

    async def save_mapping(self, social_user_id: str, session_id: str) -> None:
        changed = Mapping.session_id != session_id
        statement = insert(Mapping).values(
            social_user_id=social_user_id, session_id=session_id, last_used=datetime.now(),
            last_consolidated_offset=0, total_message_count=0,
        ).on_conflict_do_update(
            index_elements=[Mapping.social_user_id],
            set_={
                "session_id": session_id, "last_used": datetime.now(),
                "last_consolidated_offset": case((changed, 0), else_=Mapping.last_consolidated_offset),
                "total_message_count": case((changed, 0), else_=Mapping.total_message_count),
            },
        )
        async with self.db_manager() as db:
            await db.execute(statement)
            await db.commit()

    async def get_or_create_session(self, social_user_id: str, mode: str = "assistant") -> str:
        now = datetime.now()
        candidate = self.new_session_id(mode)
        expired = self._expired(now - timedelta(hours=24))
        statement = insert(Mapping).values(
            social_user_id=social_user_id, session_id=candidate, last_used=now,
            last_consolidated_offset=0, total_message_count=0,
        ).on_conflict_do_update(
            index_elements=[Mapping.social_user_id],
            set_={
                "session_id": case((expired, candidate), else_=Mapping.session_id),
                "last_used": now,
                "last_consolidated_offset": case((expired, 0), else_=Mapping.last_consolidated_offset),
                "total_message_count": case((expired, 0), else_=Mapping.total_message_count),
            },
        ).returning(Mapping.session_id)
        async with self.db_manager() as db:
            session_id = (await db.execute(statement)).scalar_one()
            await db.commit()
            return session_id

    async def get_session(self, social_user_id: str) -> str | None:
        async with self.db_manager() as db:
            result = await db.execute(update(Mapping).where(
                Mapping.social_user_id == social_user_id,
                ~self._expired(datetime.now() - timedelta(hours=24)),
            ).values(last_used=datetime.now()).returning(Mapping.session_id))
            session_id = result.scalar_one_or_none()
            await db.commit()
            return session_id

    async def get_mapping_info(self, social_user_id: str) -> dict | None:
        async with self.db_manager() as db:
            row = (await db.execute(select(Mapping).where(
                Mapping.social_user_id == social_user_id,
                ~self._expired(datetime.now() - timedelta(hours=24)),
            ))).scalar_one_or_none()
            if row is None:
                return None
            return {column.name: getattr(row, column.name) for column in Mapping.__table__.columns}

    async def delete_mapping(self, social_user_id: str) -> bool:
        async with self.db_manager() as db:
            result = await db.execute(delete(Mapping).where(Mapping.social_user_id == social_user_id))
            await db.commit()
            return bool(result.rowcount)

    async def cleanup_expired(self, ttl_hours: int = 24) -> int:
        async with self.db_manager() as db:
            result = await db.execute(delete(Mapping).where(
                self._expired(datetime.now() - timedelta(hours=ttl_hours))
            ))
            await db.commit()
            return int(result.rowcount or 0)

    async def get_all_social_user_ids(self) -> list[str]:
        async with self.db_manager() as db:
            return list((await db.execute(select(Mapping.social_user_id))).scalars().all())

    async def count_active(self) -> int:
        async with self.db_manager() as db:
            return (await db.execute(select(func.count()).select_from(Mapping).where(
                ~self._expired(datetime.now() - timedelta(hours=24))
            ))).scalar_one()

    async def list_active(self, limit: int = 100) -> list[dict]:
        async with self.db_manager() as db:
            rows = (await db.execute(select(Mapping).where(
                ~self._expired(datetime.now() - timedelta(hours=24))
            ).order_by(Mapping.last_used.desc(), Mapping.social_user_id).limit(min(max(limit, 1), 1000)))).scalars().all()
            return [{column.name: getattr(row, column.name) for column in Mapping.__table__.columns} for row in rows]

    async def update_consolidation_offset(
        self, social_user_id: str, new_offset: int, total_count: int,
        *, expected_session_id: str | None = None,
    ) -> None:
        statement = update(Mapping).where(Mapping.social_user_id == social_user_id)
        if expected_session_id:
            statement = statement.where(Mapping.session_id == expected_session_id)
        async with self.db_manager() as db:
            await db.execute(statement.values(
                last_consolidated_offset=new_offset, total_message_count=total_count,
            ))
            await db.commit()
