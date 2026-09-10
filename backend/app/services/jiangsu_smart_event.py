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
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config.config_manager import config_manager
from app.fetchers.jiangsu_smart_event_evidence import (
    JiangsuSmartEventEvidenceFetcher,
    POLLUTANT_FIELDS,
)
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
from app.utils.path_config import get_data_registry
from app.scheduled_tasks.models import ExecutionStatus, TaskEvent


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

CONTINUITY_SAME_CAUSE = "same_cause"
CONTINUITY_NEW_CAUSE = "new_cause"

JUDGMENT_DATA_IMPACTS = ("有数据影响", "无数据影响", "待确认")
JUDGMENT_LEVELS = ("P0", "P1", "P2", "P3", "待确认")
COMPLIANCE_RESULTS = ("完全解释", "部分解释", "不能解释", "无合规记录")
JUDGMENT_ANALYSIS_KEYS = (
    ("station_series_analysis", ("本站点污染物时序变化", "station_series_analysis", "station_series", "本站时序")),
    ("regional_comparison_analysis", ("区域背景对比", "regional_comparison_analysis", "regional_comparison", "区域对比")),
    ("data_impact_assessment", ("数据影响判断", "data_impact_assessment", "impact_assessment", "影响判断")),
    ("logic_direction_check", ("事件与数据逻辑方向校验", "logic_direction_check", "logic_direction", "方向校验")),
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
    "version": 1,
    "event_merge_window_minutes": 60,
    "event_before_extend_minutes": 30,
    "event_after_extend_minutes": 30,
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
    text = str(_first(record, "content", "alarmContent", "description") or "平台告警")
    classification_text = " ".join(
        str(record.get(key) or "") for key in ("content", "alarmContent", "description", "ddRuleType", "callType")
    )
    lower = classification_text.lower()
    if "ups" in lower or "电源" in classification_text or "供电" in classification_text:
        return "供电报警", "供电/UPS"
    if any(word in classification_text for word in ("网络", "通讯", "通信", "数采", "断数", "离线", "上传")):
        return "数采网络报警", "数采/网络"
    if any(word in classification_text for word in ("温度", "湿度", "空调", "除湿", "通风")):
        return "站房环境报警", "站房环境"
    return "仪器报警", str(_first(record, "deviceName", "device", "objectName") or text[:80] or "告警对象")


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


def _parse_continuity(text: str) -> str | None:
    """从 Agent 最终回复中提取连续性判断标记行。"""
    if not text:
        return None
    if re.search(r"连续性判断[：:]\s*(新事件|新的?一个事件|new[_\s-]?cause)", text):
        return CONTINUITY_NEW_CAUSE
    if re.search(r"连续性判断[：:]\s*(同一原因|同一事件|same[_\s-]?cause)", text):
        return CONTINUITY_SAME_CAUSE
    return None


def _extract_judgment_json(text: str) -> dict[str, Any] | None:
    """提取最终回复末尾的 ```json 结构化研判块（取最后一个可解析的）。"""
    if not text:
        return None
    candidates = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _clean_text(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] if text else None


def _clean_str_list(value: Any, *, max_items: int = 20, item_limit: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_text(item, item_limit) for item in value[:max_items]]
    return [item for item in cleaned if item]


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
    query = windows.get("query") if isinstance(windows.get("query"), dict) else {}
    start_text, end_text = query.get("start"), query.get("end")
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
        "tag_end_time": start,
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
        "event_end_time": end,
        "initial_event_name": initial_name,
        "event_name": initial_name,
        "event_status": "未研判",
        "event_type": "待 AI 研判",
        "source_alarm_rule_type": rule_type,
        "alarm_content": alarm_content or None,
        "source_alarm_state": _first(record, "ddalarmstateName", "ddalarmstate", "alarmState"),
        "event_trigger_type": SMART_EVENT_EVENT_TYPE,
        "clue_trigger_type": SMART_EVENT_TRIGGER_TYPES[label],
        "clue_tags": [tag],
        "primary_clue_tag": label,
        "clue_count": 1,
        "merged_alarm_ids": [event_id],
        "ai_event_type": None,
        "ai_event_name": None,
        "ai_data_impact": "待确认",
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

    def _evidence_package_path(self, event_id: str) -> Path:
        safe_id = hashlib.sha256(str(event_id).encode("utf-8")).hexdigest()[:24]
        return self.data_root / "jiangsu_smart_events" / "evidence" / f"{safe_id}.json"

    def _load_store(self) -> dict[str, Any]:
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
                    return value
            except (OSError, ValueError):
                pass
        return {"schema_version": "jiangsu_smart_events/v1", "events": [], "tasks": []}

    def _save_store(self, store: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.store_path.name}.", suffix=".tmp", dir=self.store_path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.store_path)
        finally:
            temporary.unlink(missing_ok=True)

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
        events = [normalize_alarm_event(row) for row in result.get("data", []) if isinstance(row, dict)]
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
        return event.get("event_status") in {"AI 已研判", "待人工确认", "已确认"}

    def _naming_priority(self) -> list[str]:
        config = self.load_config()
        priority = config.get("initial_naming_priority")
        return [str(item) for item in priority] if isinstance(priority, list) else []

    def _merge_event_into(self, target: dict[str, Any], donor: dict[str, Any]) -> list[str]:
        """把 donor 事件的线索并入同站点同日的 target 事件桶，返回新增 tag_id 列表。"""
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
        for field, earlier in (("event_start_time", True), ("event_end_time", False)):
            current = _parse_time(target.get(field))
            incoming = _parse_time(donor.get(field))
            if incoming is None:
                continue
            if current is None or (earlier and incoming < current) or (not earlier and incoming > current):
                target[field] = _format_time(incoming)
        target["merged_alarm_ids"] = list(dict.fromkeys(
            [str(target.get("event_id"))]
            + [str(item) for item in (target.get("merged_alarm_ids") or [])]
            + [str(donor.get("event_id"))]
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
        if not tags:
            return []
        now = datetime.now().astimezone().isoformat()
        existing = {item.get("tag_id") for item in bucket.get("clue_tags", [])}
        new_tags = [tag for tag in tags if tag.get("tag_id") and tag["tag_id"] not in existing]
        if not new_tags:
            return []
        bucket["clue_tags"] = list(bucket.get("clue_tags", [])) + new_tags
        bucket["clue_count"] = len(bucket["clue_tags"])
        for field, earlier in (("event_start_time", True), ("event_end_time", False)):
            for tag in new_tags:
                incoming = _parse_time(tag.get("tag_start_time") if earlier else tag.get("tag_end_time"))
                if incoming is None:
                    continue
                current = _parse_time(bucket.get(field))
                if current is None or (earlier and incoming < current) or (not earlier and incoming > current):
                    bucket[field] = _format_time(incoming)
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
        created_tasks: list[dict[str, Any]] = []
        created_event_ids: list[str] = []
        merged_event_ids: list[str] = []
        now = datetime.now().astimezone().isoformat()
        for candidate in incoming:
            event_id = str(candidate["event_id"])
            current = existing.get(event_id)
            if current is not None and (current.get("archived") is True or current.get("event_status") == "已归档"):
                for field in ("source_alarm_state", "event_end_time", "alarm_content"):
                    if candidate.get(field) not in (None, ""):
                        current[field] = candidate[field]
                current["updated_at"] = now
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
        config = self.load_config()
        stored_by_id = {
            str(item.get("event_id")): item
            for item in store.get("events", [])
            if isinstance(item, dict) and item.get("event_id")
        }
        semaphore = asyncio.Semaphore(3)

        async def collect(candidate: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            event_id = str(candidate.get("event_id") or "")
            async with semaphore:
                try:
                    package = await self.evidence_fetcher.fetch(
                        stored_by_id.get(event_id, candidate), config=config
                    )
                except Exception as exc:  # noqa: BLE001 - keep event visible with a gap
                    package = {
                        "schema_version": "jiangsu_smart_event_evidence/v1",
                        "event_id": event_id,
                        "status": "failed",
                        "gaps": [{"source": "collector", "status": "failed", "reason": str(exc)}],
                    }
                return event_id, package

        results = await asyncio.gather(*(collect(event) for event in events))
        failed = 0
        for event_id, package in results:
            target = stored_by_id.get(event_id)
            if target is None:
                continue
            target["evidence_package"] = package
            target.setdefault("evidence", {})["package"] = package
            package_path = self._evidence_package_path(event_id)
            package_path.parent.mkdir(parents=True, exist_ok=True)
            package["persisted_path"] = str(package_path)
            package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
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
                target["evidence_fingerprint"] = _event_fingerprint(target)
            if package.get("status") == "failed":
                failed += 1
        if results:
            store["updated_at"] = datetime.now().astimezone().isoformat()
            self._save_store(store)
        return {"collected": len(results), "failed": failed}

    async def collect_event_evidence(self, event_id: str) -> dict[str, Any]:
        """Collect and persist the evidence package for one stored event."""
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        result = await self._collect_event_evidence(store, [event])
        return {"event": event, **result}

    async def collect_all_event_evidence(self, *, limit: int = 100) -> dict[str, Any]:
        """Collect evidence for stored events that do not have a package yet."""
        store = self._load_store()
        candidates = [
            item for item in store.get("events", [])
            if isinstance(item, dict) and not item.get("evidence_package")
        ][:limit]
        result = await self._collect_event_evidence(store, candidates)
        return {"events": candidates, **result}

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
        if feedback:
            instruction = (
                "本次为事件反馈后的增量研判：运维或现场人员已提交处理反馈（见 feedback 字段）。"
                "请结合上一轮研判结论与反馈内容继续分析，核验反馈是否解释、修正或补充上一轮判断，"
                "输出更新后的完整研判结论；新结论将替换上一轮结论。"
            )
        else:
            instruction = (
                "本次为增量研判：事件在上一轮研判后又合并了新线索。请先阅读上一轮研判结论和新增线索，"
                "判断新增线索与上一轮事件是否同一原因；必须在回复第一行单独输出标记行"
                "“连续性判断：同一原因延续”或“连续性判断：新事件”，"
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
        for card in store.get("tasks", []):
            if card.get("task_type") != "ai_judgment" or card.get("status") not in {"待执行", "待调度"}:
                continue
            if event_ids is not None and str(card.get("event_id")) not in event_ids:
                continue
            event = events.get(card.get("event_id"))
            if not event or not event.get("event_trigger_type"):
                continue
            continuity = self._continuity_context(event, card)
            task_event = TaskEvent(
                event_id=str(event["event_id"]),
                event_type=SMART_EVENT_EVENT_TYPE,
                occurred_at=_parse_time(event.get("event_start_time")) or datetime.now().astimezone(),
                attributes={
                    "smart_event_id": event["event_id"],
                    "smart_event_type": event.get("primary_clue_tag"),
                    "clue_type": event.get("primary_clue_tag"),
                    "site_id": event.get("site_id"),
                    "site_name": event.get("site_name"),
                    "continuity_mode": continuity.get("mode") if continuity else None,
                    "evidence_package_id": event.get("evidence_package", {}).get("collected_at") if isinstance(event.get("evidence_package"), dict) else None,
                    "evidence_package_path": event.get("evidence_package", {}).get("persisted_path") if isinstance(event.get("evidence_package"), dict) else None,
                },
                payload={
                    "smart_event": event,
                    "evidence_package": event.get("evidence_package"),
                    "evidence_package_path": event.get("evidence_package", {}).get("persisted_path") if isinstance(event.get("evidence_package"), dict) else str(self._evidence_package_path(event["event_id"])),
                    "continuity_context": continuity,
                },
            )
            try:
                dispatch = await task_service.publish_event(task_event, wait=wait)
                if wait and dispatch.execution_ids:
                    # The completion hook may already have written a terminal
                    # status and final reply while publish_event was awaited.
                    latest = self._load_store()
                    latest_card = next(
                        (item for item in latest.get("tasks", []) if item.get("task_id") == card.get("task_id")),
                        None,
                    )
                    if latest_card:
                        card.clear()
                        card.update(latest_card)
                else:
                    card["status"] = "执行中" if dispatch.accepted_task_ids else card.get("status", "待执行")
                card["dispatch_status"] = "accepted" if dispatch.accepted_task_ids else "duplicate_or_unmatched"
                card["scheduled_task_ids"] = list(dispatch.accepted_task_ids or dispatch.matched_task_ids)
                card["execution_ids"] = list(dispatch.execution_ids)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], **dispatch.model_dump(mode="json")})
            except Exception as exc:  # noqa: BLE001 - keep the event visible for retry
                card["dispatch_status"] = "failed"
                card["dispatch_error"] = str(exc)
                card["updated_at"] = datetime.now().astimezone().isoformat()
                changed = True
                outcomes.append({"event_id": event["event_id"], "status": "failed", "error": str(exc)})
        if changed:
            store["updated_at"] = datetime.now().astimezone().isoformat()
            self._save_store(store)
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
        fetch_evidence: bool = False,
    ) -> dict[str, Any]:
        fetched = await self._fetch_alarm_events(
            start_time=start_time, end_time=end_time, station_codes=station_codes, limit=limit
        )
        store, created_tasks, created_event_ids, merged_event_ids = self._upsert_events(fetched["events"], actor=actor)
        evidence_result = {"collected": 0, "failed": 0}
        if fetch_evidence:
            evidence_result = await self._collect_event_evidence(store, fetched["events"])
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
        self._save_store(store)
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
        self._save_store(store)
        return {
            "status": "synced",
            "date": day_text,
            "clues": len(clues),
            "attached": attached,
            "stations": len(station_codes),
            "attached_sites": sorted(attached_sites),
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
                fetch_evidence=False,
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
    ) -> dict[str, Any]:
        sync_state: dict[str, Any] = {"in_progress": False, "started_at": None, "triggered": False}
        if refresh:
            sync_state = self.start_background_sync(
                start_time=start_time,
                end_time=end_time,
                station_codes=station_codes,
                limit=limit,
            )
        store = self._load_store()
        last_sync = store.get("last_sync") if isinstance(store.get("last_sync"), dict) else None
        upstream_error = str(last_sync.get("error")) if last_sync and last_sync.get("error") else None
        events = self._filter_events(
            [item for item in store.get("events", []) if isinstance(item, dict)],
            status=status,
            keyword=keyword,
            limit=limit,
        )
        return {
            "events": events,
            "total": len(events),
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

    async def get_event(self, event_id: str, **query: Any) -> dict[str, Any] | None:
        query.setdefault("refresh", False)
        payload = await self.list_events(**query)
        return next((item for item in payload["events"] if item["event_id"] == event_id), None)

    def list_tasks(self, *, event_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        tasks = [item for item in self._load_store().get("tasks", []) if isinstance(item, dict)]
        if event_id:
            tasks = [item for item in tasks if item.get("event_id") == event_id]
        if status:
            tasks = [item for item in tasks if item.get("status") == status]
        return tasks[:limit]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
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

    def submit_ai_judgment(
        self, event_id: str, payload: dict[str, Any], *, actor: dict[str, Any]
    ) -> dict[str, Any]:
        """Save a structured human confirmation of the Agent judgment."""

        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        event_type = str(payload.get("event_type") or payload.get("ai_event_type") or "").strip()
        if not event_type:
            raise ValueError("event_type_required")
        confirmed = bool(payload.get("confirmed", False))
        now = datetime.now().astimezone().isoformat()
        manual = {
            "event_type": event_type,
            "event_name": str(payload.get("event_name") or "").strip() or None,
            "level": str(payload.get("level") or payload.get("suggested_level") or "").strip() or None,
            "data_impact": payload.get("data_impact"),
            "diagnosis_note": str(payload.get("diagnosis_note") or "").strip() or None,
            "confirmed": confirmed,
            "confirmed_at": now if confirmed else None,
            "confirmed_by": actor if confirmed else None,
        }
        event["manual_final_event_type"] = event_type if confirmed else None
        event["manual_final_level"] = manual["level"] if confirmed else None
        event["manual_confirmation"] = manual
        event["ai_event_type"] = event_type
        event["ai_suggested_level"] = manual["level"]
        if manual["event_name"] and confirmed:
            event["event_name"] = manual["event_name"]
        if manual["data_impact"] is not None:
            event["ai_data_impact"] = manual["data_impact"]
        if manual["diagnosis_note"]:
            event["ai_diagnosis_note"] = manual["diagnosis_note"]
        event["event_status"] = "已确认" if confirmed else "待人工确认"
        event["updated_at"] = now
        self._append_operation(
            event,
            action="confirm_ai_judgment" if confirmed else "save_ai_judgment_draft",
            actor=actor,
            summary="人工确认 AI 研判结果" if confirmed else "保存 AI 研判确认草稿",
            details={"event_type": event_type, "level": manual["level"]},
        )
        store["updated_at"] = now
        self._save_store(store)
        return event

    def record_operation(
        self, event_id: str, *, action: str, summary: str, actor: dict[str, Any],
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        store = self._load_store()
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
        """提交派单处置：事件进入“派单处置中”并保留工单信息。"""
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
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
        event["event_status"] = "派单处置中"
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return event

    async def submit_feedback(
        self, event_id: str, *, feedback: str, attachments: list[str] | None = None,
        actor: dict[str, Any] | None = None, dispatch: bool = True,
    ) -> dict[str, Any]:
        """记录事件反馈，并以增量对话继续上一轮 AI 研判。

        反馈是增量对话：反馈内容作为新增输入推送给上一轮研判会话，Agent
        输出的更新结论会替换上一轮 ``ai_judgment``（旧结论进入
        ``judgment_history``），完成后事件状态回到“已反馈”。
        """
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        feedback_text = str(feedback or "").strip()
        if not feedback_text:
            raise ValueError("feedback_required")
        attachment_names = [str(item).strip()[:200] for item in (attachments or []) if str(item).strip()][:20]
        now = datetime.now().astimezone().isoformat()
        self._append_operation(
            event,
            action="event_feedback",
            actor=actor or {"user_id": "system", "username": "system"},
            summary=f"收到事件反馈：{feedback_text[:120]}",
            details={"feedback": feedback_text, "attachments": attachment_names},
        )
        event["event_status"] = "已反馈"
        event["updated_at"] = now
        cards = [
            item for item in store.get("tasks", [])
            if item.get("event_id") == event_id and item.get("task_type") == "ai_judgment"
        ]
        incremental_task = None
        if not any(item.get("status") in {"待执行", "待调度", "执行中"} for item in cards):
            base = next((item for item in reversed(cards) if item.get("status") == "已完成"), None)
            incremental_task = self._create_ai_task(event, actor=actor, base_task=base, reason="feedback")
            if isinstance(incremental_task.get("continuity"), dict):
                incremental_task["continuity"]["feedback"] = {
                    "feedback": feedback_text,
                    "attachments": attachment_names,
                    "submitted_at": now,
                }
            store.setdefault("tasks", []).append(incremental_task)
        store["updated_at"] = now
        self._save_store(store)
        dispatches: list[dict[str, Any]] = []
        if dispatch and incremental_task is not None:
            dispatches = await self._dispatch_pending_tasks(
                self._load_store(), event_ids={event_id}
            )
        latest_store = self._load_store()
        latest_event = self._stored_event(latest_store, event_id) or event
        latest_task = next(
            (item for item in latest_store.get("tasks", []) if item.get("task_id") == (incremental_task or {}).get("task_id")),
            incremental_task,
        )
        return {"event": latest_event, "task": latest_task, "dispatches": dispatches}

    def archive_event(
        self, event_id: str, *, actor: dict[str, Any], comment: str | None = None,
        confirmation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """归档并锁定事件；归档确认即最终人工确认（V3.0 15.5）。

        ``confirmation`` 携带归档事件类型/名称/等级/数据影响，默认由前端
        带入当前 AI 研判结果、允许人工修改；确认后写入 ``archive_confirmed``
        并按归档内容覆盖事件展示字段。未携带 confirmation 的旧调用仍要求
        先完成人工确认研判。
        """
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        payload = confirmation if isinstance(confirmation, dict) else {}
        event_type = str(payload.get("event_type") or payload.get("ai_event_type") or "").strip()
        if not event_type:
            manual = event.get("manual_confirmation") if isinstance(event.get("manual_confirmation"), dict) else {}
            event_type = str(manual.get("event_type") or "").strip()
        if not event_type:
            raise ValueError("smart_event_judgment_not_confirmed")
        now = datetime.now().astimezone().isoformat()
        level = str(payload.get("level") or payload.get("suggested_level") or "").strip() or event.get("ai_suggested_level")
        data_impact = payload.get("data_impact") if payload.get("data_impact") is not None else event.get("ai_data_impact")
        confirmed_name = str(payload.get("event_name") or "").strip() or (
            event.get("ai_event_name") or event.get("event_name")
        )
        confirmed = {
            "event_type": event_type,
            "event_name": confirmed_name,
            "level": level,
            "data_impact": data_impact,
            "comment": str(comment or "").strip() or None,
            "confirmed_at": now,
            "confirmed_by": actor,
        }
        # 归档确认即最终人工确认：同时落 manual_* 与展示字段。
        event["archive_confirmed"] = confirmed
        event["manual_confirmation"] = {
            "event_type": event_type,
            "event_name": confirmed_name,
            "level": level,
            "data_impact": data_impact,
            "diagnosis_note": (event.get("manual_confirmation") or {}).get("diagnosis_note")
            if isinstance(event.get("manual_confirmation"), dict) else None,
            "confirmed": True,
            "confirmed_at": now,
            "confirmed_by": actor,
            "source": "archive",
        }
        event["manual_final_event_type"] = event_type
        event["manual_final_level"] = level
        event["ai_event_type"] = event_type
        event["ai_suggested_level"] = level
        event["ai_data_impact"] = data_impact
        event["ai_event_name"] = confirmed_name
        event["event_name"] = confirmed_name
        event["archived"] = True
        event["event_status"] = "已归档"
        event["archived_at"] = now
        event["archived_by"] = actor
        event["archive_comment"] = confirmed["comment"]
        self._append_operation(
            event,
            action="archive_event",
            actor=actor,
            summary="人工归档智能事件",
            details={
                "comment": event["archive_comment"],
                "event_type": event_type,
                "level": level,
                "data_impact": data_impact,
            },
        )
        event["updated_at"] = now
        store["updated_at"] = now
        self._save_store(store)
        return event

    def create_task(self, event_id: str, *, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        store = self._load_store()
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

        Event-center refresh never calls this method.  A manual click first
        makes sure the event has a fresh evidence package (merged clues
        invalidate the stored fingerprint and force a wider re-fetch), then
        starts a brand-new round: a new conversation is used, stale pending
        cards (including merge-triggered incremental cards) are cancelled,
        and the previous conclusion is superseded into judgment_history when
        the new round completes.  First-time judgments simply reuse their
        pending card.  Feedback rounds continue the conversation instead and
        are created by ``submit_feedback``.
        """
        store = self._load_store()
        event = self._stored_event(store, event_id)
        if event is None:
            raise KeyError(event_id)
        self._ensure_not_archived(event)
        fingerprint = _event_fingerprint(event)
        if (
            not event.get("evidence_package")
            or event.get("evidence_fingerprint") != fingerprint
        ):
            await self.collect_event_evidence(event_id)
            store = self._load_store()
            event = self._stored_event(store, event_id) or event
        package = event.get("evidence_package")
        if isinstance(package, dict) and not package.get("persisted_path"):
            package_path = self._evidence_package_path(event_id)
            package_path.parent.mkdir(parents=True, exist_ok=True)
            package["persisted_path"] = str(package_path)
            package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            event.setdefault("evidence", {})["package"] = package
            self._save_store(store)
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
        event["event_status"] = "AI 研判中"
        event["updated_at"] = datetime.now().astimezone().isoformat()
        store["updated_at"] = event["updated_at"]
        self._save_store(store)
        dispatches = await self._dispatch_pending_tasks(
            self._load_store(), event_ids={event_id}, wait=wait
        )
        latest_store = self._load_store()
        latest_event = self._stored_event(latest_store, event_id) or event
        latest_task = next(
            (item for item in latest_store.get("tasks", []) if item.get("task_id") == task.get("task_id")),
            task,
        )
        return {"event": latest_event, "task": latest_task, "dispatches": dispatches}

    def _normalize_structured_judgment(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """把 Agent 输出的 JSON 研判块归一为受控字段（非法枚举一律剔除）。"""
        if not isinstance(raw, dict) or not raw:
            return None
        dictionary = set(self.load_config().get("ai_event_type_dictionary") or AI_EVENT_TYPES)
        event_type = str(raw.get("event_type") or raw.get("ai_event_type") or "").strip()
        if event_type not in dictionary:
            event_type = None
        data_impact = str(raw.get("data_impact") or "").strip()
        if data_impact not in JUDGMENT_DATA_IMPACTS:
            data_impact = None
        level = str(raw.get("suggested_level") or raw.get("level") or "").strip().upper()
        if level not in JUDGMENT_LEVELS:
            level = None
        compliance = str(raw.get("compliance_explanation_result") or "").strip()
        if compliance not in COMPLIANCE_RESULTS:
            compliance = None
        analysis_raw = raw.get("data_analysis") if isinstance(raw.get("data_analysis"), dict) else {}
        data_analysis: dict[str, str] = {}
        for key, aliases in JUDGMENT_ANALYSIS_KEYS:
            for alias in (key, *aliases):
                text = _clean_text(analysis_raw.get(alias), 4000)
                if text:
                    data_analysis[key] = text
                    break
        continuity = raw.get("continuity") if isinstance(raw.get("continuity"), dict) else {}
        same_cause = continuity.get("same_cause", raw.get("same_cause"))
        structured = {
            "event_type": event_type,
            "event_name": _clean_text(raw.get("event_name"), 240),
            "data_impact": data_impact,
            "suggested_level": level,
            "diagnosis_note": _clean_text(raw.get("diagnosis_note"), 8000),
            "manual_review_suggestion": _clean_text(raw.get("manual_review_suggestion"), 4000),
            "disposal_suggestions": _clean_str_list(raw.get("disposal_suggestions")),
            "primary_evidence_tags": _clean_str_list(raw.get("primary_evidence_tags")),
            "supporting_evidence_tags": _clean_str_list(raw.get("supporting_evidence_tags")),
            "compliance_explanation_result": compliance,
            "data_analysis": data_analysis or None,
            "continuity_same_cause": same_cause if isinstance(same_cause, bool) else None,
        }
        has_value = any(structured.values())
        return structured if has_value else None

    def apply_task_execution(self, event_id: str, task: Any, execution: Any) -> None:
        """Persist the Agent's final reply back into the fixed event detail.

        Incremental (merged-clue) rounds additionally record a continuity
        result: ``same_cause`` refreshes the original task card with the new
        conclusion, ``new_cause`` keeps the original card untouched so the
        incremental card stays an independent judgment round.
        """

        store = self._load_store()
        event = next((item for item in store.get("events", []) if item.get("event_id") == event_id), None)
        if event is None:
            return
        final_response = ""
        if getattr(execution, "steps", None):
            final_response = str(getattr(execution.steps[-1], "agent_response", "") or "")
        status = getattr(getattr(execution, "status", None), "value", getattr(execution, "status", ""))
        success = status == ExecutionStatus.SUCCESS.value
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
        structured = self._normalize_structured_judgment(_extract_judgment_json(final_response)) if success else None
        if structured is not None:
            event["ai_structured_judgment"] = structured
            if structured.get("event_type"):
                event["ai_event_type"] = structured["event_type"]
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
        incremental_card: dict[str, Any] | None = None
        for card in store.get("tasks", []):
            if card.get("event_id") != event_id or card.get("task_type") != "ai_judgment":
                continue
            if card.get("status") in {"待执行", "待调度", "执行中"} or card.get("execution_id") == result["execution_id"]:
                card["status"] = "已完成" if success else "执行失败"
                card["execution_id"] = result["execution_id"]
                card["final_response"] = final_response
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
                continuity_result = _parse_continuity(final_response) or CONTINUITY_SAME_CAUSE
            incremental_card["continuity_result"] = continuity_result
            base_id = incremental_card["continuity"].get("base_task_id")
            base_card = next(
                (item for item in store.get("tasks", []) if item.get("task_id") == base_id),
                None,
            )
            if continuity_result == CONTINUITY_SAME_CAUSE and base_card is not None:
                # 同一原因延续：原待办任务卡片内容更新为最新结论。
                base_card["final_response"] = final_response
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
            package_path = evidence_package.get("persisted_path") or str(self._evidence_package_path(event_id))
            evidence_package["persisted_path"] = package_path
            Path(package_path).parent.mkdir(parents=True, exist_ok=True)
            Path(package_path).write_text(json.dumps(evidence_package, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        event["ai_diagnosis_note"] = (
            (structured or {}).get("diagnosis_note") or final_response or event.get("ai_diagnosis_note")
        )
        feedback_round = incremental_card is not None and (
            (incremental_card.get("continuity") or {}).get("reason") == "feedback"
        )
        if success:
            event["event_status"] = "已反馈" if feedback_round else "AI 已研判"
        else:
            event["event_status"] = "AI 研判失败"
        if success:
            # 本轮研判覆盖到当前全部线索；新增线索 watermark 清零。
            event["judged_clue_ids"] = [str(tag.get("tag_id")) for tag in event.get("clue_tags", []) or []]
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
        config = {**DEFAULT_CONFIG, **values}
        config["version"] = int(config.get("version") or 1)
        config["ai_event_type_dictionary"] = [
            item for item in config["ai_event_type_dictionary"] if item in AI_EVENT_TYPES
        ] or list(AI_EVENT_TYPES)
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return config


async def persist_scheduled_task_result(task: Any, event: Any, execution: Any) -> None:
    """Scheduled-task result hook used by both the web process and worker."""

    if not str(getattr(event, "event_type", "")).startswith("jiangsu.smart_event."):
        return
    smart_event_id = getattr(event, "event_id", None) or getattr(event, "attributes", {}).get("smart_event_id")
    if not smart_event_id:
        return
    JiangsuSmartEventService().apply_task_execution(str(smart_event_id), task, execution)
