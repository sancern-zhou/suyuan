# -*- coding: utf-8 -*-
"""语义治理共享库（app/services/semantic_governance）单元测试。

全部离线：临时文件 + 纯函数；不连 Cube、不连数据库。
"""
import base64
import json

import pytest
import yaml

from app.services.semantic_governance import (
    CatalogUnavailable,
    aggregate_quality,
    build_insert,
    build_query,
    build_semantic_context,
    cube_metadata,
    dataset_metadata,
    flatten_rows,
    has_member,
    load_catalog,
    load_contract,
    load_registry,
    make_token,
    quality_guidance,
    truncate_rows,
    validate_result,
)


# ---------------------------------------------------------------- quality_policy

def test_quality_policy_decision_boundaries():
    assert quality_guidance("ok")["decision"] == "可用于定量判断"
    assert quality_guidance("degraded")["decision"] == "仅可作谨慎判断"
    assert quality_guidance("blocked")["decision"] == "不可形成业务结论"
    assert quality_guidance("anything-else")["decision"] == "质量未知"


# ---------------------------------------------------------------- catalog_store

CATALOG = {
    "version": 1,
    "project": "demo",
    "generated_from": ["cube/schema/*.js", "semantic/registry.yaml"],
    "cubes": {
        "Orders": {
            "dataset": "mart_orders",
            "grain": "one row per order",
            "applicability": "all orders",
            "measures": {
                "count": {"title": "订单量", "name": "订单量", "definition": "订单条数"},
                "finishRate": {"title": "完成率", "name": "完成率",
                               "definition": "x/y", "denominator": "count"},
            },
            "dimensions": {"city": {"title": "城市"}},
        },
    },
}


def _write_catalog(tmp_path, payload):
    path = tmp_path / "catalog.generated.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_catalog_store_loads_valid_artifact(tmp_path):
    path = _write_catalog(tmp_path, CATALOG)
    catalog = load_catalog(path)
    assert list(catalog["cubes"]) == ["Orders"]
    assert has_member(catalog, "Orders", "measures", "finishRate")
    assert has_member(catalog, "Orders", "dimensions", "city")
    assert not has_member(catalog, "Orders", "measures", "nope")
    assert not has_member(catalog, "Missing", "measures", "count")


def test_catalog_store_fail_closed_on_missing_or_corrupt(tmp_path):
    with pytest.raises(CatalogUnavailable):
        load_catalog(tmp_path / "missing.json")
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogUnavailable):
        load_catalog(corrupt)


def test_catalog_store_fail_closed_on_bad_shape(tmp_path):
    bad = _write_catalog(tmp_path, {"cubes": {"Orders": {"measures": []}}})
    with pytest.raises(CatalogUnavailable):
        load_catalog(bad)


def test_catalog_store_rereads_after_file_change(tmp_path):
    path = _write_catalog(tmp_path, CATALOG)
    assert "finishRate" in load_catalog(path)["cubes"]["Orders"]["measures"]
    changed = dict(CATALOG)
    changed["cubes"] = {"Orders": dict(CATALOG["cubes"]["Orders"],
                                       measures={"only": {"title": "x"}})}
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert "only" in load_catalog(path)["cubes"]["Orders"]["measures"]


# ---------------------------------------------------------------- registry

REGISTRY = {
    "version": 2,
    "project": "demo",
    "cubes": {"Orders": {"dataset": "mart_orders",
                         "measures": {"finishRate": {"name": "完成率",
                                                     "denominator": "count"}}}},
}


def test_registry_fail_open_on_missing(tmp_path):
    registry = load_registry(tmp_path / "missing.yaml")
    assert registry["cubes"] == {}
    assert registry["version"] == 0


def test_cube_metadata_overlays_registry_and_falls_back_to_catalog(tmp_path):
    registry = load_registry(_write_yaml(tmp_path, REGISTRY))
    metadata = cube_metadata(registry, "Orders", CATALOG)
    assert metadata["measures"]["finishRate"]["denominator"] == "count"
    # 未登记成员：产物 title 顶 name/definition
    assert metadata["measures"]["count"]["name"] == "订单量"
    assert metadata["registry_version"] == 2


def test_dataset_metadata_maps_dataset_to_cube(tmp_path):
    registry = load_registry(_write_yaml(tmp_path, REGISTRY))
    metadata = dataset_metadata(registry, "mart_orders")
    assert metadata["cube"] == "Orders"
    unknown = dataset_metadata(registry, "other_table")
    assert unknown == {"dataset": "other_table", "registry_version": 2}


def _write_yaml(tmp_path, payload):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------- contract

