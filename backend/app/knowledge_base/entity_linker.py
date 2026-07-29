"""Entity linking decisions for automatic extraction and user-entered facts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.graph_models import KnowledgeGraphEntity
from app.knowledge_base.graph_repository import KnowledgeGraphRepository


class EntityLinkCandidate(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    score: float = Field(ge=0, le=1)


class EntityLinkDecision(BaseModel):
    action: Literal["link", "create", "ambiguous"]
    entity_id: str | None = None
    canonical_name: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    candidates: list[EntityLinkCandidate] = Field(default_factory=list)


class EntityLinker:
    def __init__(self, session: AsyncSession, *, vector_candidates=None, comparer=None):
        self.session = session
        self.vector_candidates = vector_candidates
        self.comparer = comparer

    async def link(self, *, kb_id: str, entity_type: str, name: str) -> EntityLinkDecision:
        normalized = KnowledgeGraphRepository.normalize_entity_name(name)
        exact = list(
            (
                await self.session.scalars(
                    select(KnowledgeGraphEntity).where(
                        KnowledgeGraphEntity.kb_id == kb_id,
                        KnowledgeGraphEntity.normalized_name == normalized,
                    )
                )
            ).all()
        )
        typed_exact = [item for item in exact if item.entity_type == entity_type]
        if len(typed_exact) == 1:
            return self._linked(typed_exact[0], "exact_name", 1.0)
        if entity_type == "unknown" and len(exact) > 1:
            return self._ambiguous(name, exact, "same_name_multiple_types")

        rows = list(
            (
                await self.session.scalars(
                    select(KnowledgeGraphEntity).where(
                        KnowledgeGraphEntity.kb_id == kb_id,
                        KnowledgeGraphEntity.entity_type == entity_type,
                    )
                )
            ).all()
        )
        alias_key = normalized.casefold()
        alias_matches = [
            item
            for item in rows
            if any(
                KnowledgeGraphRepository.normalize_entity_name(str(alias)).casefold() == alias_key
                for alias in (item.aliases or [])
            )
        ]
        if len(alias_matches) == 1:
            return self._linked(alias_matches[0], "confirmed_alias", 1.0)
        if len(alias_matches) > 1:
            return self._ambiguous(name, alias_matches, "alias_matches_multiple_entities")

        if self.vector_candidates is not None:
            candidates = await self.vector_candidates(kb_id, entity_type, name)
            if candidates:
                top = candidates[0]
                gap = top.score - candidates[1].score if len(candidates) > 1 else top.score
                if top.score >= 0.90 and gap >= 0.08:
                    entity = await self.session.get(KnowledgeGraphEntity, top.entity_id)
                    if entity and entity.entity_type == entity_type:
                        return self._linked(entity, "vector_match", top.score)
                return EntityLinkDecision(
                    action="ambiguous",
                    canonical_name=name.strip(),
                    reason="vector_candidates_require_resolution",
                    confidence=top.score,
                    candidates=candidates,
                )

        return EntityLinkDecision(
            action="create",
            canonical_name=name.strip(),
            reason="no_matching_entity",
            confidence=1.0,
        )

    @staticmethod
    def _linked(entity: KnowledgeGraphEntity, reason: str, confidence: float) -> EntityLinkDecision:
        return EntityLinkDecision(
            action="link",
            entity_id=entity.id,
            canonical_name=entity.canonical_name or entity.name,
            reason=reason,
            confidence=confidence,
        )

    @staticmethod
    def _ambiguous(name: str, entities: list[KnowledgeGraphEntity], reason: str) -> EntityLinkDecision:
        return EntityLinkDecision(
            action="ambiguous",
            canonical_name=name.strip(),
            reason=reason,
            confidence=0.5,
            candidates=[
                EntityLinkCandidate(
                    entity_id=item.id,
                    entity_type=item.entity_type,
                    name=item.name,
                    score=1.0,
                )
                for item in entities
            ],
        )
