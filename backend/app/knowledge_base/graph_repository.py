"""Repository for knowledge graph facts, provenance mentions, and traversal."""

from __future__ import annotations

import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.chunk_diff import normalize_chunk_text
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeGraphRelation,
    KnowledgeGraphRelationMention,
)
from app.knowledge_base.graph_schemas import ChunkGraphExtraction, ReviewStatus


@dataclass(frozen=True)
class GraphUpsertResult:
    entity_ids: list[str]
    relation_ids: list[str]
    changed_entity_ids: list[str]
    changed_relation_ids: list[str]


class KnowledgeGraphRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_chunk_extraction(
        self,
        *,
        kb_id: str,
        document_id: str,
        extraction: ChunkGraphExtraction,
        extraction_run_id: str,
    ) -> GraphUpsertResult:
        chunk = await self.session.get(KnowledgeChunk, extraction.chunk_id)
        if chunk is None or chunk.kb_id != kb_id or chunk.document_id != document_id:
            raise ValueError(f"Chunk not found in knowledge base document: {extraction.chunk_id}")

        entity_by_local_id: dict[str, KnowledgeGraphEntity] = {}
        changed_entity_ids: list[str] = []
        for extracted in extraction.entities:
            normalized_name = self.normalize_entity_name(extracted.canonical_name or extracted.name)
            entity = await self.session.scalar(
                select(KnowledgeGraphEntity).where(
                    KnowledgeGraphEntity.kb_id == kb_id,
                    KnowledgeGraphEntity.entity_type == extracted.entity_type,
                    KnowledgeGraphEntity.normalized_name == normalized_name,
                )
            )
            if entity is None:
                entity = KnowledgeGraphEntity(
                    kb_id=kb_id,
                    entity_type=extracted.entity_type,
                    name=extracted.name.strip(),
                    normalized_name=normalized_name,
                    canonical_name=extracted.canonical_name,
                    aliases=self._clean_aliases(extracted.aliases),
                    description=extracted.description,
                    attributes=dict(extracted.attributes),
                )
                self.session.add(entity)
                await self.session.flush()
            elif not entity.locked_by_user:
                entity.aliases = self._clean_aliases([*(entity.aliases or []), *extracted.aliases])
                if extracted.description and not entity.description:
                    entity.description = extracted.description
                entity.attributes = {
                    **(entity.attributes or {}),
                    **extracted.attributes,
                }

            entity_by_local_id[extracted.local_id] = entity
            await self._upsert_entity_mention(
                entity=entity,
                chunk=chunk,
                evidence_text=extracted.evidence_text,
                confidence=extracted.confidence,
                extractor_name=extraction.extractor_name,
                extraction_run_id=extraction_run_id,
            )
            changed_entity_ids.append(entity.id)

        relation_ids: list[str] = []
        changed_relation_ids: list[str] = []
        for extracted in extraction.relations:
            source = entity_by_local_id.get(extracted.source_local_id)
            target = entity_by_local_id.get(extracted.target_local_id)
            if source is None or target is None:
                continue
            relation_type = self.normalize_relation_type(extracted.relation_type)
            relation = await self.session.scalar(
                select(KnowledgeGraphRelation).where(
                    KnowledgeGraphRelation.kb_id == kb_id,
                    KnowledgeGraphRelation.source_entity_id == source.id,
                    KnowledgeGraphRelation.relation_type == relation_type,
                    KnowledgeGraphRelation.target_entity_id == target.id,
                )
            )
            if relation is None:
                relation = KnowledgeGraphRelation(
                    kb_id=kb_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    relation_type=relation_type,
                    description=extracted.description,
                    attributes=dict(extracted.attributes),
                )
                self.session.add(relation)
                await self.session.flush()
            elif not relation.locked_by_user:
                if extracted.description and not relation.description:
                    relation.description = extracted.description
                relation.attributes = {
                    **(relation.attributes or {}),
                    **extracted.attributes,
                }

            await self._upsert_relation_mention(
                relation=relation,
                chunk=chunk,
                evidence_text=extracted.evidence_text,
                confidence=extracted.confidence,
                extractor_name=extraction.extractor_name,
                extraction_run_id=extraction_run_id,
            )
            relation_ids.append(relation.id)
            changed_relation_ids.append(relation.id)

        await self.session.flush()
        await self._refresh_entity_counts(set(changed_entity_ids))
        await self._refresh_relation_counts(set(changed_relation_ids))
        return GraphUpsertResult(
            entity_ids=list(dict.fromkeys(entity.id for entity in entity_by_local_id.values())),
            relation_ids=list(dict.fromkeys(relation_ids)),
            changed_entity_ids=list(dict.fromkeys(changed_entity_ids)),
            changed_relation_ids=list(dict.fromkeys(changed_relation_ids)),
        )

    async def remove_chunk_contributions(
        self,
        *,
        kb_id: str,
        chunk_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        if not chunk_ids:
            return [], []

        entity_ids = set(
            (
                await self.session.execute(
                    select(KnowledgeGraphEntityMention.entity_id).where(
                        KnowledgeGraphEntityMention.kb_id == kb_id,
                        KnowledgeGraphEntityMention.chunk_id.in_(chunk_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        relation_ids = set(
            (
                await self.session.execute(
                    select(KnowledgeGraphRelationMention.relation_id).where(
                        KnowledgeGraphRelationMention.kb_id == kb_id,
                        KnowledgeGraphRelationMention.chunk_id.in_(chunk_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        await self.session.execute(
            delete(KnowledgeGraphRelationMention).where(
                KnowledgeGraphRelationMention.kb_id == kb_id,
                KnowledgeGraphRelationMention.chunk_id.in_(chunk_ids),
            )
        )
        await self.session.execute(
            delete(KnowledgeGraphEntityMention).where(
                KnowledgeGraphEntityMention.kb_id == kb_id,
                KnowledgeGraphEntityMention.chunk_id.in_(chunk_ids),
            )
        )
        await self.session.flush()

        deactivated_relation_ids: list[str] = []
        for relation_id in relation_ids:
            relation = await self.session.get(KnowledgeGraphRelation, relation_id)
            if relation is None:
                continue
            relation.mention_count = await self._relation_mention_count(relation_id)
            if relation.mention_count:
                continue
            deactivated_relation_ids.append(relation_id)
            if self._is_disposable(relation):
                await self.session.delete(relation)
            else:
                relation.review_status = "archived"
        await self.session.flush()

        deactivated_entity_ids: list[str] = []
        for entity_id in entity_ids:
            entity = await self.session.get(KnowledgeGraphEntity, entity_id)
            if entity is None:
                continue
            entity.mention_count = await self._entity_mention_count(entity_id)
            if entity.mention_count or await self._has_active_relations(kb_id, entity_id):
                continue
            deactivated_entity_ids.append(entity_id)
            if self._is_disposable(entity):
                await self.session.delete(entity)
            else:
                entity.review_status = "archived"

        await self.session.flush()
        return sorted(deactivated_entity_ids), sorted(deactivated_relation_ids)

    async def set_review_status(
        self,
        *,
        kb_id: str,
        kind: Literal["entity", "relation"],
        record_id: str,
        status: ReviewStatus,
    ) -> None:
        model = (
            KnowledgeGraphEntity
            if kind == "entity"
            else KnowledgeGraphRelation
            if kind == "relation"
            else None
        )
        if model is None:
            raise ValueError(f"Unsupported graph record kind: {kind}")
        record = await self.session.get(model, record_id)
        if record is None or record.kb_id != kb_id:
            raise ValueError(f"Graph {kind} not found: {record_id}")
        record.review_status = status

    async def merge_entities(
        self,
        *,
        kb_id: str,
        source_id: str,
        target_id: str,
    ) -> None:
        if source_id == target_id:
            raise ValueError("Source and target entities must differ")
        source = await self.session.get(KnowledgeGraphEntity, source_id)
        target = await self.session.get(KnowledgeGraphEntity, target_id)
        if source is None or target is None or source.kb_id != kb_id or target.kb_id != kb_id:
            raise ValueError("Merge entities must belong to the requested knowledge base")

        await self._move_entity_mentions(source_id, target_id)
        relations = list(
            (
                await self.session.execute(
                    select(KnowledgeGraphRelation).where(
                        KnowledgeGraphRelation.kb_id == kb_id,
                        or_(
                            KnowledgeGraphRelation.source_entity_id == source_id,
                            KnowledgeGraphRelation.target_entity_id == source_id,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for relation in relations:
            new_source_id = (
                target_id if relation.source_entity_id == source_id else relation.source_entity_id
            )
            new_target_id = (
                target_id if relation.target_entity_id == source_id else relation.target_entity_id
            )
            if new_source_id == new_target_id:
                await self.session.delete(relation)
                continue
            duplicate = await self.session.scalar(
                select(KnowledgeGraphRelation).where(
                    KnowledgeGraphRelation.kb_id == kb_id,
                    KnowledgeGraphRelation.source_entity_id == new_source_id,
                    KnowledgeGraphRelation.relation_type == relation.relation_type,
                    KnowledgeGraphRelation.target_entity_id == new_target_id,
                    KnowledgeGraphRelation.id != relation.id,
                )
            )
            if duplicate is not None:
                await self._move_relation_mentions(relation.id, duplicate.id)
                await self.session.delete(relation)
            else:
                relation.source_entity_id = new_source_id
                relation.target_entity_id = new_target_id

        target.aliases = self._clean_aliases(
            [*(target.aliases or []), source.name, *(source.aliases or [])]
        )
        target.mention_count = await self._entity_mention_count(target_id)
        source.review_status = "merged"
        source.merged_into_id = target_id
        source.mention_count = 0
        await self.session.flush()

    async def query_entities(
        self,
        *,
        kb_id: str,
        text: str | None,
        statuses: set[str],
        limit: int,
    ) -> list[KnowledgeGraphEntity]:
        result = await self.session.execute(
            select(KnowledgeGraphEntity)
            .where(
                KnowledgeGraphEntity.kb_id == kb_id,
                KnowledgeGraphEntity.review_status.in_(statuses),
            )
            .order_by(KnowledgeGraphEntity.name, KnowledgeGraphEntity.id)
        )
        entities = list(result.scalars().all())
        if text:
            needle = self.normalize_entity_name(text)
            entities = [
                entity
                for entity in entities
                if needle
                in {
                    entity.normalized_name,
                    self.normalize_entity_name(entity.name),
                    *(self.normalize_entity_name(alias) for alias in entity.aliases or []),
                }
            ]
        return entities[: max(1, limit)]

    async def traverse(
        self,
        *,
        kb_id: str,
        seed_entity_ids: list[str],
        statuses: set[str],
        depth: int,
        limit: int,
    ) -> tuple[list[KnowledgeGraphEntity], list[KnowledgeGraphRelation]]:
        depth = max(1, min(depth, 2))
        limit = max(1, limit)
        all_entities = list(
            (
                await self.session.execute(
                    select(KnowledgeGraphEntity).where(
                        KnowledgeGraphEntity.kb_id == kb_id,
                        KnowledgeGraphEntity.review_status.in_(statuses),
                    )
                )
            )
            .scalars()
            .all()
        )
        entity_by_id = {entity.id: entity for entity in all_entities}
        all_relations = list(
            (
                await self.session.execute(
                    select(KnowledgeGraphRelation).where(
                        KnowledgeGraphRelation.kb_id == kb_id,
                        KnowledgeGraphRelation.review_status.in_(statuses),
                    )
                )
            )
            .scalars()
            .all()
        )
        adjacency: dict[str, list[KnowledgeGraphRelation]] = {}
        for relation in all_relations:
            if (
                relation.source_entity_id not in entity_by_id
                or relation.target_entity_id not in entity_by_id
            ):
                continue
            adjacency.setdefault(relation.source_entity_id, []).append(relation)
            adjacency.setdefault(relation.target_entity_id, []).append(relation)

        visited = {entity_id for entity_id in seed_entity_ids if entity_id in entity_by_id}
        queue = deque((entity_id, 0) for entity_id in visited)
        relation_by_id: dict[str, KnowledgeGraphRelation] = {}
        while queue and len(visited) < limit:
            entity_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for relation in adjacency.get(entity_id, []):
                relation_by_id[relation.id] = relation
                other_id = (
                    relation.target_entity_id
                    if relation.source_entity_id == entity_id
                    else relation.source_entity_id
                )
                if other_id not in visited and len(visited) < limit:
                    visited.add(other_id)
                    queue.append((other_id, current_depth + 1))

        entities = [entity_by_id[entity_id] for entity_id in visited]
        relations = [
            relation
            for relation in relation_by_id.values()
            if relation.source_entity_id in visited and relation.target_entity_id in visited
        ]
        return entities, relations

    async def chunk_ids_for_graph_records(
        self,
        *,
        kb_id: str,
        entity_ids: list[str],
        relation_ids: list[str],
    ) -> list[str]:
        chunk_ids: set[str] = set()
        if entity_ids:
            chunk_ids.update(
                (
                    await self.session.execute(
                        select(KnowledgeGraphEntityMention.chunk_id).where(
                            KnowledgeGraphEntityMention.kb_id == kb_id,
                            KnowledgeGraphEntityMention.entity_id.in_(entity_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
        if relation_ids:
            chunk_ids.update(
                (
                    await self.session.execute(
                        select(KnowledgeGraphRelationMention.chunk_id).where(
                            KnowledgeGraphRelationMention.kb_id == kb_id,
                            KnowledgeGraphRelationMention.relation_id.in_(relation_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(chunk_ids)

    async def entity_ids_for_chunk_ids(
        self,
        *,
        kb_id: str,
        chunk_ids: list[str],
        statuses: set[str],
    ) -> list[str]:
        if not chunk_ids:
            return []
        result = await self.session.execute(
            select(KnowledgeGraphEntityMention.entity_id)
            .join(
                KnowledgeGraphEntity,
                KnowledgeGraphEntity.id == KnowledgeGraphEntityMention.entity_id,
            )
            .where(
                KnowledgeGraphEntityMention.kb_id == kb_id,
                KnowledgeGraphEntityMention.chunk_id.in_(chunk_ids),
                KnowledgeGraphEntity.review_status.in_(statuses),
            )
        )
        return list(dict.fromkeys(result.scalars().all()))

    async def get_relation(self, relation_id: str) -> KnowledgeGraphRelation | None:
        return await self.session.get(KnowledgeGraphRelation, relation_id)

    async def _upsert_entity_mention(
        self,
        *,
        entity: KnowledgeGraphEntity,
        chunk: KnowledgeChunk,
        evidence_text: str,
        confidence: float | None,
        extractor_name: str,
        extraction_run_id: str,
    ) -> None:
        mention = await self.session.scalar(
            select(KnowledgeGraphEntityMention).where(
                KnowledgeGraphEntityMention.entity_id == entity.id,
                KnowledgeGraphEntityMention.chunk_id == chunk.id,
            )
        )
        if mention is None:
            mention = KnowledgeGraphEntityMention(
                kb_id=chunk.kb_id,
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                entity_id=entity.id,
                extractor_name=extractor_name,
                extraction_run_id=extraction_run_id,
            )
            self.session.add(mention)
        mention.evidence_text = evidence_text
        mention.confidence = confidence

    async def _upsert_relation_mention(
        self,
        *,
        relation: KnowledgeGraphRelation,
        chunk: KnowledgeChunk,
        evidence_text: str,
        confidence: float | None,
        extractor_name: str,
        extraction_run_id: str,
    ) -> None:
        mention = await self.session.scalar(
            select(KnowledgeGraphRelationMention).where(
                KnowledgeGraphRelationMention.relation_id == relation.id,
                KnowledgeGraphRelationMention.chunk_id == chunk.id,
            )
        )
        if mention is None:
            mention = KnowledgeGraphRelationMention(
                kb_id=chunk.kb_id,
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                relation_id=relation.id,
                extractor_name=extractor_name,
                extraction_run_id=extraction_run_id,
            )
            self.session.add(mention)
        mention.evidence_text = evidence_text
        mention.confidence = confidence

    async def _move_entity_mentions(self, source_id: str, target_id: str) -> None:
        source_mentions = list(
            (
                await self.session.execute(
                    select(KnowledgeGraphEntityMention).where(
                        KnowledgeGraphEntityMention.entity_id == source_id
                    )
                )
            )
            .scalars()
            .all()
        )
        target_chunk_ids = set(
            (
                await self.session.execute(
                    select(KnowledgeGraphEntityMention.chunk_id).where(
                        KnowledgeGraphEntityMention.entity_id == target_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for mention in source_mentions:
            if mention.chunk_id in target_chunk_ids:
                await self.session.delete(mention)
            else:
                mention.entity_id = target_id
                target_chunk_ids.add(mention.chunk_id)

    async def _move_relation_mentions(self, source_id: str, target_id: str) -> None:
        source_mentions = list(
            (
                await self.session.execute(
                    select(KnowledgeGraphRelationMention).where(
                        KnowledgeGraphRelationMention.relation_id == source_id
                    )
                )
            )
            .scalars()
            .all()
        )
        target_chunk_ids = set(
            (
                await self.session.execute(
                    select(KnowledgeGraphRelationMention.chunk_id).where(
                        KnowledgeGraphRelationMention.relation_id == target_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for mention in source_mentions:
            if mention.chunk_id in target_chunk_ids:
                await self.session.delete(mention)
            else:
                mention.relation_id = target_id
                target_chunk_ids.add(mention.chunk_id)

    async def _refresh_entity_counts(self, entity_ids: set[str]) -> None:
        for entity_id in entity_ids:
            entity = await self.session.get(KnowledgeGraphEntity, entity_id)
            if entity is not None:
                entity.mention_count = await self._entity_mention_count(entity_id)

    async def _refresh_relation_counts(self, relation_ids: set[str]) -> None:
        for relation_id in relation_ids:
            relation = await self.session.get(KnowledgeGraphRelation, relation_id)
            if relation is not None:
                relation.mention_count = await self._relation_mention_count(relation_id)

    async def _entity_mention_count(self, entity_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(KnowledgeGraphEntityMention)
                .where(KnowledgeGraphEntityMention.entity_id == entity_id)
            )
            or 0
        )

    async def _relation_mention_count(self, relation_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(KnowledgeGraphRelationMention)
                .where(KnowledgeGraphRelationMention.relation_id == relation_id)
            )
            or 0
        )

    async def _has_active_relations(self, kb_id: str, entity_id: str) -> bool:
        count = await self.session.scalar(
            select(func.count())
            .select_from(KnowledgeGraphRelation)
            .where(
                KnowledgeGraphRelation.kb_id == kb_id,
                KnowledgeGraphRelation.review_status != "archived",
                or_(
                    KnowledgeGraphRelation.source_entity_id == entity_id,
                    KnowledgeGraphRelation.target_entity_id == entity_id,
                ),
            )
        )
        return bool(count)

    @staticmethod
    def _is_disposable(record: KnowledgeGraphEntity | KnowledgeGraphRelation) -> bool:
        return (
            record.created_by == "extractor"
            and not record.locked_by_user
            and record.review_status in {"candidate", "rejected"}
        )

    @staticmethod
    def normalize_entity_name(value: str) -> str:
        return normalize_chunk_text(unicodedata.normalize("NFKC", value)).casefold()

    @staticmethod
    def normalize_relation_type(value: str) -> str:
        return "_".join(normalize_chunk_text(value).casefold().split())

    @staticmethod
    def _clean_aliases(values: list[str]) -> list[str]:
        aliases: list[str] = []
        for value in values:
            cleaned = normalize_chunk_text(value)
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        return aliases
