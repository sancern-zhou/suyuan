import pytest

from app.knowledge_base.scene_schemas import BusinessLogic, BusinessObject, SceneDraft
from app.knowledge_base.schema_compiler import SceneSchemaCompiler, SchemaCompilationError


def test_compile_business_language_to_strict_schema():
    draft = SceneDraft(
        scene_goal="分析企业噪声投诉与整改闭环",
        desired_questions=["哪些噪声源导致投诉？"],
        business_objects=[
            BusinessObject(key="enterprise", name="企业", description="被监管企业", aliases=[]),
            BusinessObject(
                key="noise_source",
                name="噪声源",
                description="产生噪声的设备或工艺",
                aliases=["声源"],
            ),
        ],
        business_logic=[
            BusinessLogic(
                key="enterprise_has_noise_source",
                statement="企业拥有噪声源",
                source_key="enterprise",
                relation_key="has_noise_source",
                target_key="noise_source",
                policy="required",
            )
        ],
        ignored_content=["页眉页脚"],
        source_document_ids=["doc-1"],
    )
    schema = SceneSchemaCompiler().compile(draft)
    assert schema.allowed_entity_types == ["enterprise", "noise_source"]
    assert schema.allowed_relation_triplets == [
        ("enterprise", "has_noise_source", "noise_source")
    ]
    assert schema.required_relation_triplets == [
        ("enterprise", "has_noise_source", "noise_source")
    ]
    assert schema.domain_aliases == {"噪声源": ["声源"]}
    assert schema.build_requirement == draft.scene_goal


def test_compile_rejects_logic_with_unknown_endpoint():
    draft = SceneDraft.model_validate(
        {
            "scene_goal": "噪声场景建模",
            "business_objects": [{"key": "enterprise", "name": "企业"}],
            "business_logic": [
                {
                    "key": "bad",
                    "statement": "企业拥有未知对象",
                    "source_key": "enterprise",
                    "relation_key": "has_unknown",
                    "target_key": "missing",
                    "policy": "allowed",
                }
            ],
            "source_document_ids": ["doc-1"],
        }
    )
    with pytest.raises(SchemaCompilationError, match="missing"):
        SceneSchemaCompiler().compile(draft)


def test_compile_keeps_forbidden_logic_out_of_allowed_relations():
    draft = SceneDraft.model_validate(
        {
            "scene_goal": "企业异常关联分析",
            "business_objects": [
                {"key": "enterprise", "name": "企业"},
                {"key": "monitoring_station", "name": "监测站"},
            ],
            "business_logic": [
                {
                    "key": "no_direct_cause",
                    "statement": "站点异常不能直接认定企业导致污染",
                    "source_key": "monitoring_station",
                    "relation_key": "caused_by",
                    "target_key": "enterprise",
                    "policy": "forbidden",
                }
            ],
            "source_document_ids": ["doc-1"],
        }
    )
    schema = SceneSchemaCompiler().compile(draft)
    assert schema.allowed_relation_types == []
    assert schema.forbidden_relation_triplets == [
        ("monitoring_station", "caused_by", "enterprise")
    ]
