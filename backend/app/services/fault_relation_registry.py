"""故障归因关系边（fault relation edges）的代码侧契约与解析。

边以知识图谱 ``KnowledgeGraphRelation`` 行存储（relation_type 以 ``fault.`` 为前缀），
归因引擎按边的 ``attributes`` 解释证据语义。注册表职责：

- 定义已知信号闭集：每个信号都锚定 ``pollution_event_conclusion`` 中可计算的检查，
  保证"每条边都可验证"，禁止引用不存在的信号；
- 解析并校验边 attributes（结构、信号引用、hard 边必须绑定原因规则）；
- 提供与规则级联（``FaultDiagnosisService._ranked_cause``）语义一致的默认边集，
  作为金色对拍基准与项目编边的参考模板。

引擎语义（与规则级联逐字段一致）：

- ``violation``：该一致性关系被破坏（signals 命中 reason_codes）→ 追加故障侧
  supporting 证据与待补采证据；若绑定原因规则，则 cause/cause_type/action 被设置，
  后命中（sequence 更大）的规则覆盖先命中的；
- ``contradiction``：关系成立（signals 命中）→ 追加指向真实污染过程的反驳证据；
- supporting/missing 按 violation.sequence 升序累积，contradicting 按
  contradiction.sequence 升序累积，与级联分支的文本顺序一致。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

RELATION_TYPE_PREFIX = "fault."


# 已知信号闭集。键必须与 pollution_event_conclusion 产出的 reason_code 一致；
# 新信号需先在该处实现检查，再登记到这里，边集才可引用。
KNOWN_SIGNALS: dict[str, str] = {
    "station_hour_missing": "站点小时数据缺失",
    "too_few_peer_stations": "同城可比站点过少",
    "single_station_dominant": "污染事件由单站或少数站点主导",
    "peer_trend_inconsistent": "同城站点趋势不同步",
    "pm_cochange_weak": "PM2.5 与 PM10 协同变化偏弱",
    "pm_cochange_supported": "PM2.5 与 PM10 协同变化较强",
    "no2_o3_pattern_weak": "NO2 与 O3 反向变化特征偏弱",
    "no2_o3_inverse_supported": "NO2 与 O3 反向变化特征明显",
    "quality_gate_limited": "质量门限受限",
    "main_pollutant_constant_streak": "主污染物长时间恒值",
    "weather_missing": "气象数据缺失",
    "meteorology_supports_pollution": "气象条件支持污染累积",
    "regional_signal_coherent": "区域信号一致",
    "multi_station_coherent": "同城多站点一致变化",
}

STRENGTHS = ("hard", "soft")

# 引擎级联缺省值（与 _ranked_cause 的初始值/兜底值一致）。
DEFAULT_CAUSE = "站点数据链路异常"
DEFAULT_CAUSE_TYPE = "data_quality"
DEFAULT_ACTION = "核查站点小时数据、数采状态和同城站点对比。"
DEFAULT_SUPPORTING = "一级结论已标记为疑似设备或数据故障"
DEFAULT_MISSING = "近期运维工单、质控记录和设备状态"


@dataclass(frozen=True)
class ConditionalCause:
    """满足 ``when_codes_subset``（reason_codes 是其子集）时改写归因结论。"""

    when_codes_subset: frozenset[str]
    cause: str
    cause_type: str
    missing_evidence: tuple[str, ...]
    action: str


@dataclass(frozen=True)
class ViolationSpec:
    """关系被破坏（signals 命中）时的故障侧证据与归因结论。

    ``sequence`` 是证据累积与原因覆盖顺序：sequence 大的原因规则覆盖小的。
    """

    signals: tuple[str, ...]
    reason: str
    sequence: int
    cause: str | None = None
    cause_type: str | None = None
    missing_evidence: tuple[str, ...] = ()
    action: str | None = None
    conditional: ConditionalCause | None = None


@dataclass(frozen=True)
class ContradictionSpec:
    """关系成立（signals 命中）时指向真实污染过程的反驳证据。"""

    signals: tuple[str, ...]
    reason: str
    sequence: int


@dataclass(frozen=True)
class FaultRelationEdge:
    relation_type: str
    strength: str
    violation: ViolationSpec | None
    contradiction: ContradictionSpec | None
    source_name: str = ""
    target_name: str = ""


def _require_known_signals(raw: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{field} 必须是非空信号列表")
    unknown = [str(item) for item in raw if str(item) not in KNOWN_SIGNALS]
    if unknown:
        raise ValueError(
            f"{field} 引用未登记信号 {unknown}；新信号需先在 pollution_event_conclusion"
            " 实现检查并登记 KNOWN_SIGNALS"
        )
    return tuple(str(item) for item in raw)


def _parse_sequence(raw: Any, *, field: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{field} 必须显式给出整数（证据累积/原因覆盖顺序）")
    return raw


def _parse_cause_fields(group: Mapping[str, Any], *, field: str):
    cause = group.get("cause")
    cause_type = group.get("cause_type")
    action = group.get("action")
    set_fields = [
        name
        for name, value in (("cause", cause), ("cause_type", cause_type), ("action", action))
        if value
    ]
    if set_fields and len(set_fields) != 3:
        raise ValueError(f"{field}.cause/cause_type/action 必须同时提供或同时省略")
    return cause, cause_type, action


def _parse_missing_evidence(raw: Any, *, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"{field} 必须是非空字符串列表")
    return tuple(raw)


def _parse_conditional(raw: Any, *, field: str) -> ConditionalCause | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{field} 必须是对象")
    subset = _require_known_signals(raw.get("when_codes_subset"), field=f"{field}.when_codes_subset")
    cause = raw.get("cause")
    cause_type = raw.get("cause_type")
    action = raw.get("action")
    if not (cause and cause_type and action):
        raise ValueError(f"{field} 缺少 cause/cause_type/action")
    missing = _parse_missing_evidence(raw.get("missing_evidence"), field=f"{field}.missing_evidence")
    if not missing:
        raise ValueError(f"{field}.missing_evidence 必须列出需补采的证据")
    return ConditionalCause(frozenset(subset), str(cause), str(cause_type), missing, str(action))


def _parse_violation(raw: Any, *, field: str) -> ViolationSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{field} 必须是对象")
    signals = _require_known_signals(raw.get("signals"), field=f"{field}.signals")
    sequence = _parse_sequence(raw.get("sequence"), field=f"{field}.sequence")
    reason = raw.get("reason")
    if not reason or not isinstance(reason, str):
        raise ValueError(f"{field}.reason 必须是非空文本")
    cause, cause_type, action = _parse_cause_fields(raw, field=field)
    missing = _parse_missing_evidence(raw.get("missing_evidence"), field=f"{field}.missing_evidence")
    if missing and not cause:
        raise ValueError(f"{field}.missing_evidence 仅在绑定原因规则时有效")
    conditional = _parse_conditional(raw.get("conditional"), field=f"{field}.conditional")
    if conditional and cause:
        raise ValueError(f"{field}.conditional 与直接 cause 互斥：命中即设 cause 的边不需要 conditional")
    return ViolationSpec(
        signals=signals,
        reason=reason,
        sequence=sequence,
        cause=cause,
        cause_type=cause_type,
        missing_evidence=missing,
        action=action,
        conditional=conditional,
    )


def _parse_contradiction(raw: Any, *, field: str) -> ContradictionSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{field} 必须是对象")
    signals = _require_known_signals(raw.get("signals"), field=f"{field}.signals")
    sequence = _parse_sequence(raw.get("sequence"), field=f"{field}.sequence")
    reason = raw.get("reason")
    if not reason or not isinstance(reason, str):
        raise ValueError(f"{field}.reason 必须是非空文本")
    return ContradictionSpec(signals=signals, reason=reason, sequence=sequence)


def parse_fault_edge(relation: Mapping[str, Any]) -> FaultRelationEdge:
    """把图谱关系行解析为归因边；不合法时抛 ``ValueError``。"""
    relation_type = str(relation.get("relation_type") or "")
    if not relation_type.startswith(RELATION_TYPE_PREFIX):
        raise ValueError(f"relation_type 必须以 {RELATION_TYPE_PREFIX} 为前缀：{relation_type!r}")
    attributes = relation.get("attributes")
    if not isinstance(attributes, dict):
        raise ValueError(f"{relation_type}: attributes 必须是对象")

    strength = attributes.get("strength")
    if strength not in STRENGTHS:
        raise ValueError(f"{relation_type}: strength 必须是 {STRENGTHS} 之一")

    violation = _parse_violation(attributes.get("violation"), field=f"{relation_type}.violation")
    contradiction = _parse_contradiction(
        attributes.get("contradiction"), field=f"{relation_type}.contradiction"
    )
    if violation is None and contradiction is None:
        raise ValueError(f"{relation_type}: violation 与 contradiction 至少定义一组")
    if strength == "hard" and (violation is None or not (violation.cause or violation.conditional)):
        raise ValueError(f"{relation_type}: hard 边必须绑定原因规则（cause 或 conditional）")

    return FaultRelationEdge(
        relation_type=relation_type,
        strength=strength,
        violation=violation,
        contradiction=contradiction,
        source_name=str(relation.get("source_name") or ""),
        target_name=str(relation.get("target_name") or ""),
    )


def load_fault_edges(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[FaultRelationEdge], list[str]]:
    """批量解析关系行，跳过并记录不合法的边。"""
    edges: list[FaultRelationEdge] = []
    warnings: list[str] = []
    for row in rows:
        try:
            edges.append(parse_fault_edge(row))
        except ValueError as exc:
            warnings.append(str(exc))
    return edges, warnings


def diagnose_from_edges(reason_codes: list[str], edges: list[FaultRelationEdge]) -> dict[str, Any]:
    """图驱动归因：按 sequence 级联命中边，语义与规则级联逐字段一致。

    返回结构与 ``FaultDiagnosisService._ranked_cause`` 相同，额外携带
    ``matched_relation_types`` 与 ``attribution_source``。
    """
    codes = set(reason_codes)
    supporting: list[str] = []
    contradicting: list[str] = []
    missing: list[str] = []
    cause = DEFAULT_CAUSE
    cause_type = DEFAULT_CAUSE_TYPE
    action = DEFAULT_ACTION
    matched: list[str] = []

    violations = sorted(
        (edge.violation for edge in edges if edge.violation is not None),
        key=lambda item: (item.sequence, item.reason),
    )
    for violation in violations:
        if not any(signal in codes for signal in violation.signals):
            continue
        matched.append(violation.reason)
        supporting.append(violation.reason)
        missing.extend(violation.missing_evidence)
        if violation.cause:
            cause = violation.cause
            cause_type = violation.cause_type or DEFAULT_CAUSE_TYPE
            action = violation.action or DEFAULT_ACTION
        conditional = violation.conditional
        if conditional is not None and codes <= set(conditional.when_codes_subset):
            cause = conditional.cause
            cause_type = conditional.cause_type
            action = conditional.action
            missing.extend(conditional.missing_evidence)

    contradictions = sorted(
        (edge.contradiction for edge in edges if edge.contradiction is not None),
        key=lambda item: (item.sequence, item.reason),
    )
    for contradiction in contradictions:
        if any(signal in codes for signal in contradiction.signals):
            matched.append(contradiction.reason)
            contradicting.append(contradiction.reason)

    if not supporting:
        supporting.append(DEFAULT_SUPPORTING)
    if not missing:
        missing.append(DEFAULT_MISSING)
    confidence = "medium" if len(supporting) >= 2 and not contradicting else "low"
    return {
        "cause": cause,
        "cause_type": cause_type,
        "confidence": confidence,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "missing_evidence": missing,
        "recommended_action": action,
        "matched_relation_types": matched,
        "attribution_source": "knowledge_graph_edges",
    }


# 默认边集：与 _ranked_cause 规则级联逐分支对应的参考实现。
# 运行时边集来自各项目知识图谱种子（projects/*/data-ops/graph/graph_seed.json），
# 此处仅作金色对拍基准与新项目编边模板，不直接入库。
DEFAULT_FAULT_EDGES: list[dict[str, Any]] = [
    {
        "relation_type": "fault.pm_cochange",
        "source_name": "PM2.5",
        "target_name": "PM10",
        "attributes": {
            "strength": "hard",
            "violation": {
                "sequence": 1,
                "signals": ["pm_cochange_weak"],
                "reason": "PM2.5 与 PM10 协同关系偏弱",
                "cause": "采样系统或颗粒物监测链路异常",
                "cause_type": "device_or_facility",
                "missing_evidence": ["采样流量、切割头、采样管路和颗粒物仪器维护记录"],
                "action": "优先核查采样流量、采样管路、切割头和颗粒物监测仪运行状态。",
            },
            "contradiction": {
                "sequence": 2,
                "signals": ["pm_cochange_supported"],
                "reason": "PM2.5 与 PM10 协同变化较强，支持真实颗粒物过程",
            },
        },
    },
    {
        "relation_type": "fault.timeseries_continuity",
        "source_name": "主污染物时序",
        "target_name": "数采链路",
        "attributes": {
            "strength": "hard",
            "violation": {
                "sequence": 3,
                "signals": ["main_pollutant_constant_streak"],
                "reason": "主污染物出现长时间恒值，可能存在仪器停滞、数采卡滞或数据刷新异常",
                "cause": "监测仪或数采链路恒值异常",
                "cause_type": "data_quality",
                "missing_evidence": ["分钟级原始数据、数采状态、仪器运行状态和近期质控记录"],
                "action": "优先核查分钟级原始数据、数采链路刷新状态、仪器运行状态和同期质控记录。",
            },
        },
    },
    {
        "relation_type": "fault.single_station_dominance",
        "source_name": "污染事件",
        "target_name": "站点贡献",
        "attributes": {
            "strength": "hard",
            "violation": {
                "sequence": 4,
                "signals": ["single_station_dominant"],
                "reason": "污染事件由单站或少数站点主导",
                "conditional": {
                    "when_codes_subset": ["single_station_dominant", "weather_missing"],
                    "cause": "单站局地影响或数据链路异常待复核",
                    "cause_type": "needs_review",
                    "missing_evidence": [
                        "分钟级原始数据、数采状态、仪器运行状态、站点周边局地源和近期运维记录"
                    ],
                    "action": "先复核同城站点时序和站点周边局地源，再核查分钟级原始数据、数采状态和仪器运行状态。",
                },
            },
        },
    },
    {
        "relation_type": "fault.peer_trend",
        "source_name": "污染事件",
        "target_name": "同城站点趋势",
        "attributes": {
            "strength": "soft",
            "violation": {
                "sequence": 5,
                "signals": ["peer_trend_inconsistent"],
                "reason": "同城站点未出现同步变化",
            },
        },
    },
    {
        "relation_type": "fault.no2_o3_inverse",
        "source_name": "NO2",
        "target_name": "O3",
        "attributes": {
            "strength": "hard",
            "violation": {
                "sequence": 6,
                "signals": ["no2_o3_pattern_weak"],
                "reason": "NO2 与 O3 关系不符合常见反向变化特征",
                "cause": "气态分析仪或校准链路异常",
                "cause_type": "device_or_facility",
                "missing_evidence": ["气态分析仪校准、零跨检查和质控记录"],
                "action": "核查气态分析仪状态、校准记录、零跨检查和采样系统。",
            },
            "contradiction": {
                "sequence": 3,
                "signals": ["no2_o3_inverse_supported"],
                "reason": "NO2 与 O3 关系符合常见反向变化特征",
            },
        },
    },
    {
        "relation_type": "fault.peer_coherence",
        "source_name": "污染事件",
        "target_name": "同城站点一致性",
        "attributes": {
            "strength": "soft",
            "contradiction": {
                "sequence": 1,
                "signals": ["multi_station_coherent"],
                "reason": "同城多站点存在一致变化，削弱单站设备故障判断",
            },
        },
    },
    {
        "relation_type": "fault.meteo_regional",
        "source_name": "污染过程",
        "target_name": "气象与区域一致性",
        "attributes": {
            "strength": "soft",
            "contradiction": {
                "sequence": 4,
                "signals": ["meteorology_supports_pollution", "regional_signal_coherent"],
                "reason": "气象或区域一致性支持真实污染过程",
            },
        },
    },
]


def default_fault_edges() -> list[FaultRelationEdge]:
    """解析默认边集；注册表自检失败属于代码缺陷，直接抛出。"""
    edges, warnings = load_fault_edges(DEFAULT_FAULT_EDGES)
    if warnings:
        raise ValueError(f"默认边集存在非法边：{warnings}")
    return edges
