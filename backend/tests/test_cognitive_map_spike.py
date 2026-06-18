from pathlib import Path

import pytest

from app.agent.cognition.models import (
    CognitiveMapQuery,
    CognitiveSchema,
    SourceFile,
)
from app.agent.cognition.providers.local_extractor import LocalRuleBasedExtractorProvider
from app.agent.cognition.providers.text_parser import TextParserProvider
from app.agent.cognition.spike_pipeline import run_local_spike
from app.agent.cognition.view_builder import CognitiveMapViewBuilder


@pytest.mark.asyncio
async def test_text_parser_chunks_plain_text_with_source_locations(tmp_path: Path):
    source_path = tmp_path / "ozone_notes.txt"
    source_path.write_text(
        "深圳市臭氧污染过程分析\n\n"
        "臭氧受光化学反应影响。深圳市监测站用于观测O3浓度。\n",
        encoding="utf-8",
    )
    source_file = SourceFile(
        file_id="file_1",
        map_id="map_1",
        filename=source_path.name,
        content_type="text/plain",
        storage_path=str(source_path),
    )

    chunks = await TextParserProvider(max_chars=30).parse(source_file)

    assert len(chunks) >= 2
    assert chunks[0].chunk_id == "file_1:chunk:0"
    assert chunks[0].source_file_id == "file_1"
    assert chunks[0].location == "paragraph 1"
    assert "深圳市臭氧污染过程分析" in chunks[0].text


@pytest.mark.asyncio
async def test_local_extractor_maps_schema_terms_to_candidates_with_evidence():
    schema = CognitiveSchema.default_air_quality_schema()
    source_file = SourceFile(
        file_id="file_1",
        map_id="map_1",
        filename="notes.txt",
        content_type="text/plain",
        storage_path="/tmp/notes.txt",
    )
    chunks = await TextParserProvider(max_chars=500).parse_text(
        source_file=source_file,
        text="深圳市监测站监测臭氧。臭氧受光化学反应影响，机动车排放支持本地生成假设。",
    )

    result = await LocalRuleBasedExtractorProvider().extract(
        chunks=chunks,
        schema=schema,
    )

    entity_pairs = {(entity.entity_type, entity.name) for entity in result.candidate_entities}
    relation_types = {relation.relation_type for relation in result.candidate_relations}

    assert ("Region", "深圳市") in entity_pairs
    assert ("Pollutant", "臭氧") in entity_pairs
    assert ("ProcessMechanism", "光化学反应") in entity_pairs
    assert "affects" in relation_types
    assert result.evidence
    assert all(entity.source_evidence_ids for entity in result.candidate_entities)
    assert result.diagnostics.provider_name == "local_rule_based"


def test_view_builder_returns_agent_prompt_summary_with_evidence_refs():
    schema = CognitiveSchema.default_air_quality_schema()
    extraction = LocalRuleBasedExtractorProvider().extract_sync_from_text(
        text="臭氧受光化学反应影响，机动车排放支持本地生成假设。",
        schema=schema,
        map_id="map_1",
        file_id="file_1",
    )
    query = CognitiveMapQuery(
        task="分析臭氧污染过程",
        agent_mode="expert",
        agent_role="chemistry",
        map_ids=["map_1"],
        entity_hints=["臭氧"],
    )

    view = CognitiveMapViewBuilder().build_from_extraction(query, extraction)

    assert view.agent_mode == "expert"
    assert any(entity.name == "臭氧" for entity in view.entities)
    assert view.evidence_summaries
    assert "## 当前认知地图" in view.prompt_summary
    assert "map_evidence:" in view.prompt_summary


@pytest.mark.asyncio
async def test_local_spike_pipeline_writes_extraction_and_view_json(tmp_path: Path):
    source_path = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    source_path.write_text(
        "深圳市监测站监测臭氧。臭氧受光化学反应影响。",
        encoding="utf-8",
    )

    result = await run_local_spike(
        source_path=source_path,
        output_dir=output_dir,
        task="分析臭氧污染过程",
        entity_hints=["臭氧"],
    )

    assert result.extraction_path.exists()
    assert result.view_path.exists()
    assert result.extraction.candidate_entities
    assert result.view.prompt_summary
    assert "臭氧" in result.view_path.read_text(encoding="utf-8")
