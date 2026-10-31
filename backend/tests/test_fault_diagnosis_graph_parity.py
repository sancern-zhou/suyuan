"""故障归因金色对拍：图驱动引擎（默认边集）与规则级联逐字段一致。

对拍通过后，项目分支把同一批边编入知识图谱种子即可无行为漂移地切换；
引擎与级联的任何一方单独改动都必须让本文件的对拍失败。
"""
import itertools

import pytest

from app.services.fault_diagnosis import FaultDiagnosisService
from app.services.fault_relation_registry import (
    KNOWN_SIGNALS,
    default_fault_edges,
    diagnose_from_edges,
)
from structlog.testing import capture_logs

# 参与级联的信号全集；边集外的信号不应改变归因结果。
CASCADE_SIGNALS = sorted(KNOWN_SIGNALS)

PARITY_FIELDS = (
    "cause",
    "cause_type",
    "confidence",
    "supporting_evidence",
    "contradicting_evidence",
    "missing_evidence",
    "recommended_action",
)


def _service(tmp_path) -> FaultDiagnosisService:
    return FaultDiagnosisService(output_root=tmp_path / "registry")


def _reason_code_combinations() -> list[list[str]]:
    combos: list[list[str]] = [[]]
    combos.extend([signal] for signal in CASCADE_SIGNALS)
    combos.extend(list(pair) for pair in itertools.combinations(CASCADE_SIGNALS, 2))
    # 代表性三信号组合：多硬边竞争原因 + 条件改写被覆盖的场景。
    combos.extend(
        [
            ["pm_cochange_weak", "main_pollutant_constant_streak", "single_station_dominant"],
            ["pm_cochange_weak", "single_station_dominant", "weather_missing"],
            ["no2_o3_pattern_weak", "single_station_dominant", "weather_missing"],
            ["pm_cochange_weak", "no2_o3_pattern_weak", "multi_station_coherent"],
            [
                "main_pollutant_constant_streak",
                "multi_station_coherent",
                "meteorology_supports_pollution",
            ],
            [
                "single_station_dominant",
                "peer_trend_inconsistent",
                "no2_o3_inverse_supported",
            ],
        ]
    )
    return combos


@pytest.mark.parametrize("reason_codes", _reason_code_combinations())
def test_graph_engine_matches_rule_cascade(tmp_path, reason_codes):
    service = _service(tmp_path)
    graph_cause = diagnose_from_edges(reason_codes, default_fault_edges())
    cascade_cause = service._ranked_cause(reason_codes, {})
    for field in PARITY_FIELDS:
        assert graph_cause[field] == cascade_cause[field], (
            f"reason_codes={reason_codes} 字段 {field} 不一致："
            f"graph={graph_cause[field]!r} cascade={cascade_cause[field]!r}"
        )


def test_attributed_cause_uses_graph_path_when_edges_available(tmp_path):
    edges = default_fault_edges()
    service = FaultDiagnosisService(
        output_root=tmp_path / "registry",
        fault_relation_provider=lambda **kwargs: {"used": True, "edges": edges},
    )
    cause = service._attributed_cause({}, {}, ["pm_cochange_weak"])
    assert cause["attribution_source"] == "knowledge_graph_edges"
    assert cause["cause"] == "采样系统或颗粒物监测链路异常"


def test_attributed_cause_falls_back_to_cascade_without_edges(tmp_path):
    service_no_provider = _service(tmp_path)
    cause = service_no_provider._attributed_cause({}, {}, ["pm_cochange_weak"])
    assert "attribution_source" not in cause
    assert cause["cause"] == "采样系统或颗粒物监测链路异常"

    service_empty = FaultDiagnosisService(
        output_root=tmp_path / "registry",
        fault_relation_provider=lambda **kwargs: {"used": False, "edges": []},
    )
    cause_empty = service_empty._attributed_cause({}, {}, ["pm_cochange_weak"])
    assert "attribution_source" not in cause_empty


def test_shadow_compare_logs_divergence_only(tmp_path):
    from app.services.fault_relation_registry import parse_fault_edge

    shifted = parse_fault_edge(
        {
            "relation_type": "fault.pm_cochange",
            "attributes": {
                "strength": "hard",
                "violation": {
                    "sequence": 1,
                    "signals": ["pm_cochange_weak"],
                    "reason": "PM2.5 与 PM10 协同关系偏弱",
                    "cause": "（测试）偏离级联的原因",
                    "cause_type": "device_or_facility",
                    "missing_evidence": ["采样流量记录"],
                    "action": "核查采样系统。",
                },
            },
        }
    )
    service = FaultDiagnosisService(
        output_root=tmp_path / "registry",
        fault_relation_provider=lambda **kwargs: {"used": True, "edges": [shifted]},
    )
    with capture_logs() as logs:
        cause = service._attributed_cause({}, {}, ["pm_cochange_weak"])
    assert cause["cause"] == "（测试）偏离级联的原因"
    divergences = [log for log in logs if log.get("event") == "fault_attribution_divergence"]
    assert len(divergences) == 1
    assert "cause" in divergences[0]["differing"]


def test_provider_payload_skips_invalid_edges():
    from app.knowledge_base.fault_relation_provider import make_fault_relation_provider
    from app.services.fault_relation_registry import DEFAULT_FAULT_EDGES

    rows = list(DEFAULT_FAULT_EDGES) + [
        {"relation_type": "fault.broken", "attributes": {"strength": "hard"}}
    ]
    payload = make_fault_relation_provider(rows)
    assert payload["used"] is True
    assert payload["fallback_reason"] == ""
    assert len(payload["edges"]) == len(DEFAULT_FAULT_EDGES)

    empty = make_fault_relation_provider([])
    assert empty["used"] is False
    assert empty["fallback_reason"] == "no_fault_edges"
