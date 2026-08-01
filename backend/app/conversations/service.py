"""Authorization and registration policy for conversation ownership."""

from datetime import datetime

from fastapi import HTTPException

from app.auth.models import CurrentUser

from .schemas import ConversationCatalogRecord, ConversationSource


class ConversationCatalogService:
    def __init__(self, repository, *, resource_service=None):
        self.repository = repository
        self.resource_service = resource_service

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
            clean_title = title.strip() if isinstance(title, str) else title
            if not (existing.title or "").strip() and clean_title:
                return await self.repository.upsert(
                    existing.model_copy(
                        update={
                            "mode": mode or existing.mode,
                            "title": clean_title,
                            "updated_at": datetime.utcnow(),
                        }
                    )
                )
            return existing
        stored = await self.repository.upsert(
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
        if stored.owner_user_id != owner_user_id or stored.source != source:
            raise RuntimeError("catalog_identity_conflict")
        return stored

    async def claim_web_draft(
        self,
        *,
        session_id: str,
        user: CurrentUser,
        mode: str | None,
    ) -> ConversationCatalogRecord:
        """Bind a pre-analysis upload session to its owner, or authorize it."""
        existing = await self.repository.get(session_id)
        if existing is not None:
            return await self.require_write(session_id, user)
        try:
            return await self.register(
                session_id=session_id,
                user=user,
                source=ConversationSource.WEB,
                mode=mode,
                title=None,
            )
        except RuntimeError as exc:
            if str(exc) == "catalog_identity_conflict":
                raise HTTPException(status_code=404, detail="session_not_found") from exc
            raise

    async def find(self, session_id: str) -> ConversationCatalogRecord | None:
        """Return a catalog record without applying visibility policy."""
        return await self.repository.get(session_id)

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

    async def delete(self, session_id: str) -> bool:
        catalog_deleted = await self.repository.delete(session_id)
        resources_deleted = False
        if self.resource_service is not None:
            resources_deleted = await self.resource_service.delete_session_resources(session_id)
        return bool(catalog_deleted or resources_deleted)
