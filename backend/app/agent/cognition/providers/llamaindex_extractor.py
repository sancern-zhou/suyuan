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
    possible_entity_props: list[str]
    possible_relation_props: list[str]
    validation_schema: list[tuple[str, str, str]]


class LlamaIndexPropertyGraphExtractorProvider:
    """Optional LlamaIndex Property Graph adapter placeholder.

    This provider intentionally exposes the project-level contract first. The
    concrete LlamaIndex wiring can evolve without changing callers.
    """

    provider_name = "llamaindex_property_graph"

    def __init__(
        self,
        llm: Any | None = None,
        max_triplets_per_chunk: int = 10,
        num_workers: int = 4,
    ) -> None:
        self.llm = llm
        self.max_triplets_per_chunk = max_triplets_per_chunk
        self.num_workers = num_workers
        self._entity_type_lookup: dict[str, str] = {}
        self._relation_type_lookup: dict[str, str] = {}

    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
        *,
        source_namespace: str | None = None,
    ) -> ExtractionResult:
        try:
            from llama_index.core import PropertyGraphIndex
            from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
            from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
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
        if hasattr(self.llm, "set_cognitive_schema"):
            self.llm.set_cognitive_schema(schema)

        components = self.build_schema_components(schema)
        extractor = SchemaLLMPathExtractor(
            llm=self.llm,
            possible_entities=components.possible_entities,
            possible_entity_props=components.possible_entity_props,
            possible_relations=components.possible_relations,
            possible_relation_props=components.possible_relation_props,
            kg_validation_schema=components.validation_schema,
            strict=True,
            max_triplets_per_chunk=self.max_triplets_per_chunk,
            num_workers=self.num_workers,
        )
        nodes = [
            TextNode(
                text=chunk.text,
                id_=chunk.chunk_id,
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
        map_id = chunks[0].map_id if chunks else "unknown"

        graph_store = SimplePropertyGraphStore()

        def _build_index() -> None:
            PropertyGraphIndex(
                nodes=nodes,
                llm=self.llm,
                kg_extractors=[extractor],
                property_graph_store=graph_store,
                embed_kg_nodes=False,
                use_async=True,
            )

        import asyncio

        await asyncio.to_thread(_build_index)
        if not self._store_triplets(graph_store):
            extracted_nodes = await extractor.acall(nodes)
            self._populate_store_from_extracted_nodes(graph_store, extracted_nodes)
        if not self._store_triplets(graph_store):
            self._populate_store_from_last_structured_payload(graph_store, chunks)
        self.last_property_graph_store = graph_store

        return self.map_property_graph_store_to_extraction(
            map_id=map_id,
            graph_store=graph_store,
            source_namespace=source_namespace,
            diagnostic=ExtractionDiagnostic(
                provider_name=self.provider_name,
                provider_version="llama-index-core",
            ),
        )

    def build_schema_components(self, schema: CognitiveSchema) -> LlamaIndexSchemaComponents:
        self._entity_type_lookup = {
            self._llamaindex_label(entity_type): entity_type
            for entity_type in (schema.allowed_entity_types or ["Entity"])
        }
        self._relation_type_lookup = {
            self._llamaindex_label(relation_type): relation_type
            for relation_type in (schema.allowed_relation_types or ["related_to"])
        }
        entity_values = tuple(self._entity_type_lookup)
        relation_values = tuple(self._relation_type_lookup)
        possible_entities = Literal.__getitem__(entity_values)
        possible_relations = Literal.__getitem__(relation_values)
        validation_schema = [
            (
                self._llamaindex_label(source),
                self._llamaindex_label(relation),
                self._llamaindex_label(target),
            )
            for source, relation, target in schema.allowed_relation_triplets
        ]
        if "has_alias" in (schema.allowed_relation_types or []):
            for entity_type in schema.allowed_entity_types or []:
                validation_schema.append((
                    self._llamaindex_label(entity_type),
                    self._llamaindex_label("has_alias"),
                    self._llamaindex_label(entity_type),
                ))
        return LlamaIndexSchemaComponents(
            possible_entities=possible_entities,
            possible_relations=possible_relations,
            possible_entity_props=["description"],
            possible_relation_props=["description"],
            validation_schema=list(dict.fromkeys(validation_schema)),
        )

    def map_payload_to_extraction(
        self,
        map_id: str,
        payload: dict[str, Any],
        evidence_by_id: dict[str, dict[str, Any]],
        diagnostic: ExtractionDiagnostic | None = None,
        source_namespace: str | None = None,
    ) -> ExtractionResult:
        identity_namespace = source_namespace or map_id
        enriched_evidence_by_id = {key: dict(value) for key, value in evidence_by_id.items()}

        entities: dict[tuple[str, str], CandidateEntity] = {}
        for item in payload.get("entities", []):
            entity_type = self._project_entity_type(
                str(item.get("type") or item.get("entity_type") or "Entity")
            )
            name = str(item.get("name") or item.get("label") or "").strip()
            if not name:
                continue
            key = (entity_type, name)
            entities[key] = CandidateEntity(
                entity_id=self._stable_id("ent", identity_namespace, entity_type, name),
                map_id=map_id,
                entity_type=entity_type,
                name=name,
                canonical_name=item.get("canonical_name") or name,
                aliases=list(item.get("aliases") or []),
                description=item.get("description"),
                source_evidence_ids=[str(item.get("evidence_id"))] if item.get("evidence_id") else [],
                attributes=dict(item.get("attributes") or {}),
            )

        relations: list[CandidateRelation] = []
        for item in payload.get("relations", []):
            relation_type = self._project_relation_type(
                str(item.get("type") or item.get("relation_type") or "").strip()
            )
            source_name = str(item.get("source") or "").strip()
            target_name = str(item.get("target") or "").strip()
            source_type = self._project_entity_type(str(item.get("source_type") or "Entity"))
            target_type = self._project_entity_type(str(item.get("target_type") or "Entity"))
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
            source_evidence_ids = [str(evidence_id)] if evidence_id else []
            if evidence_id and evidence_id in enriched_evidence_by_id:
                data = enriched_evidence_by_id[evidence_id]
                data["quote"] = item.get("evidence_quote") or data.get("quote")
                data["normalized_summary"] = (
                    item.get("evidence_summary")
                    or data.get("normalized_summary")
                    or data.get("quote")
                    or data["text_span"][:160]
                )
                data["support_type"] = item.get("support_type") or data.get("support_type") or "unknown"
                data["evidence_quality"] = (
                    "llm_relation_evidence"
                    if item.get("evidence_quote") or item.get("evidence_summary")
                    else data.get("evidence_quality") or "unknown"
                )
            relations.append(
                CandidateRelation(
                    relation_id=self._stable_id(
                        "rel",
                        identity_namespace,
                        source.entity_id,
                        relation_type,
                        target.entity_id,
                    ),
                    map_id=map_id,
                    source_entity_id=source.entity_id,
                    target_entity_id=target.entity_id,
                    relation_type=relation_type,
                    description=item.get("description"),
                    source_evidence_ids=source_evidence_ids,
                    attributes=dict(item.get("attributes") or {}),
                )
            )

        evidence = [
            Evidence(
                evidence_id=evidence_id,
                map_id=map_id,
                source_file_id=data["source_file_id"],
                chunk_id=data["chunk_id"],
                location=data["location"],
                text_span=data["text_span"],
                normalized_summary=data.get("normalized_summary") or data["text_span"][:160],
                quote=data.get("quote") or None,
                support_type=data.get("support_type") or "unknown",
                evidence_quality=data.get("evidence_quality") or "unknown",
            )
            for evidence_id, data in enriched_evidence_by_id.items()
        ]

        return ExtractionResult(
            map_id=map_id,
            candidate_entities=list(entities.values()),
            candidate_relations=relations,
            evidence=evidence,
            diagnostics=diagnostic or ExtractionDiagnostic(provider_name=self.provider_name),
        )

    def map_property_graph_store_to_extraction(
        self,
        map_id: str,
        graph_store: Any,
        diagnostic: ExtractionDiagnostic | None = None,
        source_namespace: str | None = None,
    ) -> ExtractionResult:
        from llama_index.core.graph_stores.types import TRIPLET_SOURCE_KEY

        identity_namespace = source_namespace or map_id

        evidence_by_source: dict[str, Evidence] = {}
        entities: dict[tuple[str, str], CandidateEntity] = {}
        relations: dict[tuple[str, str, str], CandidateRelation] = {}

        def evidence_for_properties(
            properties: dict[str, Any],
            evidence_key: str | None = None,
            fallback_summary: str | None = None,
        ) -> str | None:
            source_id = str(properties.get(TRIPLET_SOURCE_KEY) or properties.get("chunk_id") or "")
            if not source_id:
                return None
            key = evidence_key or source_id
            if key not in evidence_by_source:
                quote = str(properties.get("evidence_quote") or "").strip()
                relation_summary = str(properties.get("evidence_summary") or "").strip()
                is_fallback = not quote and not relation_summary and bool(fallback_summary)
                summary = str(
                    relation_summary
                    or quote
                    or fallback_summary
                    or properties.get("text_span")
                    or ""
                )[:240]
                evidence_by_source[key] = Evidence(
                    evidence_id=self._stable_id("ev", identity_namespace, key),
                    map_id=map_id,
                    source_file_id=str(properties.get("source_file_id") or "unknown"),
                    chunk_id=str(properties.get("chunk_id") or source_id),
                    location=str(properties.get("location") or "unknown"),
                    text_span=str(properties.get("text_span") or ""),
                    normalized_summary=summary,
                    quote=quote or None,
                    support_type=(
                        "fallback"
                        if is_fallback
                        else str(properties.get("support_type") or "unknown")
                    ),
                    evidence_quality=(
                        "missing_relation_evidence"
                        if is_fallback
                        else "llm_relation_evidence"
                        if quote or relation_summary
                        else "unknown"
                    ),
                )
            return evidence_by_source[key].evidence_id

        def entity_from_node(node: Any) -> CandidateEntity:
            entity_type = self._project_entity_type(str(getattr(node, "label", "Entity")))
            name = str(getattr(node, "name", None) or getattr(node, "id", None) or node).strip()
            key = (entity_type, name)
            properties = dict(getattr(node, "properties", {}) or {})
            if key not in entities:
                description = str(properties.get("description") or "").strip() or None
                entities[key] = CandidateEntity(
                    entity_id=self._stable_id("ent", identity_namespace, entity_type, name),
                    map_id=map_id,
                    entity_type=entity_type,
                    name=name,
                    canonical_name=name,
                    description=description,
                    attributes={},
                )
            return entities[key]

        for source_node, relation, target_node in self._store_triplets(graph_store):
            source = entity_from_node(source_node)
            target = entity_from_node(target_node)
            relation_type = self._project_relation_type(str(getattr(relation, "label", "")))
            if not relation_type or source.entity_id == target.entity_id:
                continue
            properties = dict(getattr(relation, "properties", {}) or {})
            relation_evidence_key = "|".join([
                str(properties.get(TRIPLET_SOURCE_KEY) or properties.get("chunk_id") or ""),
                source.name,
                relation_type,
                target.name,
            ])
            fallback_summary = f"{source.name} --{relation_type}--> {target.name}"
            relation_evidence_id = evidence_for_properties(
                properties,
                evidence_key=relation_evidence_key,
                fallback_summary=fallback_summary,
            )
            key = (source.entity_id, relation_type, target.entity_id)
            if key in relations:
                continue
            description = str(properties.get("description") or "").strip() or None
            relations[key] = CandidateRelation(
                relation_id=self._stable_id(
                    "rel",
                    identity_namespace,
                    source.entity_id,
                    relation_type,
                    target.entity_id,
                ),
                map_id=map_id,
                source_entity_id=source.entity_id,
                target_entity_id=target.entity_id,
                relation_type=relation_type,
                description=description,
                source_evidence_ids=[relation_evidence_id] if relation_evidence_id else [],
                attributes={},
            )

        return ExtractionResult(
            map_id=map_id,
            candidate_entities=list(entities.values()),
            candidate_relations=list(relations.values()),
            evidence=list(evidence_by_source.values()),
            diagnostics=diagnostic or ExtractionDiagnostic(provider_name=self.provider_name),
        )

    def _store_triplets(self, graph_store: Any) -> list[Any]:
        graph = getattr(graph_store, "graph", None)
        if graph is not None and hasattr(graph, "get_triplets"):
            return list(graph.get_triplets())
        try:
            return list(graph_store.get_triplets(ids=["__never_match__"]))
        except Exception:
            return []

    def _populate_store_from_extracted_nodes(self, graph_store: Any, nodes: list[Any]) -> None:
        from llama_index.core.graph_stores.types import (
            KG_NODES_KEY,
            KG_RELATIONS_KEY,
            TRIPLET_SOURCE_KEY,
        )

        kg_nodes = []
        kg_relations = []
        for node in nodes:
            metadata = dict(getattr(node, "metadata", {}) or {})
            node_id = str(getattr(node, "id_", "") or metadata.get("chunk_id") or "")
            node_kg_nodes = list(metadata.pop(KG_NODES_KEY, []) or [])
            node_kg_relations = list(metadata.pop(KG_RELATIONS_KEY, []) or [])
            for kg_node in node_kg_nodes:
                kg_node.properties[TRIPLET_SOURCE_KEY] = node_id
            for kg_relation in node_kg_relations:
                kg_relation.properties[TRIPLET_SOURCE_KEY] = node_id
            kg_nodes.extend(node_kg_nodes)
            kg_relations.extend(node_kg_relations)

        if kg_nodes:
            graph_store.upsert_nodes(kg_nodes)
        if kg_relations:
            graph_store.upsert_relations(kg_relations)

    def _populate_store_from_last_structured_payload(
        self,
        graph_store: Any,
        chunks: list[DocumentChunk],
    ) -> None:
        payload = getattr(self.llm, "last_structured_payload", None)
        if not isinstance(payload, dict) or not payload.get("triplets"):
            return

        from llama_index.core.graph_stores.types import EntityNode, Relation
        nodes_by_name: dict[str, EntityNode] = {}
        relations: list[Relation] = []
        for item in payload.get("triplets", []):
            subject = item.get("subject") or {}
            relation = item.get("relation") or {}
            obj = item.get("object") or {}
            source_name = str(subject.get("name") or "").strip()
            target_name = str(obj.get("name") or "").strip()
            relation_type = self._project_relation_type(str(relation.get("type") or ""))
            if not source_name or not target_name or not relation_type:
                continue
            if source_name == target_name:
                continue

            relation_properties = {"description": str(relation.get("description") or "").strip()}

            source_type = self._project_entity_type(str(subject.get("type") or "Entity"))
            target_type = self._project_entity_type(str(obj.get("type") or "Entity"))
            source_properties = {"description": str(subject.get("description") or "").strip()}
            target_properties = {"description": str(obj.get("description") or "").strip()}
            nodes_by_name[source_name] = EntityNode(
                name=source_name,
                label=source_type,
                properties=source_properties,
            )
            nodes_by_name[target_name] = EntityNode(
                name=target_name,
                label=target_type,
                properties=target_properties,
            )
            relations.append(
                Relation(
                    label=relation_type,
                    source_id=source_name,
                    target_id=target_name,
                    properties=relation_properties,
                )
            )

        if nodes_by_name:
            graph_store.upsert_nodes(list(nodes_by_name.values()))
        if relations:
            graph_store.upsert_relations(relations)

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

    def _llamaindex_label(self, value: str) -> str:
        return value.replace(" ", "_").upper()

    def _project_entity_type(self, value: str) -> str:
        return self._entity_type_lookup.get(self._llamaindex_label(value), value)

    def _project_relation_type(self, value: str) -> str:
        return self._relation_type_lookup.get(self._llamaindex_label(value), value.strip().lower())
