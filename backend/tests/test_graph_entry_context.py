"""问数入口图谱实体链接（graph_entry_context）测试。"""
from app.agent.context.context_builder import SYSTEM_CONTEXT_LAYER_ORDER, SimplifiedContextBuilder
from app.agent.context.graph_entry_context import build_graph_entry_layer
from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.project_config.models import KnowledgeManifest


def _entity(entity_id, name, *, entity_type="Metric", aliases=None, description="", attributes=None):
    return KnowledgeGraphEntity(
        id=entity_id,
        kb_id="kb1",
        entity_type=entity_type,
        name=name,
        normalized_name=name.lower(),
        aliases=aliases or [],
        description=description,
        attributes=attributes or {},
        review_status="confirmed",
    )


def _relation(source_id, target_id, relation_type, description=""):
    return KnowledgeGraphRelation(
        kb_id="kb1",
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type=relation_type,
        description=description,
        review_status="confirmed",
    )


# ---- 纯函数渲染层 ----


def test_match_by_name_and_alias_with_length_ranking():
    entities = [
        _entity("e1", "超期率", description="超期工单占比"),
        _entity("e2", "工单超期率", aliases=["超期率"], description="别名命中"),
        _entity("e3", "完成率"),
    ]
    layer = build_graph_entry_layer("超期率怎么算的", entities, [])
    assert "超期率" in layer
    assert "完成率" not in layer


def test_relations_adjacent_to_matched_entities_rendered():
    entities = [
        _entity("e1", "超期率"),
        _entity("e2", "mart_work_order_analysis", entity_type="MartTable"),
        _entity("e3", "guangdong_query_metrics", entity_type="QueryTool"),
        _entity("e4", "无关实体"),
    ]
    relations = [
        _relation("e1", "e2", "measured_in", "超期率存于工单分析宽表"),
        _relation("e1", "e3", "query_via"),
        _relation("e4", "e2", "belongs_to"),
    ]
    layer = build_graph_entry_layer("超期率在哪查", entities, relations)
    assert "measured_in" in layer
    assert "query_via" in layer
    assert "无关实体" not in layer
    # 关系描述进入渲染
    assert "超期率存于工单分析宽表" in layer


def test_no_match_returns_empty():
    entities = [_entity("e1", "超期率")]
    assert build_graph_entry_layer("今天天气怎么样", entities, []) == ""
    assert build_graph_entry_layer("", entities, []) == ""


def test_layer_is_bounded():
    entities = [
        _entity(f"e{i}", f"指标名称超长测试{i}", description="描述" * 200)
        for i in range(10)
    ]
    relations = [
        _relation(f"e{i}", f"e{i + 1}", "derived_from") for i in range(30)
    ]
    layer = build_graph_entry_layer(
        " ".join(f"指标名称超长测试{i}" for i in range(10)), entities, relations
    )
    assert len(layer) <= 1900  # 上限 1800 + 截断标记


# ---- 配置与构建器门控 ----


def test_knowledge_manifest_parses_graph_entry_modes():
    manifest = KnowledgeManifest(
        bindings={"data_semantics": "广东数据语义"},
        graph_entry_modes=["gd_query", "query"],
    )
    assert manifest.graph_entry_modes == ["gd_query", "query"]
    assert KnowledgeManifest().graph_entry_modes == []


def test_system_layer_order_contains_graph_entry():
    assert "graph_entry" in SYSTEM_CONTEXT_LAYER_ORDER
    assert SYSTEM_CONTEXT_LAYER_ORDER.index("graph_entry") == (
        SYSTEM_CONTEXT_LAYER_ORDER.index("knowledge_evidence") + 1
    )


def _new_builder():
    return SimplifiedContextBuilder(llm_client=None, memory_manager=None)


def test_builder_skips_layer_when_mode_not_enabled(monkeypatch):
    import app.agent.context.graph_entry_context as module

    builder = _new_builder()
    builder.graph_entry_context = "旧轮残留"
    monkeypatch.setattr(
        "app.project_config.load_project_context",
        lambda *_: type("Ctx", (), {
            "manifest": type("M", (), {
                "knowledge": KnowledgeManifest(graph_entry_modes=["gd_query"])
            }),
        })(),
    )
    import asyncio

    asyncio.run(builder._maybe_build_graph_entry_context("问题", "query", 1))
    assert builder.graph_entry_context is None


def test_builder_builds_layer_for_enabled_mode_on_first_iteration(monkeypatch):
    builder = _new_builder()
    monkeypatch.setattr(
        "app.project_config.load_project_context",
        lambda *_: type("Ctx", (), {
            "manifest": type("M", (), {
                "knowledge": KnowledgeManifest(graph_entry_modes=["gd_query"])
            }),
        })(),
    )
    async def fake_build(question):
        return "图谱命中内容"

    import app.agent.context.graph_entry_context as module
    monkeypatch.setattr(module, "build_graph_entry_context", fake_build)
    import asyncio

    asyncio.run(builder._maybe_build_graph_entry_context("超期率", "gd_query", 1))
    assert builder.graph_entry_context == "图谱命中内容"

    # 同轮后续迭代复用快照，不重算
    async def fail_build(question):
        raise AssertionError("不应重算")

    monkeypatch.setattr(module, "build_graph_entry_context", fail_build)
    asyncio.run(builder._maybe_build_graph_entry_context("第二个问题", "gd_query", 2))
    assert builder.graph_entry_context == "图谱命中内容"
