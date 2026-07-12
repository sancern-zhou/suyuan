from app.knowledge_base.graph_extraction.llm_factory import ProjectLLMAdapter
from app.knowledge_base.graph_extraction.models import GraphExtractionSchema


class FakeLLMService:
    pass


def noise_scene_schema():
    return GraphExtractionSchema(
        allowed_entity_types=["enterprise", "noise_source"],
        allowed_relation_types=["has_noise_source"],
        allowed_relation_triplets=[("enterprise", "has_noise_source", "noise_source")],
        required_relation_triplets=[("enterprise", "has_noise_source", "noise_source")],
        build_requirement="工业企业厂界噪声分析",
        entity_type_descriptions={"enterprise": "被监管企业", "noise_source": "产生噪声的对象"},
        relation_type_descriptions={"has_noise_source": "企业拥有噪声源"},
        ignored_content=["页眉页脚"],
    )


def test_prompt_uses_scene_schema_without_air_quality_hardcoding():
    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())
    adapter.set_cognitive_schema(noise_scene_schema())
    prompt = adapter._build_structured_kg_prompt("企业A存在空压机噪声", 10)
    assert "enterprise：被监管企业" in prompt
    assert "enterprise --has_noise_source--> noise_source" in prompt
    assert "工业企业厂界噪声分析" in prompt
    assert "Station, Pollutant, Metric" not in prompt


def test_prompt_contains_confirmed_rules_and_ignored_content():
    adapter = ProjectLLMAdapter(llm_service=FakeLLMService())
    adapter.set_cognitive_schema(noise_scene_schema())
    adapter.set_business_rules([{"summary": "监测结果必须关联昼夜时段"}])
    prompt = adapter._build_structured_kg_prompt("正文", 10)
    assert "监测结果必须关联昼夜时段" in prompt
    assert "不要抽取：页眉页脚" in prompt
