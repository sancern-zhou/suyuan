"""Authorization and registration policy for conversation ownership."""

from fastapi import HTTPException

from app.auth.models import CurrentUser

from .schemas import ConversationCatalogRecord, ConversationSource


class ConversationCatalogService:
    def __init__(self, repository):
        self.repository = repository

    async def register(
        self,
        *,
        session_id: str,
        user: CurrentUser,
        source: ConversationSource,
        mode: str | None,
        title: str | None,
        read_only_on_web: bool = False,
    ) -> ConversationCatalogRecord:
        return await self.register_identity(
            session_id=session_id,
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            source=source,
            mode=mode,
            title=title,
            read_only_on_web=read_only_on_web,
        )

    async def register_identity(
        self,
        *,
        session_id: str,
        owner_user_id: str,
        owner_username: str,
        owner_display_name: str,
        source: ConversationSource,
        mode: str | None,
        title: str | None,
        read_only_on_web: bool = False,
    ) -> ConversationCatalogRecord:
        existing = await self.repository.get(session_id)
        if existing:
            if existing.owner_user_id != owner_user_id or existing.source != source:
                raise RuntimeError("catalog_identity_conflict")
            return existing
        return await self.repository.upsert(
            ConversationCatalogRecord(
                session_id=session_id,
                owner_user_id=owner_user_id,
                owner_username=owner_username,
                owner_display_name=owner_display_name,
                source=source,
                mode=mode,
                title=title,
                read_only_on_web=read_only_on_web,
            )
        )

    async def require_read(
        self, session_id: str, user: CurrentUser
    ) -> ConversationCatalogRecord:
        row = await self.repository.get(session_id)
        if row is None or (not user.is_admin and row.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="session_not_found")
        return row

    async def require_write(
        self, session_id: str, user: CurrentUser
    ) -> ConversationCatalogRecord:
        row = await self.require_read(session_id, user)
        if row.read_only_on_web:
            raise HTTPException(status_code=409, detail="social_session_read_only")
        return row

    async def list_visible(
        self, user: CurrentUser, *, limit: int, offset: int = 0
    ) -> list[ConversationCatalogRecord]:
        return await self.repository.list_visible(
            user_id=None if user.is_admin else user.id,
            limit=limit,
            offset=offset,
        )
