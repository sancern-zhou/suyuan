"""Account-owned assistant transcripts shared by Web and App, exclusively in SQL."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import Integer, func, select, update

from app.auth.identity_matching import primary_owner_id, visible_owner_ids
from app.conversations.models import ConversationCatalogDB as Catalog, ConversationReadDB as Read
from app.db.models_session import SessionDB, SessionMessageDB as Message

VISIBLE_TYPES = ("user", "final", "error", "fatal_error", "incomplete", "interrupted")


class AssistantConversationSync:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from app.db.session_database import session_async_session
            session_factory = session_async_session
        self.session_factory = session_factory

    @staticmethod
    def _scope(user, modes=("assistant",)):
        # Administrative read access never grants personal assistant authority.
        return (
            Catalog.owner_user_id.in_(visible_owner_ids(user.id)),
            Catalog.source == "web",
            Catalog.mode.in_(modes),
            Catalog.read_only_on_web.is_(False),
            ~Catalog.session_id.startswith("scheduled_task_"),
        )

    async def _require(self, db, user, session_id):
        row = (await db.execute(select(Catalog).where(
            Catalog.session_id == session_id, *self._scope(user)
        ))).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "session_not_found")
        return row

    async def summaries(self, user, *, limit=100, offset=0, modes=("assistant",)):
        owner = primary_owner_id(user.id)
        async with self.session_factory() as db:
            # Aggregate before paging; empty drafts never displace actual conversations.
            watermarks = select(
                Message.session_id,
                func.max(Message.sequence_number).label("last_sequence"),
                func.max(Message.id).label("revision"),
                func.max(Message.created_at).label("last_message_at"),
                func.sum((Message.sequence_number > func.coalesce(Read.through_sequence, -1)).cast(
                    Integer
                )).label("unread_count"),
            ).outerjoin(Read, (Read.session_id == Message.session_id) & (Read.owner_user_id == owner)).where(
                Message.msg_type.in_(VISIBLE_TYPES)
            ).group_by(Message.session_id).subquery()
            rows = (await db.execute(select(Catalog, watermarks).join(
                watermarks, Catalog.session_id == watermarks.c.session_id
            ).where(*self._scope(user, modes)).order_by(
                watermarks.c.last_message_at.desc(), Catalog.session_id
            ).limit(limit).offset(offset))).all()
            return [{
                "session_id": row[0].session_id, "mode": row[0].mode,
                "title": row[0].title or "新对话", "source": "web",
                "read_only_on_web": False,
                "updated_at": row.last_message_at,
                "unread_count": int(row.unread_count or 0),
                "last_sequence": row.last_sequence, "revision": row.revision,
            } for row in rows]

    async def snapshot(self, user, session_id, *, revision=None, limit=100):
        from app.db.session_repository import SessionRepository

        async with self.session_factory() as db:
            await self._require(db, user, session_id)
            # The same parent-row lock is used by foreground and background appenders.
            session = (await db.execute(select(SessionDB).where(
                SessionDB.session_id == session_id
            ).with_for_update())).scalar_one_or_none()
            pending = (session.session_metadata or {}).get("pending_interaction") if session else None
            current = (await db.execute(select(func.max(Message.id)).where(
                Message.session_id == session_id
            ))).scalar_one() or 0
            if revision is not None and revision == current:
                return {"session_id": session_id, "revision": current, "unchanged": True,
                        "pending_interaction": pending}
            rows = (await db.execute(select(Message).where(
                Message.session_id == session_id
            ).order_by(Message.sequence_number.desc(), Message.id.desc()).limit(limit))).scalars().all()
            # Reuse the canonical serializer; no lossy text or attachment projection.
            messages = [SessionRepository._message_row_to_context_dict(row) for row in reversed(rows)]
            return {
                "session_id": session_id, "revision": current, "messages": messages,
                "pending_interaction": pending,
                "through_sequence": rows[0].sequence_number if rows else -1,
                "oldest_sequence": rows[-1].sequence_number if rows else None,
                "has_more": bool(rows and rows[-1].sequence_number > 0),
            }

    async def mark_read(self, user, session_id, through_sequence):
        owner = primary_owner_id(user.id)
        async with self.session_factory() as db:
            await self._require(db, user, session_id)
            # Serialize creation and advancement; never acknowledge unseen future rows.
            await db.execute(update(SessionDB).where(SessionDB.session_id == session_id).values(
                updated_at=SessionDB.updated_at
            ))
            last = (await db.execute(select(func.max(Message.sequence_number)).where(
                Message.session_id == session_id
            ))).scalar_one()
            through = min(through_sequence, last if last is not None else -1)
            row = await db.get(Read, (session_id, owner))
            if row is None:
                db.add(Read(session_id=session_id, owner_user_id=owner, through_sequence=through))
            elif through > row.through_sequence:
                row.through_sequence = through
                row.updated_at = datetime.utcnow()
            await db.commit()
        return {"session_id": session_id, "through_sequence": through}
