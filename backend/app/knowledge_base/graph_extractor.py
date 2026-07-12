"""Adapter from cognition graph providers to per-chunk KB extraction."""

from __future__ import annotations

import hashlib

import structlog

from app.knowledge_base.graph_extraction.models import GraphDocumentChunk, GraphExtractionSchema
from app.knowledge_base.graph_schemas import (
    ChunkGraphExtraction,
    ExtractedEntity,
    ExtractedEvidence,
    ExtractedRelation,
)

logger = structlog.get_logger()


class KnowledgeGraphExtractor:
    """Extract an independently retryable graph fragment from one chunk."""

    def __init__(self, provider=None):
        if provider is None:
            from app.knowledge_base.graph_extraction.llm_factory import create_llamaindex_llm
            from app.knowledge_base.graph_extraction.provider_factory import (
                create_extractor_provider,
            )

            provider = create_extractor_provider(
                "llamaindex",
                llm=create_llamaindex_llm("project"),
            )
        self.provider = provider

    async def extract_chunk(
        self,
        *,
        kb_id: str,
        chunk,
        schema: GraphExtractionSchema,
    ) -> ChunkGraphExtraction:
        source_namespace = f"{kb_id}:{chunk.id}"
        graph_chunk = GraphDocumentChunk(
            chunk_id=chunk.id,
            knowledge_base_id=kb_id,
            source_file_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            text=chunk.content,
            location=self._location(chunk),
            metadata=dict(chunk.chunk_metadata or {}),
        )
        extraction = await self.provider.extract(
            [graph_chunk],
            schema,
            source_namespace=source_namespace,
        )

        entity_id_map = {
            entity.entity_id: self._local_id(source_namespace, entity.entity_id)
            for entity in extraction.candidate_entities
        }
        evidence_by_id = {item.evidence_id: item for item in extraction.evidence}
        entities = [
            ExtractedEntity(
                local_id=entity_id_map[entity.entity_id],
                entity_type=entity.entity_type,
                name=entity.name,
                canonical_name=entity.canonical_name,
                aliases=list(entity.aliases),
                description=entity.description,
                attributes=dict(entity.attributes),
                evidence_text=self._evidence_text(
                    entity.source_evidence_ids, evidence_by_id, chunk.content, entity.name
                ),
                evidence=self._exact_evidence(
                    entity.source_evidence_ids, evidence_by_id, chunk.content, entity.name
                ),
            )
            for entity in extraction.candidate_entities
        ]

        relations = []
        for relation in extraction.candidate_relations:
            source_local_id = entity_id_map.get(relation.source_entity_id)
            target_local_id = entity_id_map.get(relation.target_entity_id)
            if source_local_id is None or target_local_id is None:
                logger.warning(
                    "knowledge_graph_relation_endpoint_missing",
                    chunk_id=chunk.id,
                    relation_id=relation.relation_id,
                    source_entity_id=relation.source_entity_id,
                    target_entity_id=relation.target_entity_id,
                )
                continue
            relations.append(
                ExtractedRelation(
                    source_local_id=source_local_id,
                    target_local_id=target_local_id,
                    relation_type=relation.relation_type,
                    description=relation.description,
                    attributes=dict(relation.attributes),
                    evidence_text=self._evidence_text(
                        relation.source_evidence_ids, evidence_by_id, chunk.content
                    ),
                    evidence=self._exact_evidence(
                        relation.source_evidence_ids, evidence_by_id, chunk.content
                    ),
                )
            )

        return ChunkGraphExtraction(
            chunk_id=chunk.id,
            extractor_name=str(
                getattr(self.provider, "provider_name", self.provider.__class__.__name__)
            ),
            entities=entities,
            relations=relations,
        )

    @staticmethod
    def _local_id(source_namespace: str, entity_id: str) -> str:
        digest = hashlib.sha1(
            f"{source_namespace}|{entity_id}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:16]
        return f"local_{digest}"

    @staticmethod
    def _location(chunk) -> str:
        parts = []
        if chunk.page_number is not None:
            parts.append(f"page:{chunk.page_number}")
        if chunk.section_path:
            parts.append("section:" + "/".join(chunk.section_path))
        return ";".join(parts) or f"chunk:{chunk.chunk_index}"

    @staticmethod
    def _evidence_text(evidence_ids, evidence_by_id, chunk_text: str, fallback: str = "") -> str:
        for evidence_id in evidence_ids or []:
            evidence = evidence_by_id.get(evidence_id)
            quote = str(getattr(evidence, "quote", "") or "")
            if quote and quote in chunk_text:
                return quote
        if fallback and fallback in chunk_text:
            return fallback
        return chunk_text

    @classmethod
    def _exact_evidence(cls, evidence_ids, evidence_by_id, chunk_text: str, fallback: str = ""):
        quote = cls._evidence_text(evidence_ids, evidence_by_id, chunk_text, fallback)
        evidence = ExtractedEvidence(quote=quote)
        try:
            return evidence.validate_against(chunk_text)
        except ValueError:
            return None
