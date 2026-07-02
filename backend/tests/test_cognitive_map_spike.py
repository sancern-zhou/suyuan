from pathlib import Path
from typing import get_args

import pytest
from llama_index.core.llms import ChatMessage, CompletionResponse

from app.agent.cognition.models import (
    CognitiveMapQuery,
    CognitiveSchema,
    ExtractionDiagnostic,
    ExtractionResult,
    SourceFile,
)
from app.agent.cognition.evaluation import generate_evaluation_markdown
from app.agent.cognition.llm_factory import ProjectLLMAdapter, create_llamaindex_llm
from app.agent.cognition.provider_factory import create_extractor_provider, create_parser_provider
from app.agent.cognition.providers.llamaindex_extractor import (
    LlamaIndexPropertyGraphExtractorProvider,
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
async def test_text_parser_packs_short_paragraphs_to_reduce_llm_calls():
    source_file = SourceFile(
        file_id="file_1",
        map_id="map_1",
        filename="notes.txt",
        content_type="text/plain",
        storage_path="/tmp/notes.txt",
    )
    text = "\n\n".join(f"短段落{i}" for i in range(20))

    chunks = await TextParserProvider(max_chars=120).parse_text(
        source_file=source_file,
        text=text,
    )

    assert len(chunks) < 20
    assert all(len(chunk.text) <= 120 for chunk in chunks)
    assert chunks[0].location.startswith("paragraphs 1-")


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


@pytest.mark.asyncio
async def test_local_spike_pipeline_can_write_evaluation_markdown(tmp_path: Path):
    source_path = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    evaluation_path = tmp_path / "evaluation.md"
    source_path.write_text("臭氧受光化学反应影响。", encoding="utf-8")

    await run_local_spike(
        source_path=source_path,
        output_dir=output_dir,
        task="分析臭氧污染过程",
        entity_hints=["臭氧"],
        evaluation_output=evaluation_path,
    )

    assert evaluation_path.exists()
    assert "认知地图抽取评估" in evaluation_path.read_text(encoding="utf-8")


def test_provider_factory_selects_local_defaults():
    assert create_parser_provider("text").__class__.__name__ == "TextParserProvider"
    assert create_extractor_provider("local").__class__.__name__ == "LocalRuleBasedExtractorProvider"


def test_provider_factory_selects_optional_adapters_without_importing_dependencies():
    assert create_parser_provider("pdf").__class__.__name__ == "PdfParserProvider"
    assert create_parser_provider("markitdown").__class__.__name__ == "MarkItDownParserProvider"
    assert (
        create_extractor_provider("llamaindex").__class__.__name__
        == "LlamaIndexPropertyGraphExtractorProvider"
    )


def test_provider_factory_passes_llm_to_llamaindex_provider():
    llm = object()
    provider = create_extractor_provider("llamaindex", llm=llm)

    assert provider.llm is llm


def test_llamaindex_provider_defaults_to_parallel_extraction():
    provider = create_extractor_provider("llamaindex", llm=object())

    assert provider.num_workers == 4


def test_project_llm_prompt_includes_build_requirement():
    class DummyLLMService:
        async def chat(self, *args, **kwargs):
            return "{}"

    adapter = ProjectLLMAdapter(llm_service=DummyLLMService())
    schema = CognitiveSchema.default_air_quality_schema()
    schema.build_requirement = "用于运维故障诊断，优先抽取站点、设备、告警和工单之间的因果关系。"
    adapter.set_cognitive_schema(schema)

    prompt = adapter._build_structured_kg_prompt("测试文本", max_triplets=3)

    assert "本次认知地图构建需求" in prompt
    assert schema.build_requirement in prompt
    assert "优先保留与该需求相关" in prompt


def test_llamaindex_provider_maps_extraction_result_payload_to_project_models():
    provider = LlamaIndexPropertyGraphExtractorProvider()
    payload = {
        "entities": [
            {
                "name": "臭氧",
                "type": "Pollutant",
                "aliases": ["O3"],
                "evidence_id": "ev_1",
            },
            {
                "name": "光化学反应",
                "type": "ProcessMechanism",
                "evidence_id": "ev_1",
            },
        ],
        "relations": [
            {
                "source": "光化学反应",
                "source_type": "ProcessMechanism",
                "target": "臭氧",
                "target_type": "Pollutant",
                "type": "affects",
                "evidence_id": "ev_1",
            }
        ],
    }

    extraction = provider.map_payload_to_extraction(
        map_id="map_1",
        payload=payload,
        evidence_by_id={
            "ev_1": {
                "source_file_id": "file_1",
                "chunk_id": "chunk_1",
                "location": "paragraph 1",
                "text_span": "臭氧受光化学反应影响。",
            }
        },
        diagnostic=ExtractionDiagnostic(provider_name="llamaindex_property_graph"),
    )

    assert isinstance(extraction, ExtractionResult)
    assert len(extraction.candidate_entities) == 2
    assert extraction.candidate_relations[0].relation_type == "affects"
    assert extraction.candidate_relations[0].source_evidence_ids == ["ev_1"]
    assert extraction.evidence[0].ref == "map_evidence:ev_1"


def test_llamaindex_payload_relation_mapping_falls_back_to_entity_name_lookup():
    provider = LlamaIndexPropertyGraphExtractorProvider()
    payload = {
        "entities": [
            {"name": "臭氧", "type": "Pollutant", "evidence_id": "ev_1"},
            {"name": "光化学反应", "type": "ProcessMechanism", "evidence_id": "ev_1"},
        ],
        "relations": [
            {
                "source": "光化学反应",
                "target": "臭氧",
                "type": "affects",
                "evidence_id": "ev_1",
            }
        ],
    }

    extraction = provider.map_payload_to_extraction(
        map_id="map_1",
        payload=payload,
        evidence_by_id={
            "ev_1": {
                "source_file_id": "file_1",
                "chunk_id": "chunk_1",
                "location": "paragraph 1",
                "text_span": "臭氧受光化学反应影响。",
            }
        },
    )

    assert len(extraction.candidate_relations) == 1
    assert extraction.candidate_relations[0].relation_type == "affects"


def test_llamaindex_provider_builds_schema_components_from_cognitive_schema():
    provider = LlamaIndexPropertyGraphExtractorProvider(llm=object())
    schema = CognitiveSchema.default_air_quality_schema()

    components = provider.build_schema_components(schema)

    assert components.possible_entities is not None
    assert components.possible_relations is not None
    assert "PROCESSMECHANISM" in get_args(components.possible_entities)
    assert "AFFECTS" in get_args(components.possible_relations)
    assert ("PROCESSMECHANISM", "AFFECTS", "POLLUTANT") in components.validation_schema


def test_llamaindex_provider_maps_uppercase_llamaindex_labels_to_project_schema():
    provider = LlamaIndexPropertyGraphExtractorProvider()
    schema = CognitiveSchema.default_air_quality_schema()
    provider.build_schema_components(schema)

    extraction = provider.map_payload_to_extraction(
        map_id="map_1",
        payload={
            "entities": [
                {"name": "臭氧", "type": "POLLUTANT", "evidence_id": "ev_1"},
                {"name": "光化学反应", "type": "PROCESSMECHANISM", "evidence_id": "ev_1"},
            ],
            "relations": [
                {
                    "source": "光化学反应",
                    "target": "臭氧",
                    "type": "AFFECTS",
                    "evidence_id": "ev_1",
                }
            ],
        },
        evidence_by_id={
            "ev_1": {
                "source_file_id": "file_1",
                "chunk_id": "chunk_1",
                "location": "paragraph 1",
                "text_span": "臭氧受光化学反应影响。",
            }
        },
    )

    entity_types = {entity.entity_type for entity in extraction.candidate_entities}
    assert "Pollutant" in entity_types
    assert "ProcessMechanism" in entity_types
    assert extraction.candidate_relations[0].relation_type == "affects"


@pytest.mark.asyncio
async def test_llamaindex_provider_builds_property_graph_store_from_chunks():
    class FakeLLMService:
        provider = "fake"
        model = "fake-model"

        async def call_llm_with_json_response(self, prompt, max_retries=2):
            return {
                "triplets": [
                    {
                        "subject": {"type": "ProcessMechanism", "name": "光化学反应"},
                        "relation": {"type": "affects"},
                        "object": {"type": "Pollutant", "name": "臭氧"},
                    }
                ]
            }

    source_file = SourceFile(
        file_id="file_1",
        map_id="map_1",
        filename="notes.txt",
        content_type="text/plain",
        storage_path="/tmp/notes.txt",
    )
    chunks = await TextParserProvider(max_chars=500).parse_text(
        source_file=source_file,
        text="臭氧受光化学反应影响。",
    )
    llm = ProjectLLMAdapter(llm_service=FakeLLMService(), model_name="fake-model")
    provider = LlamaIndexPropertyGraphExtractorProvider(llm=llm)

    extraction = await provider.extract(
        chunks=chunks,
        schema=CognitiveSchema.default_air_quality_schema(),
    )

    assert provider.last_property_graph_store is not None
    assert provider.last_property_graph_store.graph.get_triplets()
    assert any(entity.name == "臭氧" for entity in extraction.candidate_entities)
    assert extraction.candidate_relations[0].relation_type == "affects"
    assert extraction.evidence[0].source_file_id == "file_1"


@pytest.mark.asyncio
async def test_llamaindex_provider_reports_missing_llm_cleanly():
    provider = LlamaIndexPropertyGraphExtractorProvider()
    schema = CognitiveSchema.default_air_quality_schema()

    with pytest.raises(RuntimeError, match="requires an LLM"):
        await provider.extract(chunks=[], schema=schema)


@pytest.mark.asyncio
async def test_project_llm_adapter_uses_project_llm_service_chat():
    class FakeLLMService:
        provider = "fake"
        model = "fake-model"

        async def chat(self, messages, temperature=None, max_tokens=None):
            assert messages == [{"role": "user", "content": "hello"}]
            assert temperature == 0.2
            assert max_tokens == 128
            return "world"

    llm = ProjectLLMAdapter(
        llm_service=FakeLLMService(),
        model_name="fake-model",
        temperature=0.2,
        max_tokens=128,
    )

    response = await llm.acomplete("hello")

    assert isinstance(response, CompletionResponse)
    assert response.text == "world"
    assert llm.metadata.model_name == "fake-model"


@pytest.mark.asyncio
async def test_project_llm_adapter_async_chat_uses_project_llm_service_chat():
    class FakeLLMService:
        provider = "fake"
        model = "fake-model"

        async def chat(self, messages, temperature=None, max_tokens=None):
            assert messages == [
                {"role": "system", "content": "extract"},
                {"role": "user", "content": "hello"},
            ]
            return "structured"

    llm = ProjectLLMAdapter(llm_service=FakeLLMService(), model_name="fake-model")

    response = await llm.achat(
        [
            ChatMessage(role="system", content="extract"),
            ChatMessage(role="user", content="hello"),
        ]
    )

    assert response.message.content == "structured"


@pytest.mark.asyncio
async def test_project_llm_adapter_structured_predict_uses_project_json_service():
    class FakeOutputModel:
        payload = None

        @classmethod
        def model_validate(cls, payload):
            cls.payload = payload
            return cls()

    class FakeLLMService:
        provider = "fake"
        model = "fake-model"

        async def call_llm_with_json_response(self, prompt, max_retries=2):
            assert "triplets" in prompt
            assert "臭氧受光化学反应影响" in prompt
            return {
                "triplets": [
                    {
                        "subject": {"type": "ProcessMechanism", "name": "光化学反应"},
                        "relation": {"type": "affects"},
                        "object": {"type": "Pollutant", "name": "臭氧"},
                    }
                ]
            }

    llm = ProjectLLMAdapter(llm_service=FakeLLMService(), model_name="fake-model")

    result = await llm.astructured_predict(
        FakeOutputModel,
        prompt=None,
        text="臭氧受光化学反应影响。",
        max_triplets_per_chunk=3,
    )

    assert isinstance(result, FakeOutputModel)
    assert FakeOutputModel.payload["triplets"][0]["relation"]["type"] == "affects"


def test_create_llamaindex_llm_project_provider_returns_project_adapter():
    llm = create_llamaindex_llm("project")

    assert isinstance(llm, ProjectLLMAdapter)


def test_project_llm_adapter_includes_allowed_triplets_in_structured_prompt():
    llm = ProjectLLMAdapter(llm_service=object(), model_name="fake-model")
    llm.set_cognitive_schema(CognitiveSchema.default_air_quality_schema())

    prompt = llm._build_structured_kg_prompt("臭氧受光化学反应影响。", max_triplets=3)

    assert "ProcessMechanism --affects--> Pollutant" in prompt


def test_project_llm_adapter_normalizes_common_triplet_keys():
    llm = ProjectLLMAdapter(llm_service=object(), model_name="fake-model")

    payload = llm._normalize_structured_payload({"relations": [{"subject": {}}]})

    assert payload["triplets"] == [{"subject": {}}]


def test_generate_evaluation_markdown_summarizes_extraction():
    extraction = LocalRuleBasedExtractorProvider().extract_sync_from_text(
        text="深圳市监测站监测臭氧。臭氧受光化学反应影响，机动车排放支持本地生成假设。",
        schema=CognitiveSchema.default_air_quality_schema(),
        map_id="map_1",
        file_id="file_1",
    )

    markdown = generate_evaluation_markdown(extraction, sample_size=3)

    assert "# 认知地图抽取评估" in markdown
    assert "候选实体数量" in markdown
    assert "有证据实体比例" in markdown
    assert "Pollutant" in markdown
