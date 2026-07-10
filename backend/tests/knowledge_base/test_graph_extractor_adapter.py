from types import SimpleNamespace

import pytest

from app.agent.cognition.models import (
    CandidateEntity,
    CandidateRelation,
    CognitiveSchema,
    Evidence,
    ExtractionDiagnostic,
    ExtractionResult,
)
from app.knowledge_base.graph_extractor import KnowledgeGraphExtractor


class _FakeProvider:
    provider_name = "fake_graph"

    def __init__(self):
        self.received = None

    async def extract(self, chunks, schema, *, source_namespace=None):
        self.received = (chunks, schema, source_namespace)
        return ExtractionResult(
            map_id=chunks[0].map_id,
            candidate_entities=[
                CandidateEntity(
                    entity_id="old-o3",
                    map_id=chunks[0].map_id,
                    entity_type="Pollutant",
                    name="臭氧",
                    canonical_name="O3",
                    source_evidence_ids=["ev-1"],
                ),
                CandidateEntity(
                    entity_id="old-light",
                    map_id=chunks[0].map_id,
                    entity_type="ProcessMechanism",
                    name="光化学反应",
                ),
            ],
            candidate_relations=[
                CandidateRelation(
                    relation_id="old-rel",
                    map_id=chunks[0].map_id,
                    source_entity_id="old-light",
                    target_entity_id="old-o3",
                    relation_type="affects",
                    source_evidence_ids=["ev-1"],
                )
            ],
            evidence=[
                Evidence(
                    evidence_id="ev-1",
                    map_id=chunks[0].map_id,
                    source_file_id=chunks[0].source_file_id,
                    chunk_id=chunks[0].chunk_id,
                    location=chunks[0].location,
                    text_span=chunks[0].text,
                    normalized_summary=chunks[0].text,
                )
            ],
            diagnostics=ExtractionDiagnostic(provider_name=self.provider_name),
        )


@pytest.mark.asyncio
async def test_extract_chunk_maps_local_ids_and_current_chunk_evidence():
    provider = _FakeProvider()
    adapter = KnowledgeGraphExtractor(provider=provider)
    chunk = SimpleNamespace(
        id="chunk-1",
        document_id="doc-1",
        chunk_index=2,
        content="臭氧受光化学反应影响。",
        page_number=3,
        section_path=["分析"],
        chunk_metadata={"source": "report.pdf"},
    )

    result = await adapter.extract_chunk(
        kb_id="kb1",
        chunk=chunk,
        schema=CognitiveSchema.default_air_quality_schema(),
    )

    assert result.chunk_id == chunk.id
    assert result.extractor_name == "fake_graph"
    assert result.entities[0].name == "臭氧"
    local_ids = {item.local_id for item in result.entities}
    assert result.relations[0].source_local_id in local_ids
    assert result.relations[0].target_local_id in local_ids
    assert result.entities[0].evidence_text == chunk.content
    assert result.relations[0].evidence_text == chunk.content
    assert "map_id" not in result.model_dump()

    provider_chunk = provider.received[0][0]
    assert provider_chunk.chunk_id == chunk.id
    assert provider_chunk.map_id == "kb1"
    assert provider.received[2] == "kb1:chunk-1"


@pytest.mark.asyncio
async def test_extract_chunk_drops_relation_with_missing_endpoint():
    provider = _FakeProvider()
    original_extract = provider.extract

    async def extract_with_dangling_relation(*args, **kwargs):
        result = await original_extract(*args, **kwargs)
        result.candidate_relations[0].source_entity_id = "missing"
        return result

    provider.extract = extract_with_dangling_relation
    adapter = KnowledgeGraphExtractor(provider=provider)
    chunk = SimpleNamespace(
        id="chunk-1",
        document_id="doc-1",
        chunk_index=0,
        content="证据",
        page_number=None,
        section_path=[],
        chunk_metadata={},
    )

    result = await adapter.extract_chunk(
        kb_id="kb1",
        chunk=chunk,
        schema=CognitiveSchema.default_air_quality_schema(),
    )

    assert result.relations == []
