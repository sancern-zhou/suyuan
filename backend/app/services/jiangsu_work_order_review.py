"""Persistent review records for Jiangsu fault work-order SOP audits."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import fcntl
from functools import wraps
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app.tools.resource_declarations import resources_for_visuals
from app.utils.path_config import get_data_registry, is_path_within, resolve_agent_path

REVIEW_VISUAL_TYPE = "fault_work_order_review"
REVIEW_SCENARIO = "fault_work_order_review"
VALID_SOP_IDS = {"SOP-01", "SOP-02", "SOP-03"}
WORK_ORDER_DECISIONS = {"approve", "reject", "needs_evidence"}
DATA_DECISIONS = {
    "keep",
    "partial_exclude",
    "exclude",
    "missing_no_delete",
    "not_applicable",
    "needs_evidence",
}
GATE_SCOPES = {"core", "supporting", "rebuttal"}
REASONABLENESS_STATUSES = {"pass", "uncertain", "fail"}
TERMINAL_REVIEW_STATUSES = {"archived", "rejected", "needs_evidence"}


def _reviews_dir() -> Path:
    directory = get_data_registry() / "work_order_reviews"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _review_path(review_id: str) -> Path:
    safe_id = _safe_identifier(review_id, "review_id")
    return _reviews_dir() / f"{safe_id}.json"


def _safe_identifier(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text or any(part in text for part in ("/", "\\", "..", "\x00")):
        raise ValueError(f"{name} 无效")
    return text


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_datetime(value: Any, *, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} 不能为空")
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            pass
    raise ValueError(f"{field} 必须是可解析时间")


def _normalise_station(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalise_string_list(value: Any, *, max_items: int = 80) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def _normalise_gate_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        status = str(value.get("status") or value.get("decision") or value.get("result") or "uncertain").strip()
        basis = str(value.get("basis") or value.get("evidence") or value.get("comment") or "").strip()
        missing = _normalise_string_list(value.get("missing_evidence") or value.get("missing"))
        scope = str(value.get("scope") or value.get("evidence_role") or "core").strip().lower()
    else:
        status = str(value or "uncertain").strip()
        basis = ""
        missing = []
        scope = "core"
    if status not in {"pass", "fail", "uncertain", "not_applicable"}:
        status = "uncertain"
    if scope not in GATE_SCOPES:
        scope = "core"
    result: dict[str, Any] = {"status": status}
    if basis:
        result["basis"] = basis
    if missing:
        result["missing_evidence"] = missing
    if scope:
        result["scope"] = scope
    return result


def _normalise_gates(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("gates 必须是对象")
    raw = value
    gates: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key or "").strip()
        if not key:
            raise ValueError("gates 包含空门禁编号")
        if key in gates:
            raise ValueError(f"gates 包含重复门禁编号：{key}")
        gates[key] = _normalise_gate_result(raw_value)
    if not gates:
        raise ValueError("gates 至少需要包含一个门禁结果")
    return gates


def _normalise_data_impact(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("data_impact 必须是数组")
    impacts: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"data_impact[{index}] 必须是对象")
        item = dict(raw)
        decision = str(item.get("decision") or "needs_evidence").strip()
        item["granularity"] = str(item.get("granularity") or "hour").strip()
        if item["granularity"] != "hour":
            raise ValueError(f"data_impact[{index}] 仅允许小时数据审核；5分钟数据仅作分析参考")
        if decision not in DATA_DECISIONS:
            raise ValueError(f"data_impact[{index}].decision 无效")
        item["decision"] = decision
        if decision in {"partial_exclude", "exclude"}:
            if not str(item.get("pollutant") or "").strip():
                raise ValueError(f"data_impact[{index}].pollutant 不能为空")
            if not item.get("start") or not item.get("end"):
                raise ValueError(f"data_impact[{index}] 建议剔除时必须填写明确 start/end")
        if item.get("start") and item.get("end"):
            start = _parse_datetime(item["start"], field=f"data_impact[{index}].start")
            end = _parse_datetime(item["end"], field=f"data_impact[{index}].end")
            if start > end:
                raise ValueError(f"data_impact[{index}] 开始时间不能晚于结束时间")
        impacts.append(item)
    return impacts


def _normalise_reasonableness(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    status = str(raw.get("status") or "uncertain").strip()
    if status not in REASONABLENESS_STATUSES:
        status = "uncertain"
    basis = str(raw.get("basis") or raw.get("comment") or "").strip()
    result: dict[str, Any] = {"status": status}
    if basis:
        result["basis"] = basis
    return result


def _normalise_exclusion_intervals(value: Any, *, exclusion_required: bool) -> list[dict[str, Any]]:
    if value is None:
        intervals: list[Any] = []
    elif isinstance(value, list):
        intervals = value
    else:
        raise ValueError("exclusion_intervals 必须是数组")
    if exclusion_required and not intervals:
        raise ValueError("需要数据剔除时必须填写 exclusion_intervals")

    normalised: list[dict[str, Any]] = []
    for index, raw in enumerate(intervals):
        if not isinstance(raw, dict):
            raise ValueError(f"exclusion_intervals[{index}] 必须是对象")
        item = dict(raw)
        pollutant = str(item.get("pollutant") or "").strip()
        granularity = str(item.get("granularity") or "hour").strip()
        if granularity != "hour":
            raise ValueError(f"exclusion_intervals[{index}] 仅允许小时数据剔除")
        if not pollutant:
            raise ValueError(f"exclusion_intervals[{index}].pollutant 不能为空")
        start = _parse_datetime(item.get("start"), field=f"exclusion_intervals[{index}].start")
        end = _parse_datetime(item.get("end"), field=f"exclusion_intervals[{index}].end")
        if start > end:
            raise ValueError(f"exclusion_intervals[{index}] 开始时间不能晚于结束时间")
        boundary_sources = _normalise_string_list(item.get("boundary_sources"))
        if exclusion_required and not boundary_sources:
            raise ValueError(f"exclusion_intervals[{index}].boundary_sources 不能为空")
        reasonableness = _normalise_reasonableness(item.get("reasonableness_check"))
        if exclusion_required and not reasonableness.get("basis"):
            raise ValueError(f"exclusion_intervals[{index}].reasonableness_check.basis 不能为空")
        item.update({
            "pollutant": pollutant,
            "granularity": granularity,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "boundary_sources": boundary_sources,
            "reasonableness_check": reasonableness,
            "human_confirmed": bool(item.get("human_confirmed") is True),
        })
        normalised.append(item)
    return normalised


def _normalise_agent_exclusion_intervals(
    value: Any,
    *,
    data_impact: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand index-referenced agent intervals against data_impact entries.

    Agents submit ``{data_impact_index, boundary_sources, reasonableness_check}``;
    pollutant/granularity/start/end come from the referenced data_impact item so
    the same boundary is never hand-copied twice.
    """
    if value is None:
        intervals: list[Any] = []
    elif isinstance(value, list):
        intervals = value
    else:
        raise ValueError("exclusion_intervals 必须是数组")
    exclusion_required = any(
        str(item.get("decision") or "") in {"partial_exclude", "exclude"} for item in data_impact
    )
    if exclusion_required and not intervals:
        raise ValueError("需要数据剔除时必须填写 exclusion_intervals")

    normalised: list[dict[str, Any]] = []
    for index, raw in enumerate(intervals):
        if not isinstance(raw, dict):
            raise ValueError(f"exclusion_intervals[{index}] 必须是对象")
        raw_index = raw.get("data_impact_index")
        try:
            ref_index = int(raw_index)
        except (TypeError, ValueError):
            raise ValueError(f"exclusion_intervals[{index}].data_impact_index 必须是整数") from None
        if ref_index < 0 or ref_index >= len(data_impact):
            raise ValueError(
                f"exclusion_intervals[{index}].data_impact_index={ref_index} 超出 data_impact 范围"
            )
        referenced = data_impact[ref_index]
        if str(referenced.get("decision") or "") not in {"partial_exclude", "exclude"}:
            raise ValueError(
                f"exclusion_intervals[{index}].data_impact_index 必须引用 partial_exclude 或 exclude 条目"
            )
        pollutant = str(referenced.get("pollutant") or "").strip()
        if not pollutant or not referenced.get("start") or not referenced.get("end"):
            raise ValueError(
                f"data_impact[{ref_index}] 缺少 pollutant/start/end，不能作为剔除区间"
            )
        boundary_sources = _normalise_string_list(raw.get("boundary_sources"))
        if exclusion_required and not boundary_sources:
            raise ValueError(f"exclusion_intervals[{index}].boundary_sources 不能为空")
        reasonableness = _normalise_reasonableness(raw.get("reasonableness_check"))
        if exclusion_required and not reasonableness.get("basis"):
            raise ValueError(f"exclusion_intervals[{index}].reasonableness_check.basis 不能为空")
        normalised.append({
            "data_impact_index": ref_index,
            "pollutant": pollutant,
            "granularity": str(referenced.get("granularity") or "hour").strip(),
            "station_code": referenced.get("station_code"),
            "device_id": referenced.get("device_id"),
            "start": referenced["start"],
            "end": referenced["end"],
            "boundary_sources": boundary_sources,
            "reasonableness_check": reasonableness,
            "human_confirmed": False,
        })
    if exclusion_required:
        referenced_indexes = {int(item["data_impact_index"]) for item in normalised}
        missing_indexes = [
            index for index, item in enumerate(data_impact)
            if str(item.get("decision") or "") in {"partial_exclude", "exclude"}
            and index not in referenced_indexes
        ]
        if missing_indexes:
            missing_text = "、".join(str(index) for index in missing_indexes)
            raise ValueError(f"每个建议剔除的 data_impact 都必须提供确认区间，缺少索引：{missing_text}")
    return normalised


