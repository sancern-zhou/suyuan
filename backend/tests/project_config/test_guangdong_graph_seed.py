"""广东数据语义图谱种子与问数入口链接测试。

守护两件事：
1. project.yaml 的图谱绑定与入口模式声明正确（graph_entry_modes + data_semantics 绑定）；
2. gen_graph_seed.py 生成的种子结构完备（域归属全覆盖、指标消歧、锚点存在），
   且种子实体能被 graph_entry_context 的匹配器命中。
"""
import importlib.util
import io
from pathlib import Path

import pytest

from app.project_config.loader import load_project_context
from config.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_SCRIPT = REPO_ROOT / "projects/guangdong/data-ops/sync/gen_graph_seed.py"
SEED_JSON = REPO_ROOT / "projects/guangdong/data-ops/graph/graph_seed.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_graph_seed", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed():
    module = _load_generator()
    return module.build_seed()


@pytest.fixture(autouse=True)
def _guangdong_project(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "guangdong")


def test_guangdong_manifest_declares_graph_entry():
    manifest = load_project_context("guangdong").manifest.knowledge
    assert manifest.graph_entry_modes == ["gd_query", "query"]
    assert manifest.bindings.get("data_semantics") == "广东数据语义"


def test_seed_entity_inventory(seed):
    counts = {}
    for entity in seed["entities"]:
        counts[entity["entity_type"]] = counts.get(entity["entity_type"], 0) + 1
    # 42 张契约表全部入图；7 个数据域；6 个查询路由工具；registry 全部指标
    assert counts.get("MartTable") == 42
    assert counts.get("Domain") == 7
    assert counts.get("QueryTool") == 6
    assert counts.get("Metric") == 24
    local_ids = [entity["local_id"] for entity in seed["entities"]]
    assert len(local_ids) == len(set(local_ids)), "实体 local_id 重复"


def test_seed_metric_disambiguation(seed):
    names = {entity["name"] for entity in seed["entities"] if entity["entity_type"] == "Metric"}
    # 同名指标（超期率/完成率/涉及站点数）必须带 cube 前缀消歧
    assert "工单超期率" in names and "巡检超期率" in names
    assert "工单完成率" in names and "巡检完成率" in names
    # 裸名保留在别名中以支持问题匹配
    by_name = {
        entity["name"]: entity for entity in seed["entities"] if entity["entity_type"] == "Metric"
    }
    assert "超期率" in by_name["工单超期率"]["aliases"]
    assert "超期率" in by_name["巡检超期率"]["aliases"]


def test_seed_relations_reference_known_entities(seed):
    local_ids = {entity["local_id"] for entity in seed["entities"]}
    for relation in seed["relations"]:
        assert relation["source_local_id"] in local_ids, relation
        assert relation["target_local_id"] in local_ids, relation
    relation_types = {relation["relation_type"] for relation in seed["relations"]}
    assert {"belongs_to", "measured_in", "derived_from", "query_via"} <= relation_types


def test_seed_document_contains_anchor_marker(seed):
    module = _load_generator()
    document = module.build_document(seed)
    assert seed["anchor_marker"] in document
    assert "工单超期率" in document or "超期率" in document


def test_seed_json_artifact_matches_generator():
    """提交的 graph_seed.json 必须是当前生成器的产物（防漂移）。"""
    module = _load_generator()
    deployed = io.open(SEED_JSON, encoding="utf-8").read()
    assert deployed == module._render_seed_json(module.build_seed())


def test_seed_entities_hit_question_matching(seed):
    """种子实体经 graph_entry_context 匹配器能命中典型问数问题。"""
    from app.agent.context.graph_entry_context import build_graph_entry_layer
    from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation

    entities = [
        KnowledgeGraphEntity(
            id=entity["local_id"],
            kb_id="kb-test",
            entity_type=entity["entity_type"],
            name=entity["name"],
            normalized_name=entity["name"].lower(),
            aliases=entity.get("aliases") or [],
            description=entity.get("description") or "",
            attributes=entity.get("attributes") or {},
            review_status="confirmed",
        )
        for entity in seed["entities"]
    ]
    relations = [
        KnowledgeGraphRelation(
            kb_id="kb-test",
            source_entity_id=relation["source_local_id"],
            target_entity_id=relation["target_local_id"],
            relation_type=relation["relation_type"],
            description=relation.get("description") or "",
            review_status="confirmed",
        )
        for relation in seed["relations"]
    ]
    layer = build_graph_entry_layer("工单超期率怎么算的？在哪查？", entities, relations)
    assert "工单超期率" in layer
    assert "measured_in" in layer and "mart_work_order_analysis" in layer
    assert "query_via" in layer and "语义层指标点查" in layer
    # 口径红线进层：分母口径可追溯
    assert "计划完成时间" in layer
