"""Jiangsu smart-event domain adapter.

The upstream smart-event and rule APIs are still evolving.  This module keeps
the application contract stable and currently builds pending events from the
already available Jiangsu alarm API.  A future platform adapter can replace
the source without changing route or frontend payloads.

Clues of the same site on the same natural day are merged into one stored
event bucket.  Buckets that already carry an AI judgment get a pending delta
plus an incremental task card that continues the previous conversation; the
Agent decides whether the new clues extend the same cause or form a new
event, which decides whether the original task card is refreshed or the
incremental card becomes an independent round.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from app.config.config_manager import config_manager
from app.fetchers.jiangsu_smart_event_evidence import (
    POLLUTANT_FIELDS,
    JiangsuSmartEventEvidenceFetcher,
)
from app.scheduled_tasks.models import TaskEvent
from app.services.jiangsu_smart_event_automation import (
    AUTOMATION_DEFAULTS,
    evidence_signature,
    schedule_retry,
    update_impact_conflict,
    update_initial_assessment,
)
from app.services.jiangsu_smart_event_store import SCHEMA as EVENT_STORE_SCHEMA
from app.services.jiangsu_smart_event_store import JiangsuEventPackages
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
from app.utils.path_config import format_agent_path, get_data_registry, resolve_agent_path

AI_EVENT_TYPES = (
    "疑似雾炮喷淋",
    "疑似人员进入采样区干扰操作",
    "疑似仪器故障",
    "疑似外界环境影响",
    "疑似站房停电",
    "疑似公共系统异常",
    "疑似站房环境影响",
    "合规运维核查",
    "数据异常待研判",
    "其他待人工复核",
)
SMART_EVENT_TRIGGER_TYPES = {
    "供电报警": "jiangsu.smart_event.alarm.power",
    "数采网络报警": "jiangsu.smart_event.alarm.network",
    "站房环境报警": "jiangsu.smart_event.alarm.environment",
    "仪器报警": "jiangsu.smart_event.alarm.instrument",
}
SMART_EVENT_EVENT_TYPE = "jiangsu.smart_event.alarm"
SMART_EVENT_TASK_ID = "jiangsu_smart_event_ai_judgment"
SMART_EVENT_AGENT_MODES = {
    "external": "smart_event_external",
    "environment": "smart_event_external",
    "instrument": "smart_event_instrument",
    "power": "smart_event_instrument",
    "network": "smart_event_instrument",
}


def smart_event_agent_mode(event: dict[str, Any]) -> str:
    """Resolve the dedicated conversational mode for an event clue."""
    trigger = str(event.get("clue_trigger_type") or "").rsplit(".", 1)[-1]
    return SMART_EVENT_AGENT_MODES.get(trigger, "smart_event_external")

CONTINUITY_SAME_CAUSE = "same_cause"
CONTINUITY_NEW_CAUSE = "new_cause"

logger = structlog.get_logger()


def _card_accepts_execution(card: dict[str, Any], attributes: dict[str, Any], started_at: Any) -> bool:
    """Whether a finished execution still belongs to the card's current dispatch.

    The dispatch token identifies one dispatch round. A worker restart resumes
    queued claims from the durable snapshot, which may carry the token of an
    earlier attempt while the card already stores a newer one. Such a resumed
    execution is still the latest activity of the card and must be accepted
    unless the card was re-dispatched after that execution started, in which
    case a newer run supersedes the late result.
    """

    token = (attributes or {}).get("smart_event_dispatch_token")
    if not token or card.get("dispatch_token") == token:
        return True
    dispatched = _parse_time(card.get("dispatched_at"))
    started = _parse_time(started_at)
    if dispatched is None or started is None:
        return False
    local_tz = datetime.now().astimezone().tzinfo
    if dispatched.tzinfo is None:
        dispatched = dispatched.replace(tzinfo=started.tzinfo or local_tz)
    if started.tzinfo is None:
        started = started.replace(tzinfo=dispatched.tzinfo or local_tz)
    return started >= dispatched

JUDGMENT_ANALYSIS_KEYS = (
    "station_series_analysis", "regional_comparison_analysis",
    "data_impact_assessment", "logic_direction_check",
)

# 主线索标签 → V3.0 初始命名词（第 7.2 节命名模板）。
NAMING_LABELS = {
    "供电报警": "供电断数",
    "数采网络报警": "公共系统报警",
    "站房环境报警": "站房环境",
    "仪器报警": "仪器报警",
    # 断数类标签（V3.0 5.4）。
    "站点级断数": "供电断数",
    "多仪器断数": "公共系统报警",
    "单仪器断数": "仪器报警",
    "数据延迟上传": "公共系统报警",
    # 超限类标签（V3.0 5.5）。
    "浓度超限": "超限报警",
    "预警超限": "超限报警",
    "仪器参数超限": "仪器报警",
    # 异常数据类标签（V3.0 5.2）。
    "数据突升": "数据异常",
    "数据突降": "数据异常",
    "离群异常": "数据异常",
    "恒值异常": "数据异常",
    "负值或无效值": "数据异常",
    "逻辑异常": "数据异常",
    # 视频类标签（V3.0 5.1，视频接口接入后生效）。
    "人员进入采样区": "人员进入采样区",
    "接触采样设施": "人员进入采样区",
    "遮挡采样口": "人员进入采样区",
    "雾炮喷淋": "雾炮喷淋",
    "洒水冲洗": "雾炮喷淋",
}

# 合规记录 → 合规标签分类规则（V3.0 5.6，按顺序取第一个命中）。
COMPLIANCE_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("停电通知", ("停电", "供电检修", "电力检修", "ups维护")),
    ("喷淋洒水报备", ("喷淋", "洒水", "冲洗", "降尘", "雾炮")),
    ("校准记录", ("校准", "质控", "标气", "标定", "流量审核", "比对")),
    ("维修记录", ("维修", "更换", "故障处理", "备件", "检修")),
    ("进站记录", ("进站", "巡检", "现场检查", "保养", "例行", "维护")),
)

# 小时浓度超限参考阈值（μg/m³）；CO 上游单位不确定，默认不检测，可通过配置启用。
DEFAULT_HOUR_LIMITS: dict[str, Any] = {
    "SO2": 150, "NO2": 200, "O3": 200, "PM10": 150, "PM2.5": 75, "CO": None,
}

DEFAULT_CONFIG: dict[str, Any] = {
    **AUTOMATION_DEFAULTS,
    "version": 1,
    "event_merge_window_minutes": 60,
    "video_tag_confidence_threshold": 0.7,
    "station_missing_factor_threshold": 2,
    "station_missing_duration_minutes": 5,
    "multi_instrument_threshold": 2,
    "single_instrument_missing_duration_minutes": 5,
    "initial_naming_priority": [
        "人员进入采样区",
        "雾炮喷淋",
        "供电断数",
        "公共系统报警",
        "站房环境",
        "仪器报警",
        "超限报警",
        "数据异常",
    ],
    "ai_event_type_dictionary": list(AI_EVENT_TYPES),
    "data_anomaly_threshold_pct": 20,
    "pm_rise_threshold_pct": 20,
    "pollutant_hour_limits": dict(DEFAULT_HOUR_LIMITS),
}


class SmartEventUpstreamError(RuntimeError):
    """Raised when the current upstream alarm source cannot be queried."""


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %I:%M:%S %p",
        ):
            try:
                parsed = datetime.strptime(str(value).strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _format_time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_event_times(event: dict[str, Any]) -> None:
    """Keep the evidence interval separate from the latest displayed occurrence.

    Retained clues recover starts overwritten by older display-time handling.
    """
    starts = [_parse_time(event.get("event_start_time"))]
    ends = [_parse_time(event.get("event_end_time"))]
    for tag in event.get("clue_tags", []) or []:
        if isinstance(tag, dict) and tag.get("tag_category") != "合规" and tag.get("tag_source") != "合规记录":
            starts.append(_parse_time(tag.get("tag_start_time")))
            ends.append(_parse_time(tag.get("tag_end_time")) or _parse_time(tag.get("tag_start_time")))
    starts = [value for value in starts if value is not None]
    latest = _parse_time(event.get("latest_occurrence_time"))
    if starts:
        event["event_start_time"] = _format_time(min(starts))
        event["latest_occurrence_time"] = _format_time(max(starts + ([latest] if latest else [])))
    ends = [value for value in ends if value is not None] + starts
    if ends:
        event["event_end_time"] = _format_time(max(ends))


def _is_archived(event: dict[str, Any]) -> bool:
    return event.get("archived") is True or event.get("event_status") == "已归档"


def _judged_status(event: dict[str, Any]) -> str:
    return "待归档" if event.get("ai_suggested_level") == "P3" else "待复核"


def _normalize_event_status(event: dict[str, Any]) -> None:
    status = event.get("event_status")
    if _is_archived(event):
        event["archived"] = True
        event["event_status"] = "已归档"
    elif status in {"AI 已研判", "待人工确认", "已确认"}:
        event["event_status"] = _judged_status(event)
    elif status == "派单处置中":
        event["event_status"] = "待反馈"
    elif status == "待重新研判":
        event["event_status"] = "待复核"
    elif status in {"AI 研判中", "AI 研判失败"}:
        event["event_status"] = _judged_status(event) if event.get("ai_event_type") else "未研判"


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _stable_id(record: dict[str, Any]) -> str:
    raw = _first(record, "id", "alarmId", "callId", "uniqueCode")
    if raw not in (None, ""):
        return f"alarm:{raw}"
    material = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return f"alarm:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _alarm_label(record: dict[str, Any]) -> tuple[str, str]:
    rule_type = str(_first(record, "ddRuleType", "ddruletype", "ruleType", "callType") or "").strip()
    text = str(_first(record, "content", "alarmContent", "description") or "平台告警")
    label = rule_type or text[:40] or "平台告警"
    obj = str(_first(record, "deviceName", "device", "objectName") or text[:80] or "告警对象")
    return label, obj


def _primary_tag(tags: list[dict[str, Any]], priority: list[str]) -> dict[str, Any] | None:
    """按初始命名优先级选出主线索标签（同优先级取开始时间更早者）。"""
    best: dict[str, Any] | None = None
    best_key: tuple[Any, ...] | None = None
    for index, tag in enumerate(tags):
        name = str(tag.get("tag_name") or "")
        naming = NAMING_LABELS.get(name, name)
        rank = priority.index(naming) if naming in priority else len(priority)
        start = _parse_time(tag.get("tag_start_time"))
        key = (rank, start is None, start.timestamp() if start else 0.0, index)
        if best_key is None or key < best_key:
            best, best_key = tag, key
    return best


def _initial_event_name(site_name: Any, tag_name: Any) -> str:
    naming = NAMING_LABELS.get(str(tag_name or ""), str(tag_name or "告警"))
    return f"{site_name}{naming}线索待研判事件"


def _bucket_key(event: dict[str, Any]) -> tuple[str, str] | None:
    """同站点 + 事件开始时间所在自然日 构成同日合并键。"""
    site = str(event.get("site_id") or "").strip()
    start = _parse_time(event.get("event_start_time"))
    if not site or start is None:
        return None
    return site, start.astimezone().date().isoformat()


def _event_fingerprint(event: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "site_id": event.get("site_id"),
            "start": event.get("event_start_time"),
            "end": event.get("event_end_time"),
            "tags": sorted(str(tag.get("tag_id")) for tag in event.get("clue_tags", []) or []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _compact_tags(tags: list[dict[str, Any]], *, max_items: int = 30) -> list[dict[str, Any]]:
    """Compact clue tags for inline embedding into evidence packages."""
    if not tags:
        return []
    compact: list[dict[str, Any]] = []
    for tag in tags[:max_items]:
        if not isinstance(tag, dict):
            continue
        compact.append({
            key: (str(value)[:160] if isinstance(value, str) else value)
            for key, value in tag.items()
            if key in {
                "tag_id", "tag_source", "tag_category", "tag_name", "tag_object",
                "tag_start_time", "tag_end_time", "tag_display_text",
            }
        })
    return compact


def _hour_value(record: dict[str, Any], canonical: str) -> float | None:
    aliases = next((fields for name, fields in POLLUTANT_FIELDS if name == canonical), (canonical,))
    for alias in aliases:
        if alias in record:
            raw = record.get(alias)
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return None
            if number != number or number <= -900:
                return None
            return number
    return None


def _detection_tag(
    event_id: str, *, source: str, category: str, name: str, obj: str,
    start: str | None, end: str | None, note: str,
) -> dict[str, Any]:
    tag_id = f"detect:{event_id}:{category}:{name}:{obj}"
    return {
        "tag_id": tag_id,
        "tag_source": source,
        "tag_category": category,
        "tag_name": name,
        "tag_object": obj,
        "tag_start_time": start,
        "tag_end_time": end,
        "tag_confidence": None,
        "clue_id": tag_id,
        "tag_display_text": f"{category}：{name}" + (f"（{note}）" if note else ""),
        "detected": True,
    }


def detect_data_clue_tags(
    event: dict[str, Any], package: dict[str, Any], config: dict[str, Any],
) -> list[dict[str, Any]]:
    """基于证据包小时数据检测断数/超限/异常数据线索标签（V3.0 5.2/5.4/5.5）。

    检测标签的 tag_id 是确定性的：同一事件同一异常只会生成一个标签，
    重复抓取证据不会导致标签无限增长或证据指纹反复失效。
    """
    monitoring = ((package.get("sources") or {}).get("monitoring") or {})
    hour_records = (
        (monitoring.get("data") or {}).get("station_hour") or {}
    ).get("data") if isinstance(monitoring.get("data"), dict) else None
    hour_records = hour_records if isinstance(hour_records, list) else []
    if not hour_records:
        return []
    event_id = str(event.get("event_id"))
    windows = package.get("time_windows") if isinstance(package.get("time_windows"), dict) else {}
    # 检测标签时间锚定事件窗口（告警起止），避免把合并桶的结束时间拉伸到自然日末尾；
    # 旧包回退 day/query 窗口。
    scope = (
        windows.get("event") if isinstance(windows.get("event"), dict) else
        windows.get("day") if isinstance(windows.get("day"), dict) else
        windows.get("query") if isinstance(windows.get("query"), dict) else {}
    )
    start_text, end_text = scope.get("start"), scope.get("end")
    tags: list[dict[str, Any]] = []
    threshold_pct = float(config.get("data_anomaly_threshold_pct") or 20) / 100.0
    limits_raw = config.get("pollutant_hour_limits") if isinstance(config.get("pollutant_hour_limits"), dict) else {}
    limits = {**DEFAULT_HOUR_LIMITS, **limits_raw}

    series: list[tuple[str | None, dict[str, float | None]]] = []
    for record in hour_records:
        if not isinstance(record, dict):
            continue
        time_text = str(record.get("timePoint") or "") or None
        series.append((time_text, {name: _hour_value(record, name) for name, _ in POLLUTANT_FIELDS}))
    if not series:
        return []

    # ---- 断数检测 ----
    station_factor_threshold = int(config.get("station_missing_factor_threshold") or 2)
    multi_threshold = int(config.get("multi_instrument_threshold") or 2)
    per_factor_missing: dict[str, int] = {name: 0 for name, _ in POLLUTANT_FIELDS}
    max_hour_missing_factors = 0
    for _, values in series:
        missing = [name for name, value in values.items() if value is None]
        max_hour_missing_factors = max(max_hour_missing_factors, len(missing))
        for name in missing:
            per_factor_missing[name] += 1
    if max_hour_missing_factors >= station_factor_threshold:
        tags.append(_detection_tag(
            event_id, source="断数报警", category="断数", name="站点级断数",
            obj=str(event.get("site_name") or event.get("site_id") or ""),
            start=start_text, end=end_text,
            note=f"单小时最多 {max_hour_missing_factors} 项污染物同时缺失",
        ))
    elif max_hour_missing_factors >= multi_threshold:
        tags.append(_detection_tag(
            event_id, source="断数报警", category="断数", name="多仪器断数",
            obj=str(event.get("site_name") or event.get("site_id") or ""),
            start=start_text, end=end_text,
            note=f"单小时 {max_hour_missing_factors} 项污染物同时缺失",
        ))
    else:
        for name, missing_hours in per_factor_missing.items():
            if missing_hours > 0:
                tags.append(_detection_tag(
                    event_id, source="断数报警", category="断数", name="单仪器断数",
                    obj=name, start=start_text, end=end_text,
                    note=f"{name} 缺失 {missing_hours} 个小时值",
                ))

    # ---- 超限 / 负值 / 恒值 / 突变检测 ----
    for name, _ in POLLUTANT_FIELDS:
        limit = limits.get(name)
        values = [(time, values.get(name)) for time, values in series]
        present = [(time, value) for time, value in values if value is not None]
        if not present:
            continue
        if limit is not None:
            exceed = [value for _, value in present if value > float(limit)]
            if exceed:
                tags.append(_detection_tag(
                    event_id, source="超限报警", category="超限", name="浓度超限",
                    obj=name, start=start_text, end=end_text,
                    note=f"{name} 最高 {max(exceed):g} 超过阈值 {float(limit):g}",
                ))
        negatives = [value for _, value in present if value < 0]
        if negatives:
            tags.append(_detection_tag(
                event_id, source="异常数据识别", category="数据", name="负值或无效值",
                obj=name, start=start_text, end=end_text,
                note=f"{name} 出现 {len(negatives)} 个负值/无效值",
            ))
        flat_run = 1
        max_flat = 1
        for index in range(1, len(present)):
            if abs(present[index][1] - present[index - 1][1]) < 0.1 and abs(present[index][1]) > 0.1:
                flat_run += 1
                max_flat = max(max_flat, flat_run)
            else:
                flat_run = 1
        if max_flat >= 4:
            tags.append(_detection_tag(
                event_id, source="异常数据识别", category="数据", name="恒值异常",
                obj=name, start=start_text, end=end_text,
                note=f"{name} 连续 {max_flat} 小时几乎不变",
            ))
        for index in range(1, len(present)):
            previous_value = present[index - 1][1]
            current_value = present[index][1]
            delta = abs(current_value - previous_value)
            if delta >= max(threshold_pct * abs(previous_value), 5.0):
                name_text = "数据突升" if current_value > previous_value else "数据突降"
                tags.append(_detection_tag(
                    event_id, source="异常数据识别", category="数据", name=name_text,
                    obj=name, start=present[index][0], end=present[index][0],
                    note=f"{name} 由 {previous_value:g} 变为 {current_value:g}",
                ))
                break

    # ---- 区域离群检测（依赖区域差值，存在时才检测） ----
    comparison = (package.get("sources") or {}).get("comparison")
    deltas = comparison.get("regional_deltas") if isinstance(comparison, dict) else None
    if isinstance(deltas, dict):
        for name, pct in (deltas.get("nearby_station_delta_pct") or {}).items():
            if pct is not None and abs(float(pct)) >= float(config.get("data_anomaly_threshold_pct") or 20):
                delta_value = (deltas.get("nearby_station_delta") or {}).get(name)
                if delta_value is not None and abs(float(delta_value)) >= 5:
                    direction = "高于" if float(delta_value) > 0 else "低于"
                    tags.append(_detection_tag(
                        event_id, source="异常数据识别", category="数据", name="离群异常",
                        obj=name, start=start_text, end=end_text,
                        note=f"{name} 较周边站点{direction} {abs(float(pct)):g}%",
                    ))
    return tags


def normalize_compliance_tag(record: dict[str, Any], *, source_hint: str = "工单") -> dict[str, Any] | None:
    """把运维工单/质控/门禁记录归一为 V3.0 合规线索标签。"""
    if not isinstance(record, dict):
        return None
    text = " ".join(
        str(record.get(key) or "")
        for key in ("orderType", "orderTitle", "title", "missionName", "name", "content", "eventType")
    )
    label = None
    for candidate, keywords in COMPLIANCE_TAG_RULES:
        if any(keyword in text for keyword in keywords):
            label = candidate
            break
    if source_hint == "门禁" and label is None:
        label = "进站记录"
    if label is None:
        return None
    clue_ref = str(
        record.get("workingOrderCode") or record.get("orderCode") or record.get("id")
        or record.get("missionName") or record.get("personName") or label
    )
    occurred = _parse_time(
        record.get("createTime") or record.get("orderTime") or record.get("eventTime")
        or record.get("missionTime") or record.get("timePoint")
    )
    time_text = _format_time(occurred) if occurred else None
    tag_id = f"compliance:{source_hint}:{label}:{clue_ref}"
    note = str(record.get("orderTitle") or record.get("missionName") or record.get("personName") or clue_ref)[:80]
    return {
        "tag_id": tag_id,
        "tag_source": "合规记录",
        "tag_category": "合规",
        "tag_name": label,
        "tag_object": note,
        "tag_start_time": time_text,
        "tag_end_time": time_text,
        "tag_confidence": None,
        "clue_id": tag_id,
        "tag_display_text": f"合规：{label}（{note}）",
        "compliance_source": source_hint,
    }


def normalize_alarm_event(record: dict[str, Any]) -> dict[str, Any]:
    """Map one platform alarm row to the V3 pending-event contract."""

    event_id = _stable_id(record)
    site_id = str(_first(record, "code", "stacode", "stationCode", "station_code", "uniqueCode") or "").strip()
    site_name = str(_first(record, "stationName", "positionName", "name", "siteName") or site_id or "未知站点").strip()
    occurred = _parse_time(_first(record, "alarmtime", "alarmTime", "timePoint", "createTime", "occurredAt"))
    ended = _parse_time(_first(record, "alarmendtime", "alarmEndTime", "endTime", "resolvedAt")) or occurred
    start = _format_time(occurred)
    end = _format_time(ended)
    label, obj = _alarm_label(record)
    alarm_content = str(_first(record, "content", "alarmContent", "description") or "").strip()
    rule_type = str(_first(record, "ddRuleType", "ddruletype", "ruleType") or "").strip() or None
    tag = {
        "tag_id": f"{event_id}:alarm",
        "tag_source": "子站报警",
        "tag_category": "报警",
        "tag_name": label,
        "tag_object": obj,
        "tag_start_time": start,
        "tag_end_time": end,
        "tag_confidence": None,
        "clue_id": str(_first(record, "id", "alarmId", "callId") or event_id),
        "tag_display_text": f"报警：{label}（{alarm_content[:120]}）" if alarm_content else f"报警：{label}",
    }
    detail = alarm_content[:160] if alarm_content else label
    initial_name = _initial_event_name(site_name, label)
    return {
        "event_id": event_id,
        "site_id": site_id,
        "site_name": site_name,
        "city_name": _first(record, "cityName", "city", "city_name"),
        "district_name": _first(record, "districtName", "district", "district_name"),
        "event_start_time": start,
        "latest_occurrence_time": start,
        "event_end_time": end,
        "initial_event_name": initial_name,
        "event_name": initial_name,
        "event_status": "未研判",
        "event_type": "待 AI 研判",
        "source_alarm_rule_type": rule_type,
        "alarm_content": alarm_content or None,
        "source_alarm_state": _first(record, "ddalarmstateName", "ddalarmstate", "alarmState"),
        "event_trigger_type": SMART_EVENT_EVENT_TYPE,
        "clue_trigger_type": SMART_EVENT_TRIGGER_TYPES.get(label, SMART_EVENT_EVENT_TYPE),
        "clue_tags": [tag],
        "primary_clue_tag": label,
        "clue_count": 1,
        "merged_alarm_ids": [event_id],
        "ai_event_type": None,
        "ai_event_name": None,
        "ai_data_impact": "待确认",
        "system_data_impact": "待确认",
        "data_impact": "待确认",
        "ai_task_priority": "normal",
        "ai_suggested_level": None,
        "ai_diagnosis_note": None,
        "manual_final_event_type": None,
        "manual_final_level": None,
        "archived": False,
        "operation_records": [],
        "evidence": {"alarm": record, "alarms": [record]},
        "source": "alarm_adapter",
    }


class JiangsuSmartEventService:
    """Application service for the staged smart-event integration."""

    # Routes build a fresh service per request, so the in-flight background
    # sync is tracked on the class and shared by every instance of the
    # process.  The store on disk remains the only authoritative state.
    _background_sync_task: asyncio.Task | None = None
    _background_sync_started_at: datetime | None = None

    def __init__(
        self,
        alarm_tool: JiangsuAlarmRecordsTool | None = None,
        *,
        data_root: Path | None = None,
        evidence_fetcher: JiangsuSmartEventEvidenceFetcher | None = None,
    ):
        self.alarm_tool = alarm_tool or JiangsuAlarmRecordsTool()
        self.data_root = data_root or get_data_registry()
        self.evidence_fetcher = evidence_fetcher or JiangsuSmartEventEvidenceFetcher()

    @property
    def config_path(self) -> Path:
        return self.data_root / "jiangsu_smart_events" / "config.json"

    @property
    def store_path(self) -> Path:
        return self.data_root / "jiangsu_smart_events" / "store.json"

    @property
    def packages(self) -> JiangsuEventPackages:
        return JiangsuEventPackages(self.store_path)

    def _evidence_package_path(self, event_id: str) -> Path:
        if self._db_mode():
            from app.db.sync_bridge import run_db
            from app.services.smart_event_db import get_evidence_path_async

            reference = run_db(get_evidence_path_async(str(event_id)))
            if reference:
                return resolve_agent_path(reference)
        manifest = self.packages.read_manifest()
        if manifest.get("schema_version") == EVENT_STORE_SCHEMA:
            row = next((item for item in manifest.get("events", []) if item.get("event_id") == event_id), None)
            if row:
                detail = json.loads(resolve_agent_path(row["_detail_ref"]).read_text(encoding="utf-8"))
                if detail.get("_evidence_ref"):
                    return resolve_agent_path(detail["_evidence_ref"])
        safe_id = hashlib.sha256(str(event_id).encode("utf-8")).hexdigest()[:24]
        return self.data_root / "jiangsu_smart_events" / "evidence" / f"{safe_id}.json"

    def _db_mode(self) -> bool:
        from app.services.smart_event_db import smart_event_db_enabled

        return smart_event_db_enabled()

    @property
    def list_index_path(self) -> Path:
        return self.store_path.with_name("list-index.json")

    def _store_revision(self) -> list[int] | None:
        try:
            stat = self.store_path.stat()
            return [stat.st_ino, stat.st_size, stat.st_mtime_ns]
        except FileNotFoundError:
            return None

    @staticmethod
    def _with_review_states(store):
        from app.services.task_review import load_reviews
        review_ids = [event["review_id"] for event in store.get("events", []) if event.get("review_id")]
        reviews = load_reviews(dict.fromkeys(review_ids))
        for event in store.get("events", []):
            _normalize_event_times(event)
            _normalize_event_status(event)
            if not event.get("review_id"):
                continue
            review = reviews.get(event["review_id"])
            if review is None:
                raise ValueError("event_review_record_missing")
            if _is_archived(event) or review["status"] == "archived":
                event["archived"] = True
                event["event_status"] = "已归档"
            elif review["status"] == "in_disposal":
                if event.get("event_status") != "已反馈":
                    event["event_status"] = "待反馈"
            elif review["status"] == "rejected":
                event["event_status"] = "待复核"
        return store

    @staticmethod
    def _event_summary(item: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "event_id", "event_name", "initial_event_name", "event_status", "event_type",
            "site_id", "site_name", "event_start_time", "event_end_time", "latest_occurrence_time", "alarm_content", "clue_tags",
            "primary_clue_tag", "source_alarm_rule_type", "pending_delta", "archived",
            "ai_event_type", "ai_data_impact", "ai_suggested_level", "clue_count", "review_id",
            "system_data_impact", "data_impact", "ai_task_priority", "data_impact_basis",
            "data_impact_conflict", "data_impact_conflict_note",
        }
        return {**{key: item[key] for key in fields if key in item},
                "has_judgment": item.get("has_judgment", bool((item.get("ai_judgment") or {}).get("final_response")))}

    def _write_list_index(self, store: dict[str, Any], revision: list[int] | None) -> dict[str, Any]:
        index = {
            "schema_version": 4,
            "store_revision": revision,
            "events": [self._event_summary(item) for item in store.get("events", []) if isinstance(item, dict)],
            "tasks": store.get("tasks", []),
            "last_sync": store.get("last_sync"),
        }
        self.list_index_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".list-index.", suffix=".tmp", dir=self.list_index_path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(index, handle, ensure_ascii=False, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.list_index_path)
        finally:
            temporary.unlink(missing_ok=True)
        return index

    def _load_list_store(self) -> dict[str, Any]:
        """Read only the small index; rebuild once for legacy/external writers.

        The revision belongs to the authoritative store, so a worker update
        invalidates an old index across processes without any browser cache.
        """
        if self._db_mode():
            return self._load_store()
        revision = self._store_revision()
        try:
            index = json.loads(self.list_index_path.read_text(encoding="utf-8"))
            if (index.get("schema_version") == 4
                    and index.get("store_revision") == revision
                    and isinstance(index.get("events"), list)
                    and isinstance(index.get("tasks"), list)):
                return self._with_review_states(index)
        except (OSError, ValueError, AttributeError):
            pass
        for _ in range(3):
            revision = self._store_revision()
            manifest = self.packages.read_manifest()
            store = manifest if manifest.get("schema_version") == EVENT_STORE_SCHEMA else self._load_store()
            if revision == self._store_revision():
                return self._with_review_states(self._write_list_index(store, revision))
        raise RuntimeError("smart_event_store_changed_during_index_rebuild")

    def _load_store(self, *, event_ids: set[str] | None = None) -> dict[str, Any]:
        if self._db_mode():
            from app.db.sync_bridge import run_db
            from app.services.smart_event_db import load_store_async

            store = run_db(load_store_async(event_ids=event_ids))
            return self._with_review_states(store)
        manifest = self.packages.read_manifest()
        if manifest.get("schema_version") == EVENT_STORE_SCHEMA:
            return self._with_review_states(self.packages.load(event_ids=event_ids))
        if self.store_path.is_file():
            try:
                value = json.loads(self.store_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    value.setdefault("events", [])
                    value.setdefault("tasks", [])
                    changed = False
                    legacy_triggers = set(SMART_EVENT_TRIGGER_TYPES.values())
                    for event in value["events"]:
                        if not isinstance(event, dict):
                            continue
                        trigger = event.get("event_trigger_type")
                        if trigger in legacy_triggers:
                            event.setdefault("clue_trigger_type", trigger)
                            event["event_trigger_type"] = SMART_EVENT_EVENT_TYPE
                            changed = True
                    for task in value["tasks"]:
                        if not isinstance(task, dict) or task.get("task_type") != "ai_judgment":
                            continue
                        if task.get("scheduled_task_id") != SMART_EVENT_TASK_ID:
                            task["scheduled_task_id"] = SMART_EVENT_TASK_ID
                            changed = True
                        if task.get("event_trigger_type") in legacy_triggers:
                            task["event_trigger_type"] = SMART_EVENT_EVENT_TYPE
                            changed = True
                    if self._migrate_same_day_store(value):
                        changed = True
                    if changed:
                        self._save_store(value)
                    return self._with_review_states(value)
            except (OSError, ValueError):
                pass
        return {"schema_version": "jiangsu_smart_events/v1", "events": [], "tasks": []}

    def _save_store(self, store: dict[str, Any]) -> None:
        if self._db_mode():
            from app.db.sync_bridge import run_db
            from app.services.smart_event_db import save_store_async

            run_db(save_store_async(store))
            return
        packages = self.packages
        manifest = packages.save(store)
        self._write_list_index(manifest, packages.last_revision)

    async def aload_store(self, *, event_ids: set[str] | None = None) -> dict[str, Any]:
        """Off-loop `_load_store` for callers running on an event loop."""
        return await asyncio.to_thread(self._load_store, event_ids=event_ids)

    async def asave_store(self, store: dict[str, Any]) -> None:
        """Off-loop `_save_store` for callers running on an event loop."""
        await asyncio.to_thread(self._save_store, store)

    @staticmethod
    def _filter_events(
        events: list[dict[str, Any]], *, status: str | None, keyword: str | None, limit: int
    ) -> list[dict[str, Any]]:
        filtered = events
        if status:
            filtered = [item for item in filtered if item.get("event_status") == status]
        if keyword:
            needle = keyword.strip().lower()
            filtered = [item for item in filtered if needle in json.dumps(item, ensure_ascii=False).lower()]
        filtered = sorted(
            filtered,
            key=lambda item: (parsed.timestamp() if (parsed := _parse_time(item.get("latest_occurrence_time") or item.get("event_start_time"))) else float("-inf")),
            reverse=True,
        )
        return filtered[:limit]

    async def _fetch_alarm_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None,
        limit: int,
    ) -> dict[str, Any]:
        result = await self.alarm_tool.execute(
            station_codes=station_codes,
            station_type="省控" if not station_codes else None,
            start_time=start_time,
            end_time=end_time,
            max_result_count=min(limit, 100),
            sorting="timePoint",
        )
        if not result.get("success"):
            raise SmartEventUpstreamError(str(result.get("summary") or "告警接口查询失败"))
        invalid_states = {"撤销", "驳回", "无效", "取消", "已撤销", "已驳回", "已取消", "cancelled", "canceled", "revoked", "rejected", "invalid"}
        events = [normalize_alarm_event(row) for row in result.get("data", []) if isinstance(row, dict)
                  and not any(str(row.get(key) or "").strip().lower() in invalid_states
                              for key in ("status", "state", "alarmState", "alarmStatus"))]
        if not station_codes:
            for event in events:
                event["station_type"] = "省控"
        return {
            "events": events,
            "source_metadata": result.get("metadata") or {},
        }

    @staticmethod
    def _bucket_judged(event: dict[str, Any]) -> bool:
        """事件是否已有可延续的 AI 研判结论。"""
        judgment = event.get("ai_judgment")
        if isinstance(judgment, dict) and judgment.get("final_response"):
            return True
        return bool(event.get("ai_event_type")) or event.get("event_status") in {"AI 已研判", "待人工确认", "已确认"}

    def _naming_priority(self) -> list[str]:
        config = self.load_config()
        priority = config.get("initial_naming_priority")
        return [str(item) for item in priority] if isinstance(priority, list) else []

    def _hydrate_evidence(self, *events: dict[str, Any]) -> None:
        """Load heavy legacy evidence payloads for lightweight-loaded events."""
        lazy = [event for event in events if isinstance(event, dict) and event.pop("_evidence_lazy", None)]
        if not lazy or not self._db_mode():
            return
        from app.db.sync_bridge import run_db
        from app.services.smart_event_db import load_evidence_async

        mapping = run_db(load_evidence_async([str(event["event_id"]) for event in lazy]))
        for event in lazy:
            record = mapping.get(str(event["event_id"]))
            if record is not None:
                event["evidence"] = record

    def _merge_event_into(self, target: dict[str, Any], donor: dict[str, Any]) -> list[str]:
        """把 donor 事件的线索并入已匹配的 target 事件桶，返回新增 tag_id 列表。"""
        self._hydrate_evidence(target, donor)
        self._ensure_not_archived(target)
        now = datetime.now().astimezone().isoformat()
        new_ids: list[str] = []
        tags = {item.get("tag_id"): item for item in target.get("clue_tags", []) if isinstance(item, dict)}
        for tag in donor.get("clue_tags", []) or []:
            if not isinstance(tag, dict) or not tag.get("tag_id") or tag["tag_id"] in tags:
                continue
            tags[tag["tag_id"]] = tag
            new_ids.append(str(tag["tag_id"]))
        target["clue_tags"] = list(tags.values())
        target["clue_count"] = len(target["clue_tags"])
        for field in ("event_start_time", "event_end_time"):
            current = _parse_time(target.get(field))
            incoming = _parse_time(donor.get(field))
            if incoming is None:
                continue
            if current is None or (incoming < current if field == "event_start_time" else incoming > current):
                target[field] = _format_time(incoming)
        _normalize_event_times(target)
        target["merged_alarm_ids"] = list(dict.fromkeys(
            [str(target.get("event_id"))]
            + [str(item) for item in (target.get("merged_alarm_ids") or [])]
            + [str(donor.get("event_id"))]
            + [str(item) for item in (donor.get("merged_alarm_ids") or [])]
        ))
        evidence = target.setdefault("evidence", {})
        alarms: dict[str, Any] = {}
        for record in (evidence.get("alarms") or []) + (donor.get("evidence", {}).get("alarms") or []):
            if isinstance(record, dict):
                key = hashlib.sha256(
                    json.dumps(record, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
                alarms[key] = record
        donor_alarm = donor.get("evidence", {}).get("alarm")
        if isinstance(donor_alarm, dict):
            evidence.setdefault("alarm", donor_alarm)
        if alarms:
            evidence["alarms"] = list(alarms.values())
        for field in ("alarm_content", "source_alarm_state", "source_alarm_rule_type", "city_name", "district_name"):
            if donor.get(field) not in (None, ""):
                target[field] = donor.get(field)
        target.setdefault("operation_records", []).extend(donor.get("operation_records") or [])
        if self._bucket_judged(donor):
            if not self._bucket_judged(target):
                for field in (
                    "ai_judgment", "ai_event_type", "ai_event_name", "ai_data_impact",
                    "ai_suggested_level", "ai_diagnosis_note", "manual_confirmation",
                    "manual_final_event_type", "manual_final_level", "judged_clue_ids",
                    "event_name", "event_status",
                ):
                    if donor.get(field) not in (None, "", [], {}):
                        target[field] = donor.get(field)
            else:
                donor_judgment = donor.get("ai_judgment")
                if isinstance(donor_judgment, dict) and donor_judgment.get("final_response"):
                    history = target.setdefault("judgment_history", [])
                    history.append({
                        "round": len(history) + 1,
                        "task_id": donor_judgment.get("task_id"),
                        "final_response": donor_judgment.get("final_response"),
                        "completed_at": donor_judgment.get("completed_at"),
                        "archived_at": now,
                        "reason": "merged_from_same_day_event",
                    })
        if not self._bucket_judged(target):
            primary = _primary_tag(target.get("clue_tags", []), self._naming_priority())
            if primary is not None:
                target["primary_clue_tag"] = primary.get("tag_name")
                target["initial_event_name"] = _initial_event_name(target.get("site_name"), primary.get("tag_name"))
                target["event_name"] = target["initial_event_name"]
        target["updated_at"] = now
        return new_ids

    def _attach_tags_to_bucket(
        self, store: dict[str, Any], bucket: dict[str, Any], tags: list[dict[str, Any]],
        *, actor: dict[str, Any] | None = None,
    ) -> list[str]:
        """把线索标签挂靠到已有事件桶；返回新增 tag_id 列表。

        合规记录与数据检测线索不单独创建事件（V3.0 6.3），只挂靠到同站点
        同日已有桶；已研判桶挂靠新标签会记录 pending_delta 并按需创建增量卡。
        """
        if not tags or _is_archived(bucket):
            return []
        now = datetime.now().astimezone().isoformat()
        existing = {item.get("tag_id") for item in bucket.get("clue_tags", [])}
        new_tags = [tag for tag in tags if tag.get("tag_id") and tag["tag_id"] not in existing]
        if not new_tags:
            return []
        bucket["clue_tags"] = list(bucket.get("clue_tags", [])) + new_tags
        bucket["clue_count"] = len(bucket["clue_tags"])
        for field in ("event_start_time", "event_end_time"):
            for tag in new_tags:
                if tag.get("tag_category") == "合规" or tag.get("tag_source") == "合规记录":
                    continue
                incoming = _parse_time(tag.get("tag_start_time") if field == "event_start_time" else tag.get("tag_end_time"))
                if incoming is None:
                    continue
                current = _parse_time(bucket.get(field))
                if current is None or (incoming < current if field == "event_start_time" else incoming > current):
                    bucket[field] = _format_time(incoming)
        _normalize_event_times(bucket)
        bucket["updated_at"] = now
        if not self._bucket_judged(bucket):
            primary = _primary_tag(bucket.get("clue_tags", []), self._naming_priority())
            if primary is not None:
                bucket["primary_clue_tag"] = primary.get("tag_name")
                bucket["initial_event_name"] = _initial_event_name(bucket.get("site_name"), primary.get("tag_name"))
                bucket["event_name"] = bucket["initial_event_name"]
            return [tag["tag_id"] for tag in new_tags]
        delta = bucket.get("pending_delta") if isinstance(bucket.get("pending_delta"), dict) else {}
        clue_ids = list(dict.fromkeys(
            [str(item) for item in delta.get("clue_ids") or []] + [tag["tag_id"] for tag in new_tags]
        ))
        bucket["pending_delta"] = {
            "clue_ids": clue_ids,
            "marked_at": delta.get("marked_at") or now,
            "updated_at": now,
        }
        bucket_id = str(bucket.get("event_id"))
        cards = [
            item for item in store.get("tasks", [])
            if item.get("event_id") == bucket_id and item.get("task_type") == "ai_judgment"
        ]
        if not any(item.get("status") in {"待执行", "待调度", "执行中"} for item in cards):
            base = next((item for item in reversed(cards) if item.get("status") == "已完成"), None)
            task = self._create_ai_task(bucket, actor=actor, base_task=base, reason="merged_new_clues")
            store.setdefault("tasks", []).append(task)
        return [tag["tag_id"] for tag in new_tags]

    def _migrate_same_day_store(self, store: dict[str, Any]) -> bool:
        """把历史“一条告警一个事件”的存量数据合并为同站点同日事件桶。"""
        events = [item for item in store.get("events", []) if isinstance(item, dict)]
        if not events:
            return False
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        kept: list[dict[str, Any]] = []
        merged_any = False
        for event in events:
            if event.get("archived") is True or event.get("event_status") == "已归档":
                kept.append(event)
                continue
            key = _bucket_key(event)
            target = buckets.get(key) if key else None
            if target is None:
                if key is not None:
                    buckets[key] = event
                kept.append(event)
                continue
            self._merge_event_into(target, event)
            for card in store.get("tasks", []):
                if isinstance(card, dict) and str(card.get("event_id")) == str(event.get("event_id")):
                    card["event_id"] = target.get("event_id")
                    card["merged_from_event_id"] = event.get("event_id")
            merged_any = True
        if merged_any:
            store["events"] = kept
        return merged_any

    def _create_ai_task(
        self, event: dict[str, Any], *, actor: dict[str, Any] | None = None,
        base_task: dict[str, Any] | None = None, reason: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().astimezone().isoformat()
        task_id = f"task:{uuid4().hex}"
        task = {
            "task_id": task_id,
            "event_id": event["event_id"],
            "task_type": "ai_judgment",
            "scheduled_task_id": SMART_EVENT_TASK_ID,
            "event_type": event.get("primary_clue_tag"),
            "event_trigger_type": event.get("event_trigger_type"),
            "title": f"AI研判：{event.get('event_name') or event.get('initial_event_name')}",
            "status": "待执行",
            "conversation_id": f"conversation:{uuid4().hex}",
            "created_at": now,
            "updated_at": now,
            "created_by": actor or {"user_id": "system", "username": "system"},
            "context": {
                "event_id": event["event_id"],
                "event_name": event.get("event_name"),
                "clue_tags": event.get("clue_tags", []),
                "clue_type": event.get("primary_clue_tag"),
                "clue_count": event.get("clue_count"),
            },
        }
        if base_task is not None:
            task["conversation_id"] = base_task.get("conversation_id") or task["conversation_id"]
            task["rerun_of_task_id"] = base_task.get("task_id")
            task["continuity"] = {
                "mode": "incremental",
                "base_task_id": base_task.get("task_id"),
                "reason": reason or "merged_new_clues",
            }
            task["title"] = f"AI增量研判：{event.get('event_name') or event.get('initial_event_name')}"
            pending = event.get("pending_delta")
            if isinstance(pending, dict):
                task["context"]["pending_delta"] = pending
        return task

    def _upsert_events(
        self, incoming: list[dict[str, Any]], *, actor: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
        """Upsert alarm clues into same-site same-day event buckets.

        One platform alarm is one clue; clues of the same site on the same
        natural day are folded into a single stored event.  When new clues
        land on an already-judged bucket, a pending delta is recorded and an
        incremental AI task card reuses the previous conversation.
        """
        store = self._load_store()
        existing = {str(item.get("event_id")): item for item in store.get("events", []) if isinstance(item, dict)}
        tasks = [item for item in store.get("tasks", []) if isinstance(item, dict)]
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for item in existing.values():
            if item.get("archived") is True or item.get("event_status") == "已归档":
                continue
            key = _bucket_key(item)
            if key is not None and key not in buckets:
                buckets[key] = item
        owners = {alias: item for item in existing.values()
                  for alias in [str(item["event_id"]), *map(str, item.get("merged_alarm_ids") or [])]}
        created_tasks: list[dict[str, Any]] = []
        created_event_ids: list[str] = []
        merged_event_ids: list[str] = []
        now = datetime.now().astimezone().isoformat()
        for candidate in incoming:
            event_id = str(candidate["event_id"])
            current = owners.get(event_id)
            if current is not None and (current.get("archived") is True or current.get("event_status") == "已归档"):
                continue
            key = _bucket_key(candidate)
            bucket = current if current is not None else (buckets.get(key) if key else None)
            new_tag_ids: list[str] = []
            if bucket is None:
                candidate["created_at"] = now
                candidate["updated_at"] = now
                existing[event_id] = candidate
                if key is not None:
                    buckets[key] = candidate
                created_event_ids.append(event_id)
                bucket = candidate
            else:
                new_tag_ids = self._merge_event_into(bucket, candidate)
                if new_tag_ids:
                    merged_event_ids.append(str(bucket.get("event_id")))
            owners[event_id] = bucket
            bucket_id = str(bucket.get("event_id"))
            cards = [
                item for item in tasks
                if item.get("event_id") == bucket_id and item.get("task_type") == "ai_judgment"
            ]
            if new_tag_ids and self._bucket_judged(bucket):
                delta = bucket.get("pending_delta") if isinstance(bucket.get("pending_delta"), dict) else {}
                clue_ids = list(dict.fromkeys([str(i) for i in delta.get("clue_ids") or []] + new_tag_ids))
                bucket["pending_delta"] = {
                    "clue_ids": clue_ids,
                    "marked_at": delta.get("marked_at") or now,
                    "updated_at": now,
                }
                bucket["updated_at"] = now
                has_active_card = any(item.get("status") in {"待执行", "待调度", "执行中"} for item in cards)
                if not has_active_card:
                    base = next((item for item in reversed(cards) if item.get("status") == "已完成"), None)
                    task = self._create_ai_task(bucket, actor=actor, base_task=base, reason="merged_new_clues")
                    tasks.append(task)
                    created_tasks.append(task)
                continue
            has_ai_task = bool(cards)
            if not has_ai_task:
                task = self._create_ai_task(bucket, actor=actor)
                tasks.append(task)
                created_tasks.append(task)
        store["events"] = list(existing.values())
        store["tasks"] = tasks
        store["updated_at"] = now
        self._save_store(store)
        return store, created_tasks, created_event_ids, merged_event_ids

    async def _collect_event_evidence(
        self, store: dict[str, Any], events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Attach bounded evidence packages without publishing AI tasks."""
        if not events:
            return {"collected": 0, "failed": 0}
        config = self.load_config()
        stored_by_id = {
            str(item.get("event_id")): item
            for item in store.get("events", [])
            if isinstance(item, dict) and item.get("event_id")
        }
        semaphore = asyncio.Semaphore(3)

        async def collect(candidate: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
            event_id = str(candidate.get("event_id") or "")
            snapshot = deepcopy(stored_by_id.get(event_id, candidate))
            fingerprint = _event_fingerprint(snapshot)
            async with semaphore:
                try:
                    package = await self.evidence_fetcher.fetch(
                        snapshot, config=config
                    )
                except Exception as exc:  # noqa: BLE001 - keep event visible with a gap
                    package = {
                        "schema_version": "jiangsu_smart_event_evidence/v1",
                        "event_id": event_id,
                        "status": "failed",
                        "gaps": [{"source": "collector", "status": "failed", "reason": str(exc)}],
                    }
                return event_id, fingerprint, package

        results = await asyncio.gather(*(collect(event) for event in events))
        # Collection yields to other requests. Preserve judgments, feedback,
        # and newly merged clues written while upstream evidence was fetched.
        store.clear()
        store.update(await self.aload_store(event_ids={event_id for event_id, _, _ in results}))
        stored_by_id = {
            str(item.get("event_id")): item
            for item in store.get("events", []) if isinstance(item, dict)
        }
        failed = 0
        collected = 0
        for event_id, fingerprint, package in results:
            target = stored_by_id.get(event_id)
            if target is None or _is_archived(target):
                continue
            unchanged = _event_fingerprint(target) == fingerprint
            if not unchanged and not self._needs_event_evidence(target):
                # A newer collection already covers the merged event.
                continue
            old_package = target.get("evidence_package") or {}
            evidence_changed = bool(old_package.get("sources")) and evidence_signature(old_package) != evidence_signature(package)
            collected += 1
            target["evidence_checked_at"] = datetime.now().astimezone().isoformat()
            detected = []
            target["evidence_package"] = package
            target.setdefault("evidence", {})["package"] = package
            target["updated_at"] = datetime.now().astimezone().isoformat()
            if package.get("status") in {"success", "partial"}:
                # 证据就绪后基于小时数据检测断数/超限/异常线索并挂靠回事件桶；
                # 检测标签具有确定性 tag_id，随后再计算证据指纹避免反复失效。
                detected = detect_data_clue_tags(target, package, self.load_config())
                if detected:
                    self._attach_tags_to_bucket(
                        store, target, detected,
                        actor={"user_id": "system", "username": "data-detection"},
                    )
                    package["detected_clue_tags"] = _compact_tags(detected)
                # 记录证据指纹；事件窗口或线索变化后指纹失效，触发重新抓取。
                target["evidence_fingerprint"] = _event_fingerprint(target) if unchanged else fingerprint
            else:
                target.pop("evidence_fingerprint", None)
            update_initial_assessment(target, package, detected)
            target["evidence_signature"] = evidence_signature(package)
            if evidence_changed and self._bucket_judged(target) and package.get("status") in {"success", "partial"}:
                target.setdefault("pending_delta", {}).update({"evidence_changed": True,
                    "updated_at": datetime.now().astimezone().isoformat()})
            if package.get("status") == "failed":
                failed += 1
        if results:
            store["updated_at"] = datetime.now().astimezone().isoformat()
            await self.asave_store(store)
        return {"collected": collected, "failed": failed}

    @staticmethod
    def _needs_event_evidence(event: dict[str, Any]) -> bool:
        if event.get("archived") is True or event.get("event_status") == "已归档":
            return False
        package = event.get("evidence_package")
        return (
            not isinstance(package, dict)
            or package.get("status") not in {"success", "partial"}
            or event.get("evidence_fingerprint") != _event_fingerprint(event)
        )

    async def collect_event_evidence(self, event_id: str) -> dict[str, Any]:
        """Collect and persist the evidence package for one stored event."""
        store = self._load_store(event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        result = await self._collect_event_evidence(store, [event])
        return {"event": self._stored_event(store, event_id), **result}

    async def collect_all_event_evidence(self, *, limit: int = 100) -> dict[str, Any]:
        """Collect missing, failed, or stale evidence for active events."""
        store = self._load_store()
        candidates = [
            item for item in store.get("events", [])
            if isinstance(item, dict) and self._needs_event_evidence(item)
        ][:limit]
        result = await self._collect_event_evidence(store, candidates)
        return {"events": [self._stored_event(store, item["event_id"]) for item in candidates], **result}

    def _continuity_context(self, event: dict[str, Any], card: dict[str, Any]) -> dict[str, Any] | None:
        """为增量研判任务组装上一轮结论 + 新增线索/反馈上下文。"""
        continuity = card.get("continuity") if isinstance(card.get("continuity"), dict) else {}
        if continuity.get("mode") != "incremental":
            return None
        pending = event.get("pending_delta") if isinstance(event.get("pending_delta"), dict) else {}
        delta_ids = {str(item) for item in pending.get("clue_ids") or []}
        new_tags = [
            tag for tag in event.get("clue_tags", []) or []
            if str(tag.get("tag_id")) in delta_ids
        ]
        feedback = continuity.get("feedback") if isinstance(continuity.get("feedback"), dict) else None
        previous = event.get("ai_judgment") if isinstance(event.get("ai_judgment"), dict) else {}
        if feedback and feedback.get("source") == "review_reject":
            instruction = (
                "本次为人工审核退回后的增量研判：审核员已退回上一轮结论并给出人工判定意见（见 feedback 字段）。"
                "人工判定意见是权威基准，优先于上一轮 AI 推断与证据包缺口："
                "除非存在与人工判定直接矛盾且确凿的新证据（须在人工复核建议中逐条列明分歧依据），"
                "否则必须按人工判定意见更新事件类型、数据影响、建议等级与结论，并同步更新 event_type、event_name 等结论字段；"
                "不得因证据不足而维持“数据异常待研判”或“其他待人工复核”等待定类型。"
                "输出更新后的完整研判结论；新结论将替换上一轮结论。"
            )
        elif feedback:
            instruction = (
                "本次为事件反馈后的增量研判：运维或现场人员已提交处理反馈（见 feedback 字段）。"
                "反馈是现场一手事实，优先于上一轮 AI 推断：以反馈确认的事件类型、根因和处理结果为基准，"
                "重新选择事件类型并更新数据影响、建议等级与结论字段；"
                "不得仅因证据包存在缺口而维持“数据异常待研判”或“其他待人工复核”等待定类型。"
                "反馈与证据包明显矛盾时仍按反馈更新结论，并在人工复核建议中说明分歧证据。"
                "输出更新后的完整研判结论；新结论将替换上一轮结论。"
            )
        else:
            instruction = (
                "本次为增量研判：事件在上一轮研判后又合并了新线索。请先阅读上一轮研判结论和新增线索，"
                "判断新增线索与上一轮事件是否同一原因；"
                "在通用提交 sections 中用 same_cause 字段记录 true、false 或待确认，并用 continuity_basis 说明依据；不同原因仍归并在本事件，"
                "再基于合并后的完整事件与证据包输出覆盖全部线索的完整研判结论，不得丢弃历史线索。"
            )
        return {
            "mode": "incremental",
            "reason": continuity.get("reason"),
            "base_task_id": continuity.get("base_task_id"),
            "conversation_continued": True,
            "previous_final_response": previous.get("final_response"),
            "previous_judgment": previous or None,
            "previous_manual_confirmation": event.get("manual_confirmation") or None,
            "new_clue_tags": new_tags,
            "new_clue_count": len(new_tags),
            "feedback": feedback,
            "instruction": instruction,
        }

    async def _dispatch_pending_tasks(
        self, store: dict[str, Any], *, wait: bool = False,
        event_ids: set[str] | None = None,
        task_ids: set[str] | None = None,
        force_retry: bool = False,
    ) -> list[dict[str, Any]]:
        """Publish smart events to the real event-triggered task service."""

        try:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
        except (RuntimeError, ImportError) as exc:
            return [{"status": "not_dispatched", "reason": str(exc)}]

        events = {item.get("event_id"): item for item in store.get("events", [])}
        outcomes: list[dict[str, Any]] = []
        changed = False
        for queued in list(store.get("tasks", [])):
            card = next((item for item in store.get("tasks", []) if item.get("task_id") == queued.get("task_id")), queued)
            if task_ids is not None and card.get("task_id") not in task_ids:
                continue
            if card.get("task_type") != "ai_judgment" or card.get("status") not in {"待执行", "待调度"}:
                continue
            if event_ids is not None and str(card.get("event_id")) not in event_ids:
                continue
            event = events.get(card.get("event_id"))
            if not event or _is_archived(event) or not event.get("event_trigger_type"):
                continue
            package_path = self._evidence_package_path(str(event["event_id"]))
            package = json.loads(await asyncio.to_thread(package_path.read_text, encoding="utf-8"))
            if str(package.get("event_id")) != str(event["event_id"]):
                raise ValueError("smart_event_evidence_identity_mismatch")
            package_ref = format_agent_path(package_path)
            continuity = self._continuity_context(event, card)
            card["dispatch_token"] = uuid4().hex
            card["dispatched_at"] = datetime.now().astimezone().isoformat()
            task_event = TaskEvent(
                event_id=str(event["event_id"]),
                event_type=SMART_EVENT_EVENT_TYPE,
                occurred_at=_parse_time(event.get("event_start_time")) or datetime.now().astimezone(),
                attributes={
                    "agent_mode": smart_event_agent_mode(event),
                    "smart_event_id": event["event_id"],
                    "smart_event_task_id": card["task_id"],
                    "smart_event_dispatch_token": card["dispatch_token"],
                    "ai_task_priority": event.get("ai_task_priority", "normal"),
                    "smart_event_type": event.get("primary_clue_tag"),
                    "clue_type": event.get("primary_clue_tag"),
                    "site_id": event.get("site_id"),
                    "site_name": event.get("site_name"),
                    "continuity_mode": continuity.get("mode") if continuity else None,
                    "evidence_package_id": event.get("evidence_package", {}).get("collected_at") if isinstance(event.get("evidence_package"), dict) else None,
                    "evidence_package_path": package_ref,
                },
                payload={
                    "evidence_package_path": package_ref,
                    "smart_event": self._event_summary(event),
                    "evidence_event_id": event["event_id"],
                    "evidence_instruction": "仅使用本任务 evidence_package_path 指定的独立证据包。先校验包内 event_id 与 smart_event.event_id 一致；不一致立即停止。不得读取全局 store.json 或其他事件目录。大证据按 sources 分节读取，不将截断内容当完整证据。",
                    "continuity_context": continuity,
                },
            )
            card["input_clue_ids"] = [str(tag.get("tag_id")) for tag in event.get("clue_tags", [])]
            card["input_evidence_signature"] = event.get("evidence_signature") or evidence_signature(package)
            card["status"] = "执行中"
            card["updated_at"] = datetime.now().astimezone().isoformat()
            await self.asave_store(store)
            try:
                retry_options = {"force_retry": True} if force_retry else {}
                dispatch = await task_service.publish_event(task_event, wait=wait, **retry_options)
                latest = await self.aload_store(event_ids={str(event["event_id"])})
                latest_card = next((item for item in latest.get("tasks", []) if item.get("task_id") == card.get("task_id")), None)
                if latest_card:
                    store.clear()
                    store.update(latest)
                    card = latest_card
                if not dispatch.accepted_task_ids and card.get("status") == "执行中":
                    schedule_retry(card, self.load_config(), error="任务未接收：重复执行或没有匹配任务")
                card["dispatch_status"] = "accepted" if dispatch.accepted_task_ids else "duplicate_or_unmatched"
                card["scheduled_task_ids"] = list(dispatch.accepted_task_ids or dispatch.matched_task_ids)
                card["execution_ids"] = list(dispatch.execution_ids)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], **dispatch.model_dump(mode="json")})
            except Exception as exc:  # noqa: BLE001 - keep the event visible for retry
                latest = await self.aload_store(event_ids={str(event["event_id"])})
                card = next(item for item in latest["tasks"] if item["task_id"] == card["task_id"])
                store.clear()
                store.update(latest)
                schedule_retry(card, self.load_config(), error=str(exc))
                card["dispatch_status"] = "failed"
                card["dispatch_error"] = str(exc)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], "status": "failed", "error": str(exc)})
        if changed:
            store["updated_at"] = datetime.now().astimezone().isoformat()
            await self.asave_store(store)
        return outcomes

    async def sync_alarm_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None = None,
        actor: dict[str, Any] | None = None,
        limit: int = 100,
        wait_for_ai: bool = False,
        dispatch_ai: bool = True,
        fetch_evidence: bool = True,
    ) -> dict[str, Any]:
        fetched = await self._fetch_alarm_events(
            start_time=start_time, end_time=end_time, station_codes=station_codes, limit=limit
        )
        store, created_tasks, created_event_ids, merged_event_ids = await asyncio.to_thread(
            self._upsert_events, fetched["events"], actor=actor
        )
        evidence_result = {"collected": 0, "failed": 0}
        if fetch_evidence:
            alarm_ids = {str(item["event_id"]) for item in fetched["events"]}
            # Collect each persisted bucket once, including when this sync
            # contains only donor alarms merged into an older event ID.
            candidates = [
                item for item in store.get("events", [])
                if (
                    str(item["event_id"]) in alarm_ids
                    or alarm_ids.intersection(item.get("merged_alarm_ids") or [])
                )
                and self._needs_event_evidence(item)
            ]
            evidence_result = await self._collect_event_evidence(store, candidates)
        dispatches = await self._dispatch_pending_tasks(store, wait=wait_for_ai) if dispatch_ai else []
        store["last_sync"] = {
            "source": "alarm_adapter",
            "station_type": "省控" if not station_codes else None,
            "window": [start_time, end_time],
            "event_count": len(fetched["events"]),
            "new_event_count": len(created_event_ids),
            "new_event_ids": created_event_ids,
            "merged_event_count": len(merged_event_ids),
            "merged_event_ids": merged_event_ids,
            "source_metadata": fetched["source_metadata"],
            "synced_at": datetime.now().astimezone().isoformat(),
        }
        await self.asave_store(store)
        return {
            "events": fetched["events"],
            "stored_event_count": len(store.get("events", [])),
            "created_tasks": created_tasks,
            "merged_event_count": len(merged_event_ids),
            "dispatches": dispatches,
            "ai_dispatch_skipped": not dispatch_ai,
            "evidence": evidence_result,
            "source_metadata": fetched["source_metadata"],
        }

    async def sync_compliance_clues(
        self, *, date: str | None = None, actor: dict[str, Any] | None = None,
        fetch_evidence: bool = True,
    ) -> dict[str, Any]:
        """把同站点同日的运维工单/质控/门禁记录挂靠为合规线索标签。

        合规记录只挂靠已有事件桶，不单独触发事件生成（V3.0 6.3）。
        """
        store = self._load_store()
        day_text = (date or "").strip() or datetime.now().astimezone().date().isoformat()
        try:
            day = datetime.fromisoformat(day_text).date()
        except ValueError:
            return {"status": "invalid_date", "attached": 0, "stations": 0}
        buckets_by_site: dict[str, list[dict[str, Any]]] = {}
        for event in store.get("events", []):
            if not isinstance(event, dict) or event.get("archived") is True or event.get("event_status") == "已归档":
                continue
            key = _bucket_key(event)
            if key is None or key[1] != day.isoformat():
                continue
            buckets_by_site.setdefault(key[0], []).append(event)
        if not buckets_by_site:
            return {"status": "no_buckets", "attached": 0, "stations": 0, "date": day_text}
        station_codes = list(buckets_by_site)
        day_start = datetime.combine(day, datetime.min.time()).astimezone().isoformat()
        day_end = datetime.combine(day, datetime.max.time().replace(microsecond=0)).astimezone().isoformat()
        clues: list[tuple[str, dict[str, Any]]] = []

        async def collect_orders() -> None:
            try:
                result = await self.evidence_fetcher.work_order_tool.execute(
                    station_codes=list(station_codes),
                    start_time=day_start,
                    end_time=day_end,
                    workflow_statuses=["ToAssign", "ToAccept", "Doing", "Finish"],
                    order_statuses=["Wait", "Doing", "Finish"],
                    fetch_all=True,
                    page_size=50,
                )
            except Exception:  # noqa: BLE001 - 合规挂靠失败不阻塞告警同步
                return
            for row in (result.get("data") or []) if isinstance(result, dict) else []:
                station = str(row.get("stationCode") or row.get("code") or "").strip()
                tag = normalize_compliance_tag(row, source_hint="工单")
                if station and tag:
                    clues.append((station, tag))

        async def collect_qc() -> None:
            try:
                result = await self.evidence_fetcher.qc_history_tool.execute(
                    station_codes=list(station_codes),
                    start_time=day_start,
                    end_time=day_end,
                )
            except Exception:  # noqa: BLE001
                return
            for row in (result.get("data") or []) if isinstance(result, dict) else []:
                station = str(row.get("stationCode") or row.get("code") or "").strip()
                tag = normalize_compliance_tag(row, source_hint="质控")
                if station and tag:
                    clues.append((station, tag))

        async def collect_doors() -> None:
            for station in station_codes:
                try:
                    result = await self.evidence_fetcher.legacy_adapter.door_records(
                        station_code=station, start_time=day_start, end_time=day_end
                    )
                except Exception:  # noqa: BLE001
                    continue
                rows = (result.get("data") or []) if isinstance(result, dict) else []
                seen: set[str] = set()
                for row in rows:
                    person = str(row.get("personName") or "").strip()
                    if not person or (person, station) in seen:
                        continue
                    seen.add((person, station))
                    tag = normalize_compliance_tag(row, source_hint="门禁")
                    if tag:
                        clues.append((station, tag))

        await asyncio.gather(collect_orders(), collect_qc(), collect_doors())
        store = await self.aload_store()
        buckets_by_site = {}
        for event in store.get("events", []):
            if not isinstance(event, dict) or event.get("archived") is True or event.get("event_status") == "已归档":
                continue
            key = _bucket_key(event)
            if key and key[1] == day.isoformat():
                buckets_by_site.setdefault(key[0], []).append(event)
        attached = 0
        attached_sites: set[str] = set()
        for station, tag in clues:
            for bucket in buckets_by_site.get(station, []):
                added = self._attach_tags_to_bucket(
                    store, bucket, [tag], actor=actor or {"user_id": "system", "username": "compliance-sync"}
                )
                if added:
                    attached += len(added)
                    attached_sites.add(station)
        now = datetime.now().astimezone().isoformat()
        store["last_compliance_sync"] = {
            "date": day_text,
            "clue_count": len(clues),
            "attached_count": attached,
            "stations": len(station_codes),
            "synced_at": now,
        }
        store["updated_at"] = now
        await self.asave_store(store)
        candidates = [
            bucket for buckets in buckets_by_site.values() for bucket in buckets
            if self._needs_event_evidence(bucket)
        ]
        evidence_result = await self._collect_event_evidence(store, candidates) if fetch_evidence else {"collected": 0, "failed": 0}
        return {
            "status": "synced",
            "date": day_text,
            "clues": len(clues),
            "attached": attached,
            "stations": len(station_codes),
            "attached_sites": sorted(attached_sites),
            "evidence": evidence_result,
        }

    def start_background_sync(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None = None,
        limit: int = 100,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger one non-blocking alarm sync shared by all requests.

        The store keeps the authoritative state, so the page can render the
        stored events immediately and pick up new events once this task (or
        the hourly fetcher) has finished.
        """

        cls = type(self)
        running = cls._background_sync_task
        if running is not None and not running.done():
            return {
                "in_progress": True,
                "started_at": _format_time(cls._background_sync_started_at),
                "triggered": False,
            }
        cls._background_sync_started_at = datetime.now().astimezone()
        cls._background_sync_task = asyncio.create_task(self._run_background_sync(
            start_time=start_time,
            end_time=end_time,
            station_codes=station_codes,
            limit=limit,
            actor=actor,
        ))
        return {
            "in_progress": True,
            "started_at": _format_time(cls._background_sync_started_at),
            "triggered": True,
        }

    async def _run_background_sync(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None,
        limit: int,
        actor: dict[str, Any] | None,
    ) -> None:
        try:
            await self.sync_alarm_events(
                start_time=start_time,
                end_time=end_time,
                station_codes=station_codes,
                limit=limit,
                actor=actor or {"user_id": "system", "username": "smart-event-sync"},
                dispatch_ai=False,
                fetch_evidence=True,
            )
        except Exception as exc:  # noqa: BLE001 - surface the gap through last_sync
            self._record_sync_failure(start_time, end_time, str(exc))

    def _record_sync_failure(self, start_time: str, end_time: str, error: str) -> None:
        store = self._load_store()
        previous = store.get("last_sync") if isinstance(store.get("last_sync"), dict) else {}
        now = datetime.now().astimezone().isoformat()
        store["last_sync"] = {
            **previous,
            "source": "alarm_adapter",
            "window": [start_time, end_time],
            "error": error,
            "failed_at": now,
        }
        store["updated_at"] = now
        self._save_store(store)

    @classmethod
    def background_sync_status(cls) -> dict[str, Any]:
        task = cls._background_sync_task
        return {
            "in_progress": task is not None and not task.done(),
            "started_at": _format_time(cls._background_sync_started_at),
        }

    async def _list_events_from_db(self, *, start_time, end_time, station_codes, status,
                                   keyword, event_type, level, limit, page, sync_state) -> dict[str, Any] | None:
        from app.db.sync_bridge import run_db_async
        from app.services import smart_event_db

        if not smart_event_db.smart_event_db_enabled():
            return None

        async def overview_query(current_page):
            return await run_db_async(smart_event_db.query_events_overview_async(
                start_time=time_lo, end_time=time_hi, station_codes=station_codes,
                status=status, keyword=keyword, event_type=event_type, level=level,
                limit=limit, offset=(current_page - 1) * limit,
            ))

        try:
            time_lo, time_hi = _parse_time(start_time), _parse_time(end_time)
            page = max(1, page)
            overview = await overview_query(page)
            events, total = overview["events"], overview["total"]
            if not events and total > 0 and page > 1:
                page = max(1, min(page, max(1, (total + limit - 1) // limit)))
                overview = await overview_query(page)
                events = overview["events"]
            last_sync = overview.get("last_sync")
            last_sync = last_sync if isinstance(last_sync, dict) else None
            upstream_error = str(last_sync.get("error")) if last_sync and last_sync.get("error") else None
            return {
                "events": [self._event_summary(item) for item in events],
                "total": total,
                "page": page,
                "page_size": limit,
                "stats": overview["stats"],
                "filters": overview["filters"],
                "source": "alarm_adapter_store_stale" if upstream_error else "alarm_adapter_store",
                "source_metadata": {
                    "store_path": str(self.store_path),
                    "upstream_error": upstream_error,
                    "last_sync": last_sync,
                    "sync": {
                        "in_progress": sync_state["in_progress"],
                        "started_at": sync_state["started_at"],
                    },
                },
                "capabilities": {
                    "platform_event_api": False,
                    "alarm_adapter": True,
                    "event_store": True,
                    "task_cards": True,
                    "upstream_available": upstream_error is None,
                    "ai_judgment": True,
                    "event_driven_tasks": True,
                    "task_history_learning": True,
                    "alarm_scope": "省控",
                    "unscoped_upstream_query": True,
                    "operations": True,
                    "manual_confirmation": True,
                    "archive_lock": True,
                    "same_day_merge": True,
                    "incremental_judgment": True,
                },
            }
        except Exception:
            logger.exception("smart_event_db_list_failed")
            return None

    async def list_events(
        self,
        *,
        start_time: str,
        end_time: str,
        station_codes: list[str] | None = None,
        status: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        refresh: bool = True,
        page: int = 1,
        summary: bool = False,
        event_type: str | None = None,
        level: str | None = None,
    ) -> dict[str, Any]:
        sync_state = self.background_sync_status()
        if refresh and not summary:
            sync_state = self.start_background_sync(
                start_time=start_time,
                end_time=end_time,
                station_codes=station_codes,
                limit=100,
            )
        if summary:
            db_result = await self._list_events_from_db(
                start_time=start_time, end_time=end_time, station_codes=station_codes,
                status=status, keyword=keyword, event_type=event_type, level=level,
                limit=limit, page=page, sync_state=sync_state,
            )
            if db_result is not None:
                return db_result
        store = await asyncio.to_thread(self._load_list_store) if summary else self._load_store()
        last_sync = store.get("last_sync") if isinstance(store.get("last_sync"), dict) else None
        upstream_error = str(last_sync.get("error")) if last_sync and last_sync.get("error") else None
        events = self._filter_events(
            [item for item in store.get("events", []) if isinstance(item, dict)],
            status=status,
            keyword=None if summary else keyword,
            limit=len(store.get("events", [])),
        )
        all_events = [item for item in store.get("events", []) if isinstance(item, dict)]
        if event_type:
            events = [item for item in events if (item.get("ai_event_type") or item.get("event_type")) == event_type]
        if level:
            events = [item for item in events if str(item.get("ai_suggested_level") or "") == level]
        if summary:
            # summary 数据源为本地 store，时间条件在此统一过滤（与上游同步窗口无关）。
            # 缺少可解析时间的事件不受窗口排除，保持列表契约稳定。
            time_lo = _parse_time(start_time)
            time_hi = _parse_time(end_time)
            if time_lo or time_hi:
                events = [
                    item for item in events
                    if not (parsed := _parse_time(item.get("latest_occurrence_time") or item.get("event_start_time")))
                    or ((not time_lo or parsed >= time_lo) and (not time_hi or parsed <= time_hi))
                ]
        if summary and keyword:
            needle = keyword.strip().lower()
            search_fields = ("event_id", "event_name", "initial_event_name", "site_name", "site_id", "primary_clue_tag", "source_alarm_rule_type")
            events = [item for item in events if needle in " ".join(str(item.get(key) or "") for key in search_fields).lower()]
        total = len(events)
        page = max(1, min(page, max(1, (total + limit - 1) // limit)))
        events = events[(page - 1) * limit:page * limit]
        if summary:
            events = [self._event_summary(item) for item in events]
        return {
            "events": events,
            "total": total,
            "page": page,
            "page_size": limit,
            "stats": {
                "total": len(all_events),
                "pending": sum(not item.get("has_judgment", bool((item.get("ai_judgment") or {}).get("final_response"))) for item in all_events),
                "stations": len({item.get("site_id") or item.get("site_name") for item in all_events}),
            },
            "filters": {
                "statuses": sorted({item["event_status"] for item in all_events if item.get("event_status")}),
                "types": sorted({item.get("ai_event_type") or item.get("event_type") for item in all_events if item.get("ai_event_type") or item.get("event_type")}),
                "levels": sorted({item["ai_suggested_level"] for item in all_events if item.get("ai_suggested_level")}),
            },
            "source": "alarm_adapter_store_stale" if upstream_error else "alarm_adapter_store",
            "source_metadata": {
                "store_path": str(self.store_path),
                "upstream_error": upstream_error,
                "last_sync": last_sync,
                "sync": {
                    "in_progress": sync_state["in_progress"],
                    "started_at": sync_state["started_at"],
                },
            },
            "capabilities": {
                "platform_event_api": False,
                "alarm_adapter": True,
                "event_store": True,
                "task_cards": True,
                "upstream_available": upstream_error is None,
                "ai_judgment": True,
                "event_driven_tasks": True,
                "task_history_learning": True,
                "alarm_scope": "省控",
                "unscoped_upstream_query": True,
                "operations": True,
                "manual_confirmation": True,
                "archive_lock": True,
                "same_day_merge": True,
                "incremental_judgment": True,
            },
        }

    def _hydrate_evidence_package(self, event: dict[str, Any]) -> dict[str, Any]:
        """DB 主模式下事件只存证据 stub，详情读取时从本地证据文件回填完整包。"""
        package = event.get("evidence_package")
        reference = package.get("persisted_path") if isinstance(package, dict) else None
        if not reference or "sources" in package:
            return event
        event_id = str(event.get("event_id"))
        try:
            full = self.packages.read_evidence_package(str(reference), event_id)
        except (OSError, ValueError):
            logger.warning(
                "smart_event_evidence_hydrate_failed",
                event_id=event_id,
                reference=str(reference),
            )
            return event
        full.setdefault("persisted_path", str(reference))
        event["evidence_package"] = full
        return event

    async def get_event(self, event_id: str, **query: Any) -> dict[str, Any] | None:
        store = await asyncio.to_thread(self._load_store, event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is not None:
            self._hydrate_evidence_package(event)
        return event

    def list_tasks(self, *, event_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if self._db_mode():
            from app.db.sync_bridge import run_db
            from app.services.smart_event_db import list_tasks_async

            return run_db(list_tasks_async(event_id=event_id, status=status, limit=limit))
        tasks = [item for item in self._load_list_store().get("tasks", []) if isinstance(item, dict)]
        if event_id:
            tasks = [item for item in tasks if item.get("event_id") == event_id]
        if status:
            tasks = [item for item in tasks if item.get("status") == status]
        return tasks[:limit]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if self._db_mode():
            from app.db.sync_bridge import run_db
            from app.services.smart_event_db import get_task_by_id_async

            return run_db(get_task_by_id_async(task_id))
        return next((item for item in self.list_tasks(limit=1000) if item.get("task_id") == task_id), None)

    @staticmethod
    def _stored_event(store: dict[str, Any], event_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in store.get("events", []) if isinstance(item, dict) and item.get("event_id") == event_id),
            None,
        )

    @staticmethod
    def _append_operation(
        event: dict[str, Any], *, action: str, actor: dict[str, Any], summary: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "operation_id": f"operation:{uuid4().hex}",
            "action": action,
            "summary": summary,
            "actor": actor,
            "created_at": datetime.now().astimezone().isoformat(),
            "details": details or {},
        }
        event.setdefault("operation_records", []).append(record)
        return record

    @staticmethod
    def _ensure_not_archived(event: dict[str, Any]) -> None:
        if event.get("archived") is True or event.get("event_status") == "已归档":
            raise ValueError("smart_event_archived")

    def record_operation(
        self, event_id: str, *, action: str, summary: str, actor: dict[str, Any],
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        store = self._load_store(event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        record = self._append_operation(event, action=action, actor=actor, summary=summary, details=details)
        now = datetime.now().astimezone().isoformat()
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return record

    def dispatch_order(
        self, event_id: str, *, title: str, order_type: str | None = None,
        assignee: str | None = None, description: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """提交派单处置：事件进入“待反馈”并保留工单信息。"""
        store = self._load_store(event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        if event.get("event_status") not in {"待复核", "已反馈"}:
            raise ValueError("smart_event_dispatch_not_allowed")
        order_title = str(title or "").strip()
        if not order_title:
            raise ValueError("dispatch_order_title_required")
        now = datetime.now().astimezone().isoformat()
        self._append_operation(
            event,
            action="dispatch_order",
            actor=actor or {"user_id": "system", "username": "system"},
            summary=f"派单处置：{order_title}",
            details={
                "order_type": str(order_type or "").strip() or None,
                "assignee": str(assignee or "").strip() or None,
                "title": order_title,
                "description": str(description or "").strip() or None,
            },
        )
        event["event_status"] = "待反馈"
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return event

    def _record_feedback(
        self, event_id: str, *, feedback: str, attachments: list[str] | None = None,
        actor: dict[str, Any] | None = None, source: str = "manual",
        human_decision: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """落盘一次反馈并排队增量研判卡；不在当前进程派发，Web/Worker 均可调用。"""
        store = self._load_store(event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        if event.get("event_status") not in {"待复核", "待反馈", "已反馈"}:
            raise ValueError("smart_event_feedback_not_allowed")
        feedback_text = str(feedback or "").strip()
        if not feedback_text:
            raise ValueError("feedback_required")
        attachment_names = [str(item).strip()[:200] for item in (attachments or []) if str(item).strip()][:20]
        now = datetime.now().astimezone().isoformat()
        summary_prefix = "收到审核退回反馈" if source == "review_reject" else "收到事件反馈"
        details: dict[str, Any] = {"feedback": feedback_text, "attachments": attachment_names, "source": source}
        if human_decision:
            details["human_decision"] = human_decision
        self._append_operation(
            event,
            action="event_feedback",
            actor=actor or {"user_id": "system", "username": "system"},
            summary=f"{summary_prefix}：{feedback_text[:120]}",
            details=details,
        )
        event["event_status"] = "已反馈"
        event["updated_at"] = now
        cards = [
            item for item in store.get("tasks", [])
            if item.get("event_id") == event_id and item.get("task_type") == "ai_judgment"
        ]
        feedback_payload: dict[str, Any] = {
            "feedback": feedback_text,
            "attachments": attachment_names,
            "submitted_at": now,
            "source": source,
        }
        if human_decision:
            feedback_payload["human_decision"] = human_decision
        incremental_task = None
        pending_card = next(
            (item for item in reversed(cards) if item.get("status") in {"待执行", "待调度"}), None
        )
        if pending_card is not None:
            # 已有待执行增量卡（如新线索合并触发）：把反馈并入该卡，不重复排队。
            if isinstance(pending_card.get("continuity"), dict):
                pending_card["continuity"]["feedback"] = feedback_payload
                incremental_task = pending_card
        elif not any(item.get("status") == "执行中" for item in cards):
            base = next((item for item in reversed(cards) if item.get("status") == "已完成"), None)
            incremental_task = self._create_ai_task(event, actor=actor, base_task=base, reason="feedback")
            if isinstance(incremental_task.get("continuity"), dict):
                incremental_task["continuity"]["feedback"] = feedback_payload
            store.setdefault("tasks", []).append(incremental_task)
        store["updated_at"] = now
        self._save_store(store)
        return event, incremental_task

    def queue_review_reject_feedback(
        self, event_id: str, *, feedback: str, actor: dict[str, Any] | None = None,
        human_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """审核退回自动触发的增量研判：以人工判定为基准继续上一轮会话。

        仅落一张“待执行”增量卡，不在当前进程派发；worker 每分钟一次的
        自动化队列 tick 会领取并派发，因此 Web 进程（审核接口所在）调用
        是安全的。人工判定意见通过 ``continuity.feedback`` 进入增量指令，
        AI 必须以其为权威基准更新结论。
        """
        _, incremental_task = self._record_feedback(
            event_id, feedback=feedback, actor=actor,
            source="review_reject", human_decision=human_decision,
        )
        return incremental_task

    async def submit_feedback(
        self, event_id: str, *, feedback: str, attachments: list[str] | None = None,
        actor: dict[str, Any] | None = None, dispatch: bool = True,
    ) -> dict[str, Any]:
        """记录事件反馈，并以增量对话继续上一轮 AI 研判。

        反馈是增量对话：反馈内容作为新增输入推送给上一轮研判会话，Agent
        输出的更新结论会替换上一轮 ``ai_judgment``（旧结论进入
        ``judgment_history``），完成后事件状态回到“已反馈”。
        """
        event, incremental_task = self._record_feedback(
            event_id, feedback=feedback, attachments=attachments, actor=actor,
        )
        dispatches: list[dict[str, Any]] = []
        if dispatch and incremental_task is not None:
            dispatches = await self._dispatch_pending_tasks(
                self._load_store(event_ids={event_id}), event_ids={event_id},
                # Feedback is a deliberate continuation of the completed
                # event round. Reopen the event claim so the scheduler does
                # not mistake it for a duplicate initial judgment.
                force_retry=True,
            )
        latest_store = self._load_store(event_ids={event_id})
        latest_event = self._stored_event(latest_store, event_id) or event
        latest_task = next(
            (item for item in latest_store.get("tasks", []) if item.get("task_id") == (incremental_task or {}).get("task_id")),
            incremental_task,
        )
        return {"event": latest_event, "task": latest_task, "dispatches": dispatches}

    def create_task(self, event_id: str, *, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        store = self._load_store(event_ids={event_id})
        event = next((item for item in store.get("events", []) if item.get("event_id") == event_id), None)
        if event is None:
            raise KeyError(event_id)
        task = self._create_ai_task(event, actor=actor)
        store.setdefault("tasks", []).append(task)
        store["updated_at"] = datetime.now().astimezone().isoformat()
        self._save_store(store)
        return task

    async def run_ai_judgment(
        self, event_id: str, *, actor: dict[str, Any] | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Manually trigger a FRESH AI judgment round (new conversation).

        Evidence is collected when events are stored or clues are merged.
        A manual click only dispatches the event Agent using stored evidence
        and starts a brand-new round: a new conversation is used, stale pending
        cards (including merge-triggered incremental cards) are cancelled,
        and the previous conclusion is superseded into judgment_history when
        the new round completes.  First-time judgments simply reuse their
        pending card.  Feedback rounds continue the conversation instead and
        are created by ``submit_feedback``.
        """
        store = self._load_store(event_ids={event_id})
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        package = event.get("evidence_package")
        cards = [
            item for item in store.get("tasks", [])
            if item.get("event_id") == event_id and item.get("task_type") == "ai_judgment"
        ]
        running = next((item for item in reversed(cards) if item.get("status") == "执行中"), None)
        task = None
        if running is not None:
            task = running
        else:
            if not self._bucket_judged(event):
                task = next(
                    (item for item in reversed(cards) if item.get("status") in {"待执行", "待调度"}),
                    None,
                )
            if task is None:
                if self._bucket_judged(event):
                    # 重新研判：不在之前的会话继续，上一轮结论由新一轮完成后替换。
                    stamp = datetime.now().astimezone().isoformat()
                    for item in cards:
                        if item.get("status") in {"待执行", "待调度"}:
                            item["status"] = "已取消"
                            item["updated_at"] = stamp
                task = self._create_ai_task(event, actor=actor, reason="manual_rerun")
                task["rerun_of_task_id"] = cards[-1].get("task_id") if cards else None
                store.setdefault("tasks", []).append(task)
        _normalize_event_status(event)
        event["updated_at"] = datetime.now().astimezone().isoformat()
        store["updated_at"] = event["updated_at"]
        self._save_store(store)
        dispatches = await self._dispatch_pending_tasks(
            self._load_store(event_ids={event_id}), event_ids={event_id}, wait=wait, force_retry=True
        )
        latest_store = self._load_store(event_ids={event_id})
        latest_event = self._stored_event(latest_store, event_id) or event
        latest_task = next(
            (item for item in latest_store.get("tasks", []) if item.get("task_id") == task.get("task_id")),
            task,
        )
        return {"event": latest_event, "task": latest_task, "dispatches": dispatches}

    def apply_task_execution(self, event_id: str, task: Any, execution: Any) -> None:
        # Serialize against human archive and new review submissions. A callback
        # cannot pass the archive check and then overwrite a concurrent archive.
        from app.services.task_review import review_lock
        review_id = "review_" + hashlib.sha256(json.dumps(
            [task.task_id, event_id], ensure_ascii=False).encode()).hexdigest()[:32]
        with review_lock(review_id):
            self._apply_task_execution_locked(event_id, task, execution)

    def _apply_task_execution_locked(self, event_id: str, task: Any, execution: Any) -> None:
        """Project the submitted generic review into the event; never parse replies."""

        store = self._load_store(event_ids={event_id})
        event = next((item for item in store.get("events", []) if item.get("event_id") == event_id), None)
        if event is None or _is_archived(event):
            return
        attributes = getattr(execution, "event_attributes", None) or {}
        submitted_card_id = attributes.get("smart_event_task_id")
        if submitted_card_id and not any(card.get("task_id") == submitted_card_id
                                        and card.get("status") != "已取消" for card in store.get("tasks", [])):
            return
        submitted_card = next((card for card in store.get("tasks", [])
                               if card.get("task_id") == submitted_card_id), None)
        if not _card_accepts_execution(submitted_card or {}, attributes, getattr(execution, "started_at", None)):
            logger.warning(
                "smart_event_stale_execution_result_dropped",
                event_id=event_id,
                task_id=submitted_card_id,
                execution_id=getattr(execution, "execution_id", None),
                card_dispatch_token=(submitted_card or {}).get("dispatch_token"),
                execution_dispatch_token=attributes.get("smart_event_dispatch_token"),
            )
            return
        if (event.get("ai_judgment") or {}).get("execution_id") == execution.execution_id:
            return
        from app.services.task_review import list_reviews
        submitted = next((record for record in list_reviews(pending_only=False, task_id=task.task_id)
                          if record["subject_id"] == event_id and record["execution_id"] == execution.execution_id), None)
        success = submitted is not None and str(getattr(execution, "status", "success")) in {"success", "ExecutionStatus.SUCCESS"}
        if not success:
            submitted = None
        final_response = submitted["summary"] if submitted else ""
        status = "success" if success else "failed"
        fields = {field["key"]: field["value"] for section in submitted["sections"] for field in section["fields"]
                  if field.get("key")} if submitted else {}
        structured = {
            "event_type": fields.get("event_type"), "event_name": submitted["title"],
            "data_impact": fields.get("data_impact"), "suggested_level": fields.get("suggested_level"),
            "diagnosis_note": submitted["summary"], "manual_review_suggestion": submitted["comment"],
            "disposal_suggestions": submitted["actions"],
            "compliance_explanation_result": fields.get("compliance_explanation_result"),
            "data_analysis": {key: fields[key] for key in JUDGMENT_ANALYSIS_KEYS if key in fields},
            "primary_evidence_tags": fields.get("primary_evidence_tags"),
            "supporting_evidence_tags": fields.get("supporting_evidence_tags"),
            "continuity_basis": fields.get("continuity_basis"),
            "continuity_same_cause": {"true": True, "false": False}.get(fields.get("same_cause")),
        } if submitted else None
        if submitted:
            event["review_id"] = submitted["review_id"]
        result = {
            "task_id": getattr(task, "task_id", None),
            "execution_id": getattr(execution, "execution_id", None),
            "task_name": getattr(task, "name", None),
            "status": status,
            "final_response": final_response,
            "completed_at": _format_time(getattr(execution, "completed_at", None)),
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        previous = event.get("ai_judgment") if isinstance(event.get("ai_judgment"), dict) else None
        if success and previous and previous.get("final_response"):
            history = event.setdefault("judgment_history", [])
            history.append({
                "round": len(history) + 1,
                "task_id": previous.get("task_id"),
                "final_response": previous.get("final_response"),
                "completed_at": previous.get("completed_at"),
                "archived_at": result["updated_at"],
            })
            history[:] = history[-20:]
        if success or not (previous and previous.get("final_response")):
            event["ai_judgment"] = result
        if structured is not None:
            event["ai_structured_judgment"] = structured
            if structured.get("event_type"):
                event["ai_event_type"] = structured["event_type"]
                event["event_type"] = structured["event_type"]
            if structured.get("data_impact"):
                event["ai_data_impact"] = structured["data_impact"]
            if structured.get("suggested_level"):
                event["ai_suggested_level"] = structured["suggested_level"]
            judgment_name = structured.get("event_name") or (
                f"{event.get('site_name')}{structured['event_type']}（{structured.get('data_impact') or '待确认'}）"
                if structured.get("event_type") else None
            )
            if judgment_name:
                # V3.0 2.3：AI 研判完成后当前事件名称更新为 AI 事件名称。
                event["ai_event_name"] = judgment_name
                event["event_name"] = judgment_name
        card_summary = final_response
        incremental_card: dict[str, Any] | None = None
        completed_card = None
        for card in store.get("tasks", []):
            if card.get("event_id") != event_id or card.get("task_type") != "ai_judgment":
                continue
            if submitted_card_id and card.get("task_id") != submitted_card_id:
                continue
            if card.get("status") in {"待执行", "待调度", "执行中"} or card.get("execution_id") == result["execution_id"]:
                completed_card = card
                card["status"] = "已完成" if success else "执行失败"
                if success:
                    card["next_retry_at"] = None
                    card["retry_exhausted"] = False
                else:
                    schedule_retry(card, self.load_config(), error=getattr(execution, "error_message", None))
                card["execution_id"] = result["execution_id"]
                # Todo cards are an operational summary, not the full Agent transcript.
                card["final_response"] = card_summary
                card["updated_at"] = result["updated_at"]
                if isinstance(card.get("continuity"), dict) and card["continuity"].get("mode") == "incremental":
                    incremental_card = card
        if success and incremental_card is not None:
            same_cause = (structured or {}).get("continuity_same_cause")
            if same_cause is True:
                continuity_result = CONTINUITY_SAME_CAUSE
            elif same_cause is False:
                continuity_result = CONTINUITY_NEW_CAUSE
            else:
                continuity_result = None
            incremental_card["continuity_result"] = continuity_result
            base_id = incremental_card["continuity"].get("base_task_id")
            base_card = next(
                (item for item in store.get("tasks", []) if item.get("task_id") == base_id),
                None,
            )
            if continuity_result == CONTINUITY_SAME_CAUSE and base_card is not None:
                # 同一原因延续：原待办任务卡片内容更新为最新结论。
                base_card["final_response"] = card_summary
                base_card["continuity_updated_at"] = result["updated_at"]
                base_card["updated_at"] = result["updated_at"]
            event["last_continuity_result"] = continuity_result
        evidence_package = event.get("evidence_package")
        if isinstance(evidence_package, dict):
            evidence_package["ai_judgment"] = result
            evidence_package["judgment_status"] = status
            evidence_package["judgment_updated_at"] = result["updated_at"]
            if structured is not None:
                evidence_package["ai_structured_judgment"] = structured
            event.setdefault("evidence", {})["package"] = evidence_package
        event["ai_diagnosis_note"] = (
            (structured or {}).get("diagnosis_note") or final_response or event.get("ai_diagnosis_note")
        )
        feedback_round = incremental_card is not None and (
            (incremental_card.get("continuity") or {}).get("reason") == "feedback"
        )
        feedback_source = (
            ((incremental_card.get("continuity") or {}).get("feedback") or {}).get("source")
            if incremental_card is not None else None
        )
        if success:
            if feedback_round and feedback_source == "review_reject":
                # 审核退回触发的重研判：新结论提交人工复核，不进入“已反馈”。
                event["event_status"] = _judged_status(event)
            elif feedback_round or event.get("event_status") == "已反馈":
                event["event_status"] = "已反馈"
            elif event.get("event_status") != "待反馈":
                event["event_status"] = _judged_status(event)
        else:
            # Execution failure belongs to the task; retain the last business state.
            event.setdefault("event_status", "未研判")
        update_impact_conflict(event)
        if success:
            current_ids = [str(tag.get("tag_id")) for tag in event.get("clue_tags", [])]
            covered_ids = (completed_card or {}).get("input_clue_ids", current_ids)
            event["judged_clue_ids"] = covered_ids
            covered_signature = (completed_card or {}).get("input_evidence_signature", event.get("evidence_signature"))
            event["judged_evidence_signature"] = covered_signature
            remaining = [identity for identity in current_ids if identity not in covered_ids]
            if remaining or covered_signature != event.get("evidence_signature"):
                event["pending_delta"] = {"clue_ids": remaining, "evidence_changed": covered_signature != event.get("evidence_signature"),
                                          "updated_at": result["updated_at"]}
            else:
                event.pop("pending_delta", None)
        event["updated_at"] = result["updated_at"]
        store["updated_at"] = result["updated_at"]
        self._save_store(store)

    def load_config(self) -> dict[str, Any]:
        path = self.config_path
        if path.is_file():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    return {**DEFAULT_CONFIG, **stored}
            except (OSError, ValueError):
                pass
        # Keep config-manager visible as a compatibility source for deployments
        # that already provision a matching section.
        section = config_manager.get_section("jiangsu_smart_event")
        if isinstance(section, dict):
            return {**DEFAULT_CONFIG, **section}
        return dict(DEFAULT_CONFIG)

    def save_config(self, values: dict[str, Any]) -> dict[str, Any]:
        config = {**self.load_config(), **values}
        bounds = {"schedule_interval_minutes": (1, 1440), "rescan_lookback_hours": (1, 168),
                  "evidence_refresh_minutes": (1, 1440), "evidence_batch_size": (1, 1000),
                  "ai_max_concurrency": (1, 10), "ai_max_retries": (0, 10), "ai_retry_delay_minutes": (1, 1440)}
        for key, (minimum, maximum) in bounds.items():
            value = config[key]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
        if not isinstance(config["auto_ai_enabled"], bool):
            raise ValueError("auto_ai_enabled must be boolean")
        config["version"] = int(config.get("version") or 1)
        config["ai_event_type_dictionary"] = [
            item for item in config["ai_event_type_dictionary"] if item in AI_EVENT_TYPES
        ] or list(AI_EVENT_TYPES)
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return config


def queue_review_reject_rerun(
    record: dict[str, Any], decision: dict[str, Any], actor: dict[str, Any],
) -> dict[str, Any] | None:
    """task_review 退回钩子：智能事件审核退回后自动排队以人工判定为基准的增量研判。

    只处理智能事件审核记录；排队失败仅记录告警，绝不影响退回动作本身。
    增量卡由 worker 的自动化队列每分钟领取派发。
    """
    if record.get("task_id") != SMART_EVENT_TASK_ID or not record.get("event_id"):
        return None
    feedback = str(decision.get("comment") or "").strip()
    if not feedback:
        return None
    human_decision = {
        "action": decision.get("action"),
        "decision": decision.get("decision"),
        "comment": feedback,
        "actor": {"user_id": actor.get("user_id"), "username": actor.get("username")},
        "occurred_at": (record.get("human_decision") or {}).get("occurred_at"),
    }
    try:
        return JiangsuSmartEventService().queue_review_reject_feedback(
            str(record["event_id"]), feedback=feedback, actor=actor, human_decision=human_decision,
        )
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        logger.warning(
            "smart_event_review_reject_rerun_failed",
            review_id=record.get("review_id"),
            event_id=record.get("event_id"),
            error=str(exc),
        )
        return None


async def persist_scheduled_task_result(task: Any, event: Any, execution: Any) -> None:
    """Scheduled-task result hook used by both the web process and worker."""

    if not str(getattr(event, "event_type", "")).startswith("jiangsu.smart_event."):
        return
    smart_event_id = getattr(event, "event_id", None) or getattr(event, "attributes", {}).get("smart_event_id")
    if not smart_event_id:
        return
    JiangsuSmartEventService().apply_task_execution(str(smart_event_id), task, execution)
