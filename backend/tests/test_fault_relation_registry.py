"""故障归因边注册表（fault_relation_registry）解析与校验测试。"""
import pytest

from app.services.fault_relation_registry import (
    DEFAULT_FAULT_EDGES,
    KNOWN_SIGNALS,
    diagnose_from_edges,
    default_fault_edges,
    load_fault_edges,
    parse_fault_edge,
)


def _edge(*, relation_type=None, attributes=None, **attr_overrides):
    relation = {
        "relation_type": "fault.pm_cochange",
        "source_name": "PM2.5",
        "target_name": "PM10",
        "attributes": {
            "strength": "hard",
            "violation": {
                "sequence": 1,
                "signals": ["pm_cochange_weak"],
                "reason": "协同关系偏弱",
                "cause": "采样系统异常",
                "cause_type": "device_or_facility",
                "missing_evidence": ["采样流量记录"],
                "action": "核查采样系统。",
            },
            "contradiction": {
                "sequence": 2,
                "signals": ["pm_cochange_supported"],
                "reason": "协同变化较强，支持真实过程",
            },
        },
    }
    if relation_type is not None:
        relation["relation_type"] = relation_type
    if attributes is not None:
        relation["attributes"] = attributes
    relation["attributes"].update(attr_overrides)
    return relation


# ---- 解析与校验 ----


def test_parse_valid_edge():
    edge = parse_fault_edge(_edge())
    assert edge.relation_type == "fault.pm_cochange"
    assert edge.strength == "hard"
    assert edge.violation.signals == ("pm_cochange_weak",)
    assert edge.violation.cause == "采样系统异常"
    assert edge.contradiction.signals == ("pm_cochange_supported",)


def test_parse_rejects_non_fault_prefix():
    relation = _edge(relation_type="related.pm_cochange")
    with pytest.raises(ValueError, match="fault."):
        parse_fault_edge(relation)


def test_parse_rejects_unknown_signal():
    relation = _edge()
    relation["attributes"]["violation"]["signals"] = ["made_up_signal"]
    with pytest.raises(ValueError, match="made_up_signal"):
        parse_fault_edge(relation)


def test_parse_rejects_strength():
    relation = _edge(strength="medium")
    with pytest.raises(ValueError, match="strength"):
        parse_fault_edge(relation)


def test_parse_rejects_edge_without_signal_groups():
    relation = _edge(attributes={"strength": "soft"})
    with pytest.raises(ValueError, match="至少定义一组"):
        parse_fault_edge(relation)


def test_parse_rejects_hard_edge_without_cause_rule():
    relation = _edge()
    violation = relation["attributes"]["violation"]
    violation.pop("cause")
    violation.pop("cause_type")
    violation.pop("action")
    violation.pop("missing_evidence")
    with pytest.raises(ValueError, match="hard 边必须绑定原因规则"):
        parse_fault_edge(relation)


def test_parse_allows_hard_edge_with_conditional_only():
    relation = _edge()
    violation = relation["attributes"]["violation"]
    violation.pop("cause")
    violation.pop("cause_type")
    violation.pop("action")
    violation.pop("missing_evidence")
    violation["conditional"] = {
        "when_codes_subset": ["single_station_dominant"],
        "cause": "待复核",
        "cause_type": "needs_review",
        "missing_evidence": ["运维记录"],
        "action": "复核。",
    }
    edge = parse_fault_edge(relation)
    assert edge.violation.conditional is not None
    assert edge.violation.cause is None


def test_parse_cause_fields_all_or_none():
    relation = _edge()
    relation["attributes"]["violation"].pop("cause_type")
    with pytest.raises(ValueError, match="必须同时提供或同时省略"):
        parse_fault_edge(relation)


def test_parse_conditional_and_direct_cause_mutually_exclusive():
    relation = _edge()
    relation["attributes"]["violation"]["conditional"] = {
        "when_codes_subset": ["single_station_dominant"],
        "cause": "待复核",
        "cause_type": "needs_review",
        "missing_evidence": ["运维记录"],
        "action": "复核。",
    }
    with pytest.raises(ValueError, match="互斥"):
        parse_fault_edge(relation)


def test_load_fault_edges_skips_invalid_rows_with_warnings():
    rows = [_edge(), {"relation_type": "fault.broken", "attributes": {}}, _edge()]
    edges, warnings = load_fault_edges(rows)
    assert len(edges) == 2
    assert len(warnings) == 1


# ---- 默认边集与信号闭集自检 ----


def test_known_signals_cover_cascade_vocabulary():
    required = {
        "pm_cochange_weak",
        "pm_cochange_supported",
        "no2_o3_pattern_weak",
        "no2_o3_inverse_supported",
        "main_pollutant_constant_streak",
        "single_station_dominant",
        "peer_trend_inconsistent",
        "multi_station_coherent",
        "meteorology_supports_pollution",
        "regional_signal_coherent",
        "weather_missing",
    }
    missing = required - set(KNOWN_SIGNALS)
    assert not missing, f"信号闭集缺少级联依赖的信号：{missing}"


def test_default_edge_set_parses_cleanly():
    edges = default_fault_edges()
    assert len(edges) == len(DEFAULT_FAULT_EDGES)
    relation_types = {edge.relation_type for edge in edges}
    assert relation_types == {item["relation_type"] for item in DEFAULT_FAULT_EDGES}


# ---- 归因引擎关键语义 ----


def _by_type(edges):
    return {edge.relation_type: edge for edge in edges}


def test_engine_conditional_needs_review():
    edges = _by_type(default_fault_edges())
    result = diagnose_from_edges(
        ["single_station_dominant", "weather_missing"], list(edges.values())
    )
    assert result["cause_type"] == "needs_review"
    assert result["cause"] == "单站局地影响或数据链路异常待复核"


def test_engine_conditional_overridden_by_later_hard_rule():
    edges = _by_type(default_fault_edges())
    result = diagnose_from_edges(
        ["single_station_dominant", "no2_o3_pattern_weak"], list(edges.values())
    )
    assert result["cause"] == "气态分析仪或校准链路异常"


def test_engine_default_cause_without_hits():
    result = diagnose_from_edges(["quality_gate_limited"], default_fault_edges())
    assert result["cause"] == "站点数据链路异常"
    assert result["supporting_evidence"] == ["一级结论已标记为疑似设备或数据故障"]
    assert result["confidence"] == "low"
    assert result["attribution_source"] == "knowledge_graph_edges"
