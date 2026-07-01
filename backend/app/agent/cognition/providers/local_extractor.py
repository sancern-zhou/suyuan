from __future__ import annotations

import asyncio
import hashlib

from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveSchema,
    DocumentChunk,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
    SourceFile,
)
from app.agent.cognition.providers.text_parser import TextParserProvider


class LocalRuleBasedExtractorProvider:
    """Deterministic fallback extractor for spike tests and offline operation."""

    provider_name = "local_rule_based"

    TERM_CATALOG: dict[str, tuple[str, list[str]]] = {
        "深圳市": ("Region", ["深圳"]),
        "臭氧": ("Pollutant", ["O3", "O₃"]),
        "O3": ("Pollutant", ["臭氧", "O₃"]),
        "PM2.5": ("Pollutant", ["PM25", "细颗粒物"]),
        "监测站": ("Station", []),
        "光化学反应": ("ProcessMechanism", []),
        "机动车排放": ("EmissionSource", []),
        "本地生成假设": ("Hypothesis", []),
    }

    async def extract(
        self,
        chunks: list[DocumentChunk],
        schema: CognitiveSchema,
    ) -> ExtractionResult:
        map_id = chunks[0].map_id if chunks else "unknown"
        evidence_by_chunk: dict[str, Evidence] = {}
        entities_by_key: dict[tuple[str, str], CandidateEntity] = {}

        for chunk in chunks:
            for term, (entity_type, aliases) in self.TERM_CATALOG.items():
                if entity_type not in schema.allowed_entity_types or term not in chunk.text:
                    continue

                evidence = evidence_by_chunk.setdefault(
                    chunk.chunk_id,
                    Evidence(
                        evidence_id=self._stable_id("ev", chunk.map_id, chunk.chunk_id),
                        map_id=chunk.map_id,
                        source_file_id=chunk.source_file_id,
                        chunk_id=chunk.chunk_id,
                        location=chunk.location,
                        text_span=chunk.text,
                        normalized_summary=chunk.text[:160],
                    ),
                )

                name = "臭氧" if term in {"O3", "O₃"} else term
                key = (entity_type, name)
                if key not in entities_by_key:
                    entities_by_key[key] = CandidateEntity(
                        entity_id=self._stable_id("ent", chunk.map_id, entity_type, name),
                        map_id=chunk.map_id,
                        entity_type=entity_type,
                        name=name,
                        canonical_name=name,
                        aliases=aliases,
                        source_evidence_ids=[evidence.evidence_id],
                    )
                elif evidence.evidence_id not in entities_by_key[key].source_evidence_ids:
                    entities_by_key[key].source_evidence_ids.append(evidence.evidence_id)

        relations = self._build_relations(
            map_id=map_id,
            entities=list(entities_by_key.values()),
            evidence=list(evidence_by_chunk.values()),
            schema=schema,
        )
        return ExtractionResult(
            map_id=map_id,
            candidate_entities=list(entities_by_key.values()),
            candidate_relations=relations,
            evidence=list(evidence_by_chunk.values()),
            diagnostics=ExtractionDiagnostic(provider_name=self.provider_name),
        )

    def extract_sync_from_text(
        self,
        text: str,
        schema: CognitiveSchema,
        map_id: str,
        file_id: str,
    ) -> ExtractionResult:
        async def _run() -> ExtractionResult:
            source_file = SourceFile(
                file_id=file_id,
                map_id=map_id,
                filename=f"{file_id}.txt",
                content_type="text/plain",
                storage_path=f"/tmp/{file_id}.txt",
            )
            chunks = await TextParserProvider(max_chars=1000).parse_text(source_file, text)
            return await self.extract(chunks, schema)

        return asyncio.run(_run())

    def _build_relations(
        self,
        map_id: str,
        entities: list[CandidateEntity],
        evidence: list[Evidence],
        schema: CognitiveSchema,
    ) -> list[CandidateRelation]:
        by_type = {(entity.entity_type, entity.name): entity for entity in entities}
        relations: list[CandidateRelation] = []

        def add(source_key: tuple[str, str], relation_type: str, target_key: tuple[str, str]) -> None:
            if relation_type not in schema.allowed_relation_types:
                return
            source = by_type.get(source_key)
            target = by_type.get(target_key)
            if not source or not target:
                return
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
                    description=f"{source.name} {relation_type} {target.name}",
                    source_evidence_ids=[item.evidence_id for item in evidence],
                )
            )

        add(("ProcessMechanism", "光化学反应"), "affects", ("Pollutant", "臭氧"))
        add(("Station", "监测站"), "measures", ("Pollutant", "臭氧"))
        add(("EmissionSource", "机动车排放"), "supports", ("Hypothesis", "本地生成假设"))
        return relations

    def _stable_id(self, prefix: str, *parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"
