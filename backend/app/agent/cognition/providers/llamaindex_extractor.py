from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveSchema,
    DocumentChunk,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
)


@dataclass(frozen=True)
class LlamaIndexSchemaComponents:
    possible_entities: type[Any]
    possible_relations: type[Any]
    validation_schema: list[tuple[str, str, str]]


class LlamaIndexPropertyGraphExtractorProvider:
    """Optional LlamaIndex Property Graph adapter placeholder.

    This provider intentionally exposes the project-level contract first. The
    concrete LlamaIndex wiring can evolve without changing callers.
    """

    provider_name = "llamaindex_property_graph"

    def __init__(self, llm: Any | None = None, max_triplets_per_chunk: int = 10) -> None:
        self.llm = llm
        self.max_triplets_per_chunk = max_triplets_per_chunk

    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
    ) -> ExtractionResult:
        try:
            from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
            from llama_index.core.indices.property_graph.transformations.schema_llm import (
                KG_NODES_KEY,
                KG_RELATIONS_KEY,
            )
            from llama_index.core.schema import TextNode
        except ImportError as exc:
            raise RuntimeError(
                "LlamaIndexPropertyGraphExtractorProvider requires optional "
                "'llama-index' packages. Use LocalRuleBasedExtractorProvider "
                "for offline Spike runs."
            ) from exc

        if self.llm is None:
            raise RuntimeError(
                "LlamaIndexPropertyGraphExtractorProvider requires an LLM instance. "
                "Configure one before selecting extractor_provider='llamaindex'."
            )

        components = self.build_schema_components(schema)
        extractor = SchemaLLMPathExtractor(
            llm=self.llm,
            possible_entities=components.possible_entities,
            possible_relations=components.possible_relations,
            kg_validation_schema=components.validation_schema,
            strict=True,
            max_triplets_per_chunk=self.max_triplets_per_chunk,
        )
        nodes = [
            TextNode(
                text=chunk.text,
                metadata={
                    "map_id": chunk.map_id,
                    "source_file_id": chunk.source_file_id,
                    "chunk_id": chunk.chunk_id,
                    "location": chunk.location,
                    "text_span": chunk.text,
                },
            )
            for chunk in chunks
        ]
        extracted_nodes = await extractor.acall(nodes)

        payload: dict[str, list[dict[str, Any]]] = {"entities": [], "relations": []}
        evidence_by_id: dict[str, dict[str, Any]] = {}
        for node in extracted_nodes:
            metadata = node.metadata or {}
            chunk_id = str(metadata.get("chunk_id") or node.id_)
            evidence_id = self._stable_id("ev", str(metadata.get("map_id", "unknown")), chunk_id)
            evidence_by_id[evidence_id] = {
                "source_file_id": metadata.get("source_file_id", "unknown"),
                "chunk_id": chunk_id,
                "location": metadata.get("location", "unknown"),
                "text_span": metadata.get("text_span") or node.get_content(),
            }
            for kg_node in metadata.get(KG_NODES_KEY, []):
                payload["entities"].append(
                    {
                        "name": getattr(kg_node, "name", None)
                        or getattr(kg_node, "id", None)
                        or str(kg_node),
                        "type": getattr(kg_node, "label", None)
                        or getattr(kg_node, "type", None)
                        or "Entity",
                        "attributes": getattr(kg_node, "properties", {}) or {},
                        "evidence_id": evidence_id,
                    }
                )
            for kg_relation in metadata.get(KG_RELATIONS_KEY, []):
                payload["relations"].append(
                    {
                        "source": getattr(kg_relation, "source_id", None)
                        or getattr(kg_relation, "source", None),
                        "target": getattr(kg_relation, "target_id", None)
                        or getattr(kg_relation, "target", None),
                        "type": getattr(kg_relation, "label", None)
                        or getattr(kg_relation, "type", None)
                        or getattr(kg_relation, "name", None),
                        "source_type": getattr(kg_relation, "source_type", "Entity"),
                        "target_type": getattr(kg_relation, "target_type", "Entity"),
                        "attributes": getattr(kg_relation, "properties", {}) or {},
                        "evidence_id": evidence_id,
                    }
                )

        map_id = chunks[0].map_id if chunks else "unknown"
        return self.map_payload_to_extraction(
            map_id=map_id,
            payload=payload,
            evidence_by_id=evidence_by_id,
            diagnostic=ExtractionDiagnostic(
                provider_name=self.provider_name,
                provider_version="llama-index-core",
            ),
        )

    def build_schema_components(self, schema: CognitiveSchema) -> LlamaIndexSchemaComponents:
        entity_values = tuple(schema.allowed_entity_types or ["Entity"])
        relation_values = tuple(schema.allowed_relation_types or ["related_to"])
        possible_entities = Literal.__getitem__(entity_values)
        possible_relations = Literal.__getitem__(relation_values)
        return LlamaIndexSchemaComponents(
            possible_entities=possible_entities,
            possible_relations=possible_relations,
            validation_schema=list(schema.allowed_relation_triplets),
        )

    def map_payload_to_extraction(
        self,
        map_id: str,
        payload: dict[str, Any],
        evidence_by_id: dict[str, dict[str, Any]],
        diagnostic: ExtractionDiagnostic | None = None,
    ) -> ExtractionResult:
        evidence = [
            Evidence(
                evidence_id=evidence_id,
                map_id=map_id,
                source_file_id=data["source_file_id"],
                chunk_id=data["chunk_id"],
                location=data["location"],
                text_span=data["text_span"],
                normalized_summary=data.get("normalized_summary") or data["text_span"][:160],
                confidence=float(data.get("confidence", 0.7)),
            )
            for evidence_id, data in evidence_by_id.items()
        ]

        entities: dict[tuple[str, str], CandidateEntity] = {}
        for item in payload.get("entities", []):
            entity_type = str(item.get("type") or item.get("entity_type") or "Entity")
            name = str(item.get("name") or item.get("label") or "").strip()
            if not name:
                continue
            evidence_id = item.get("evidence_id")
            source_evidence_ids = [evidence_id] if evidence_id else []
            key = (entity_type, name)
            entities[key] = CandidateEntity(
                entity_id=self._stable_id("ent", map_id, entity_type, name),
                map_id=map_id,
                entity_type=entity_type,
                name=name,
                canonical_name=item.get("canonical_name") or name,
                aliases=list(item.get("aliases") or []),
                description=item.get("description"),
                attributes=dict(item.get("attributes") or {}),
                source_evidence_ids=source_evidence_ids,
                confidence=float(item.get("confidence", 0.7)),
            )

        relations: list[CandidateRelation] = []
        for item in payload.get("relations", []):
            relation_type = str(item.get("type") or item.get("relation_type") or "").strip()
            source_name = str(item.get("source") or "").strip()
            target_name = str(item.get("target") or "").strip()
            source_type = str(item.get("source_type") or "Entity")
            target_type = str(item.get("target_type") or "Entity")
            if not relation_type or not source_name or not target_name:
                continue

            source = entities.get((source_type, source_name)) or self._find_entity_by_name(
                entities,
                source_name,
            )
            target = entities.get((target_type, target_name)) or self._find_entity_by_name(
                entities,
                target_name,
            )
            if not source or not target:
                continue

            evidence_id = item.get("evidence_id")
            source_evidence_ids = [evidence_id] if evidence_id else []
            relations.append(
                CandidateRelation(
                    relation_id=self._stable_id(
                        "rel",
                        map_id,
                        source.entity_id,
                        relation_type,
                        target.entity_id,
                    ),
                    map_id=map_id,
                    source_entity_id=source.entity_id,
                    target_entity_id=target.entity_id,
                    relation_type=relation_type,
                    description=item.get("description"),
                    attributes=dict(item.get("attributes") or {}),
                    source_evidence_ids=source_evidence_ids,
                    confidence=float(item.get("confidence", 0.7)),
                )
            )

        return ExtractionResult(
            map_id=map_id,
            candidate_entities=list(entities.values()),
            candidate_relations=relations,
            evidence=evidence,
            diagnostics=diagnostic or ExtractionDiagnostic(provider_name=self.provider_name),
        )

    def _find_entity_by_name(
        self,
        entities: dict[tuple[str, str], CandidateEntity],
        name: str,
    ) -> CandidateEntity | None:
        for (_, entity_name), entity in entities.items():
            if entity_name == name:
                return entity
        return None

    def _stable_id(self, prefix: str, *parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"
