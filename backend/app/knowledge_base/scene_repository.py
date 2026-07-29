"""Transactional persistence for scene discovery and confirmation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.graph_extraction.models import GraphExtractionSchema
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeSceneProfile, KnowledgeSchemaSuggestion
from app.knowledge_base.scene_schemas import BusinessLogic, BusinessObject, SceneDraft


class RepresentativeDocumentRequired(ValueError):
    """Raised when scene discovery has no processed representative document."""


class SceneRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def require_representative_documents(self, kb_id: str) -> list[Document]:
        documents = list(
            (
                await self.session.scalars(
                    select(Document)
                    .where(
                        Document.knowledge_base_id == kb_id,
                        Document.status == DocumentStatus.COMPLETED,
                        Document.ingestion_status.in_(["completed", "partial"]),
                        Document.chunk_count > 0,
                    )
                    .order_by(Document.created_at, Document.id)
                )
            ).all()
        )
        if not documents:
            raise RepresentativeDocumentRequired("representative_document_required")
        return documents

    async def begin_discovery(self, kb_id: str, created_by: str) -> KnowledgeBase:
        del created_by
        await self.require_representative_documents(kb_id)
        kb = await self.session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id).with_for_update()
        )
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        kb.scene_status = "discovering"
        await self.session.commit()
        return kb

    async def create_draft(
        self,
        kb_id: str,
        draft: SceneDraft,
        created_by: str,
    ) -> KnowledgeSceneProfile:
        await self.require_representative_documents(kb_id)
        current_version = int(
            await self.session.scalar(
                select(func.max(KnowledgeSceneProfile.version)).where(
                    KnowledgeSceneProfile.kb_id == kb_id
                )
            )
            or 0
        )
        profile = KnowledgeSceneProfile(
            kb_id=kb_id,
            version=current_version + 1,
            scene_goal=draft.scene_goal,
            desired_questions=draft.desired_questions,
            business_objects=[item.model_dump(mode="json") for item in draft.business_objects],
            business_logic=[item.model_dump(mode="json") for item in draft.business_logic],
            ignored_content=draft.ignored_content,
            source_document_ids=draft.source_document_ids,
            discovery_diagnostics=draft.diagnostics,
            status="draft",
            created_by=created_by,
        )
        self.session.add(profile)
        kb = await self.session.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        kb.scene_status = "awaiting_confirmation"
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def get_current_profile(self, kb_id: str) -> KnowledgeSceneProfile | None:
        return await self.session.scalar(
            select(KnowledgeSceneProfile)
            .where(KnowledgeSceneProfile.kb_id == kb_id)
            .order_by(KnowledgeSceneProfile.version.desc())
        )

    async def confirm_profile(
        self,
        profile_id: str,
        schema: GraphExtractionSchema,
    ) -> KnowledgeSceneProfile:
        profile = await self.session.scalar(
            select(KnowledgeSceneProfile)
            .where(KnowledgeSceneProfile.id == profile_id)
            .with_for_update()
        )
        if profile is None:
            raise ValueError(f"Scene profile not found: {profile_id}")
        if profile.status != "draft":
            raise ValueError("stale_scene_profile")
        kb = await self.session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.id == profile.kb_id).with_for_update()
        )
        if kb is None:
            raise ValueError(f"Knowledge base not found: {profile.kb_id}")

        await self.session.execute(
            update(KnowledgeSceneProfile)
            .where(
                KnowledgeSceneProfile.kb_id == profile.kb_id,
                KnowledgeSceneProfile.status == "confirmed",
            )
            .values(status="archived")
        )
        kb.scene_profile_version = int(kb.scene_profile_version or 0) + 1
        kb.schema_version = int(kb.schema_version or 0) + 1
        schema.scene_profile_version = kb.scene_profile_version
        schema.schema_version = kb.schema_version
        kb.graph_schema = schema.model_dump(mode="json")
        kb.scene_status = "ready"
        kb.graph_updated_at = datetime.utcnow()
        profile.status = "confirmed"
        profile.confirmed_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def list_suggestions(
        self,
        kb_id: str,
        status: str = "pending",
    ) -> list[KnowledgeSchemaSuggestion]:
        return list(
            (
                await self.session.scalars(
                    select(KnowledgeSchemaSuggestion)
                    .where(
                        KnowledgeSchemaSuggestion.kb_id == kb_id,
                        KnowledgeSchemaSuggestion.status == status,
                    )
                    .order_by(KnowledgeSchemaSuggestion.created_at)
                )
            ).all()
        )

    async def accept_suggestion(
        self, kb_id: str, suggestion_id: str, created_by: str
    ) -> KnowledgeSceneProfile:
        suggestion = await self.session.scalar(
            select(KnowledgeSchemaSuggestion)
            .where(
                KnowledgeSchemaSuggestion.id == suggestion_id,
                KnowledgeSchemaSuggestion.kb_id == kb_id,
            )
            .with_for_update()
        )
        if suggestion is None or suggestion.status != "pending":
            raise ValueError("stale_schema_suggestion")
        current = await self.get_current_profile(kb_id)
        if current is None:
            raise ValueError("scene_profile_required")

        objects = [BusinessObject.model_validate(item) for item in current.business_objects or []]
        logic = [BusinessLogic.model_validate(item) for item in current.business_logic or []]
        if suggestion.suggestion_type == "business_object":
            candidate = BusinessObject.model_validate(suggestion.payload)
            objects = [item for item in objects if item.key != candidate.key]
            objects.append(candidate)
        elif suggestion.suggestion_type == "business_logic":
            candidate = BusinessLogic.model_validate(suggestion.payload)
            logic = [item for item in logic if item.key != candidate.key]
            logic.append(candidate)
        else:
            raise ValueError("unsupported_schema_suggestion")

        draft = SceneDraft(
            scene_goal=current.scene_goal,
            desired_questions=list(current.desired_questions or []),
            business_objects=objects,
            business_logic=logic,
            ignored_content=list(current.ignored_content or []),
            source_document_ids=list(current.source_document_ids or []),
            diagnostics={
                **dict(current.discovery_diagnostics or {}),
                "accepted_suggestion_id": suggestion.id,
            },
        )
        profile = await self.create_draft(kb_id, draft, created_by)
        suggestion.status = "accepted"
        await self.session.commit()
        return profile

    async def reject_suggestion(self, kb_id: str, suggestion_id: str) -> KnowledgeSchemaSuggestion:
        suggestion = await self.session.scalar(
            select(KnowledgeSchemaSuggestion)
            .where(
                KnowledgeSchemaSuggestion.id == suggestion_id,
                KnowledgeSchemaSuggestion.kb_id == kb_id,
            )
            .with_for_update()
        )
        if suggestion is None or suggestion.status != "pending":
            raise ValueError("stale_schema_suggestion")
        suggestion.status = "rejected"
        await self.session.commit()
        await self.session.refresh(suggestion)
        return suggestion