CONTRACT = {
    "version": 1,
    "profiles": {
        "metric_query": {
            "required": ["success", "data", "quality_status"],
            "semantic_context_required": ["dataset", "data_as_of"],
        },
        "schema_introspection": {
            "required": ["success"],
            "semantic_context_equals": {"query_role": "schema_introspection"},
        },
    },
}


def _write_contract(tmp_path, payload):
    path = tmp_path / "result_contract.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_contract_declarative_rules(tmp_path):
    contract = load_contract(_write_contract(tmp_path, CONTRACT))
    payload = {"success": True, "data": [], "quality_status": "ok",
               "semantic_context": {"dataset": "d", "data_as_of": None}}
    assert validate_result(contract, "metric_query", payload) == []
    payload["semantic_context"].pop("data_as_of")
    assert any("data_as_of" in e for e in validate_result(contract, "metric_query", payload))
    assert validate_result(None, "metric_query", payload) == []
    assert validate_result(contract, "nope", payload) == ["unknown profile: nope"]


def test_contract_semantic_context_equals_rule(tmp_path):
    contract = load_contract(_write_contract(tmp_path, CONTRACT))
    ok = {"success": True, "semantic_context": {"query_role": "schema_introspection"}}
    bad = {"success": True, "semantic_context": {"query_role": "other"}}
    assert validate_result(contract, "schema_introspection", ok) == []
    assert any("query_role" in e for e in validate_result(contract, "schema_introspection", bad))


def test_contract_fail_open_on_missing_file(tmp_path):
    assert load_contract(tmp_path / "missing.yaml") is None


# ---------------------------------------------------------------- cube_client

def test_make_token_is_wellformed_hs256():
    token = make_token("s3cret", ttl_seconds=60)
    header_b64, payload_b64, sig = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    assert header == {"alg": "HS256", "typ": "JWT"}
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert set(payload) == {"exp"}


def test_build_query_shape():
    query = build_query(
        ["Orders.count"], dimensions=["Orders.city"], time_dimension="Orders.created",
        date_range=["2026-01-01", "2026-01-31"], granularity="day",
        filters=[{"member": "Orders.city", "operator": "equals", "values": ["A"]}],
        order={"Orders.count": "desc"}, limit=51,
    )
    assert query["measures"] == ["Orders.count"]
    assert query["timeDimensions"] == [{
        "dimension": "Orders.created",
        "dateRange": ["2026-01-01", "2026-01-31"],
        "granularity": "day",
    }]
    assert query["limit"] == 51
    minimal = build_query(["Orders.count"])
    assert set(minimal) == {"measures"}


def test_flatten_and_truncate_rows():
    body = {"data": [{"Orders.count": {"value": 3}}, {"Orders.count": {"value": 5}}]}
    rows = flatten_rows(body)
    assert rows == [{"Orders.count": 3}, {"Orders.count": 5}]
    kept, truncated = truncate_rows(rows, 1)
    assert kept == [{"Orders.count": 3}] and truncated is True
    kept, truncated = truncate_rows(rows, 2)
    assert truncated is False


# ---------------------------------------------------------------- gating

def test_aggregate_quality():
    assert aggregate_quality([]) == "unknown"
    assert aggregate_quality([{"status": "OK"}]) == "ok"
    assert aggregate_quality([{"status": "OK"}, {"status": "WARN"}]) == "degraded"
    assert aggregate_quality([{"status": "OK"}, {"status": "FAIL"}]) == "blocked"


# ---------------------------------------------------------------- audit

def test_build_insert_maps_record_to_placeholders():
    sql, values = build_insert("app.query_audit", {
        "tool": "t", "row_count": 5, "truncated": False,
    })
    assert sql == "INSERT INTO app.query_audit (tool, row_count, truncated) VALUES ($1, $2, $3)"
    assert values == ["t", 5, False]


# ---------------------------------------------------------------- semantic_context

ENTRY = {"dataset": "mart_orders", "grain": "g", "applicability": "a",
         "source_window": "w", "freshness_slo": "60min", "limitations": ["l1"]}


def test_build_semantic_context_minimal_for_describe():
    ctx = build_semantic_context(2, ENTRY, {"count": {"name": "订单量"}})
    assert ctx["registry_version"] == 2
    assert ctx["metric_definitions"] == {"count": {"name": "订单量"}}
    assert "data_as_of" not in ctx and "quality_guidance" not in ctx


def test_build_semantic_context_full_for_metric_query():
    ctx = build_semantic_context(
        2, ENTRY, {}, data_as_of=None, include_data_as_of=True,
        quality_status="degraded", quality_checks=[{"check": "c", "status": "WARN"}])
    assert ctx["data_as_of"] is None  # 契约要求键存在
    assert ctx["quality_checks"] == [{"check": "c", "status": "WARN"}]
    assert ctx["quality_guidance"] == quality_guidance("degraded")