def _review_digest(payload: dict[str, Any]) -> str:
    identity = {
        "event_id": payload.get("event_id"),
        "work_order_code": payload.get("work_order_code"),
        "evidence_pack_path": payload.get("evidence_pack_path"),
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _new_review_id(payload: dict[str, Any]) -> str:
    digest = _review_digest(payload)
    if payload.get("event_id") or payload.get("work_order_code"):
        return f"jsworev_review_{digest[:20]}"
    return f"jsworev_review_{secrets.token_urlsafe(12)}"


def normalise_review_submission(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the Agent's SOP review output and return a persistent record."""

    if not isinstance(payload, dict):
        raise ValueError("review payload 必须是对象")
    review = deepcopy(payload)
    work_order_code = str(review.get("work_order_code") or "").strip()
    if not work_order_code:
        raise ValueError("work_order_code 不能为空")
    sop_id = str(review.get("sop_id") or "").strip().upper()
    if sop_id not in VALID_SOP_IDS:
        raise ValueError("sop_id 必须为 SOP-01、SOP-02 或 SOP-03")
    decision = str(review.get("work_order_decision") or "needs_evidence").strip()
    if decision not in WORK_ORDER_DECISIONS:
        raise ValueError("work_order_decision 必须为 approve、reject 或 needs_evidence")
    gates = _normalise_gates(review.get("gates"))

    data_impact = _normalise_data_impact(review.get("data_impact"))
    exclusion_required = any(
        str(item.get("decision") or "") in {"partial_exclude", "exclude"} for item in data_impact
    )
    exclusion_intervals = _normalise_agent_exclusion_intervals(
        review.get("exclusion_intervals"),
        data_impact=data_impact,
    )

    warnings: list[str] = []
    if exclusion_required:
        warnings.append("涉及数据剔除候选，归档前必须人工确认异常时间段和合理性。")
    for interval in exclusion_intervals:
        status = (interval.get("reasonableness_check") or {}).get("status")
        if status != "pass":
            warnings.append(
                f"{interval['pollutant']} {interval['start']} 至 {interval['end']} 的剔除合理性为 {status}。"
            )
    if decision == "approve":
        uncertain_gates = [
            key for key, value in gates.items()
            if str(value.get("scope") or "core").strip().lower() == "core"
            and value.get("status") in {"fail", "uncertain"}
        ]
        if uncertain_gates:
            warnings.append("工单建议通过，但存在未通过或不确定的核心门禁：" + "、".join(uncertain_gates))

    now = _now_iso()
    normalised = {
        "review_id": _safe_identifier(_new_review_id(review), "review_id"),
        "schema_version": 1,
        "status": "pending_review",
        "created_at": review.get("created_at") or now,
        "updated_at": now,
        "event_id": str(review.get("event_id") or "").strip(),
        "sop_id": sop_id,
        "work_order_code": work_order_code,
        "station": _normalise_station(review.get("station")),
        "device_id": review.get("device_id"),
        "device_type": review.get("device_type"),
        "pollutants": _normalise_string_list(review.get("pollutants"), max_items=20),
        "qc_event_type": str(review.get("qc_event_type") or "").strip(),
        "transmission_status": str(review.get("transmission_status") or "").strip(),
        "event_type": str(review.get("event_type") or "").strip(),
        "failure_fact": dict(review.get("failure_fact") or {}) if isinstance(review.get("failure_fact"), dict) else {},
        "disposal": dict(review.get("disposal") or {}) if isinstance(review.get("disposal"), dict) else {},
        "recovery": dict(review.get("recovery") or {}) if isinstance(review.get("recovery"), dict) else {},
        "retest": dict(review.get("retest") or {}) if isinstance(review.get("retest"), dict) else {},
        "transmission": dict(review.get("transmission") or {}) if isinstance(review.get("transmission"), dict) else {},
        "gates": gates,
        "data_impact": data_impact,
        "flag_boundary": dict(review.get("flag_boundary") or {}) if isinstance(review.get("flag_boundary"), dict) else {},
        "neighbor_comparison": str(review.get("neighbor_comparison") or "").strip(),
        "exclusion_required": exclusion_required,
        "exclusion_intervals": exclusion_intervals,
        "work_order_decision": decision,
        "evidence_refs": _normalise_string_list(review.get("evidence_refs"), max_items=120),
        "evidence_pack_path": str(review.get("evidence_pack_path") or "").strip(),
        "review_comment": str(review.get("review_comment") or "").strip(),
        "review_summary": str(review.get("review_summary") or "").strip(),
        "audit_warnings": warnings,
        "requires_human_exclusion_confirmation": exclusion_required,
        "human_confirmed": False,
        "history": [{
            "occurred_at": now,
            "action": "agent_review_submitted",
            "event_id": str(review.get("event_id") or "").strip(),
        }],
    }
    return normalised


def save_review(review: dict[str, Any]) -> None:
    target = _review_path(review["review_id"])
    payload = json.dumps(review, ensure_ascii=False, indent=2, default=str)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)


def load_review(review_id: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(_review_path(review_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def load_review_evidence(review_id: str) -> dict[str, Any] | None:
    review = load_review(review_id)
    if review is None:
        return None
    evidence_path = str(review.get("evidence_pack_path") or "").strip()
    if not evidence_path:
        return None
    resolved = resolve_agent_path(evidence_path)
    if not is_path_within(resolved, [get_data_registry()]):
        raise ValueError("evidence_pack_path 不在 data registry 内")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(payload, dict):
        raise ValueError("evidence_pack_path 内容格式无效")
    comparison = payload.get("same_city_monitoring")
    resource = comparison.get("raw_resource") if isinstance(comparison, dict) else None
    if isinstance(resource, dict) and resource.get("path"):
        raw_path = resolve_agent_path(resource["path"])
        if not is_path_within(raw_path, [resolved.parent]):
            raise ValueError("同城原始数据资源不在当前证据包目录内")
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("同城原始数据资源无法读取，请检查证据包资源文件") from exc
        if not isinstance(raw, dict):
            raise ValueError("同城原始数据资源格式无效")
        # The persisted Agent pack stays compact; the review UI needs actual points.
        for key in ("station_hour_raw", "station_hour_audited"):
            dataset = raw.get(key)
            if not isinstance(dataset, dict) or not isinstance(dataset.get("data"), list):
                raise ValueError(f"同城原始数据资源缺少 {key} 数据列表")
            comparison[key] = dataset
    return payload


def list_reviews_for_work_order(work_order_code: str) -> list[dict[str, Any]]:
    code = str(work_order_code or "").strip()
    if not code:
        return []
    reviews: list[dict[str, Any]] = []
    for path in _reviews_dir().glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict) and str(item.get("work_order_code") or "").strip() == code:
            reviews.append(item)
    return sorted(reviews, key=lambda item: str(item.get("updated_at") or ""), reverse=True)


def has_active_review(work_order_code: str) -> bool:
    return any(
        str(item.get("status") or "") not in TERMINAL_REVIEW_STATUSES
        for item in list_reviews_for_work_order(work_order_code)
    )


def create_review_visual(review: dict[str, Any]) -> dict[str, Any]:
    station = review.get("station") or {}
    station_label = station.get("station_name") or station.get("station_code") or review["work_order_code"]
    sop_id = str(review.get("sop_id") or "").strip().upper()
    if sop_id not in VALID_SOP_IDS:
        raise ValueError("sop_id 必须为 SOP-01、SOP-02 或 SOP-03")
    if sop_id == "SOP-03":
        title = f"传输缺失工单审核 · {station_label}"
    elif sop_id == "SOP-02":
        title = f"数据异常工单审核 · {station_label}"
    else:
        title = f"质控工单审核 · {station_label}"
    return {
        "id": f"fault_work_order_review_{review['review_id']}",
        "type": REVIEW_VISUAL_TYPE,
        "title": title,
        "data": {"review": review},
        "meta": {
            "generator": "jiangsu_submit_fault_work_order_review",
            "review_id": review["review_id"],
            "work_order_code": review["work_order_code"],
            "sop_id": sop_id,
            "visual_behavior": REVIEW_VISUAL_TYPE,
        },
    }


def resources_for_review(review: dict[str, Any], *, tool_name: str | None = None) -> list[dict[str, Any]]:
    if tool_name is None:
        tool_name = "jiangsu_submit_fault_work_order_review"
    return resources_for_visuals([create_review_visual(review)], tool_name=tool_name)


def submit_agent_review(payload: dict[str, Any]) -> dict[str, Any]:
    review = normalise_review_submission(payload)
    existing = load_review(review["review_id"])
    if existing and str(existing.get("status") or "") in TERMINAL_REVIEW_STATUSES:
        raise ValueError("审核记录已归档，不能覆盖")
    save_review(review)
    return review


def _locked_review(function):
    @wraps(function)
    def wrapped(review_id, *args, **kwargs):
        with _review_path(review_id).with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return function(review_id, *args, **kwargs)
    return wrapped


@_locked_review
def mark_human_review(
    review_id: str,
    *,
    action: Literal["confirm", "needs_evidence", "reject"],
    actor: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review = load_review(review_id)
    if review is None:
        raise FileNotFoundError("work_order_review_not_found")
    if str(review.get("status") or "") in TERMINAL_REVIEW_STATUSES:
        raise ValueError("审核记录已归档")
    payload = payload or {}
    comment = str(payload.get('review_comment') or payload.get('reason') or '').strip()
    if action == 'needs_evidence':
        action = 'reject'
    if action == 'confirm' and payload.get('final_work_order_decision', 'approve') != 'approve':
        action = 'reject'
    if action == 'reject' and not comment:
        raise ValueError('退回修改必须填写审核意见')
    if len(comment) > 2000:
        raise ValueError('审核意见不能超过 2000 字')
    now = _now_iso()
    final_decision = str(
        payload.get("final_work_order_decision")
        or payload.get("work_order_decision")
        or review.get("work_order_decision")
        or "needs_evidence"
    ).strip()
    final_decision = 'reject' if action == 'reject' else 'approve'
    if final_decision not in WORK_ORDER_DECISIONS:
        raise ValueError("final_work_order_decision 无效")

    final_data_impact = (
        _normalise_data_impact(payload["data_impact"])
        if "data_impact" in payload
        else list(review.get("data_impact") or [])
    )
    exclusion_required = bool(payload.get("exclusion_required") is True) or any(
        str(item.get("decision") or "") in {"partial_exclude", "exclude"} for item in final_data_impact
    ) or bool(review.get("exclusion_required") is True)
    final_intervals = (
        _normalise_exclusion_intervals(
            payload.get("exclusion_intervals"),
            exclusion_required=exclusion_required,
        )
        if "exclusion_intervals" in payload
        else list(review.get("exclusion_intervals") or [])
    )
    if action == "confirm":
        final_data_impact = _normalise_data_impact(final_data_impact)
        final_intervals = _normalise_exclusion_intervals(final_intervals, exclusion_required=exclusion_required)
    if action == "confirm" and exclusion_required:
        if not final_intervals:
            raise ValueError("涉及数据剔除时，归档前必须确认剔除异常时间段")
        for index, interval in enumerate(final_intervals):
            reasonableness = interval.get("reasonableness_check") or {}
            if reasonableness.get("status") not in REASONABLENESS_STATUSES:
                raise ValueError(f"exclusion_intervals[{index}] 缺少合理性判断")
            interval["human_confirmed"] = True

    status = {
        "confirm": "archived",
        "needs_evidence": "needs_evidence",
        "reject": "rejected",
    }[action]
    review.update({
        "status": status,
        "updated_at": now,
        "human_confirmed": True,
        "confirmed_at": now,
        "confirmed_by": actor,
        "final_work_order_decision": final_decision,
        "final_data_impact": final_data_impact,
        "final_exclusion_intervals": final_intervals,
        "human_review_comment": str(payload.get("review_comment") or payload.get("reason") or "").strip(),
    })
    history = list(review.get("history") or [])
    history.append({
        "occurred_at": now,
        "action": f"human_{action}",
        "actor": actor,
        "final_work_order_decision": final_decision,
    })
    review["history"] = history
    # Persist the learning outbox in the same atomic write as the human decision.
    from app.services.jiangsu_review_learning import build_feedback
    review['human_feedback'] = build_feedback(review)
    save_review(review)
    return review
