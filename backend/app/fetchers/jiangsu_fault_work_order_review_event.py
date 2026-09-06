"""Poll Jiangsu fault work orders and publish SOP review events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.weather.jiangsu_review_weather import fetch_city_weather
from app.scheduled_tasks.models.event import TaskEvent
from app.services.jiangsu_work_order_review import REVIEW_SCENARIO, has_active_review
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuFaultWorkOrderDetailTool,
    JiangsuFaultWorkOrdersTool,
    JiangsuQcMonitoringCurveTool,
    JiangsuQcRunLogTool,
    JiangsuQcTaskHistoryTool,
    JiangsuQcTaskStatusTool,
    JiangsuStationAlarmLogsTool,
    JiangsuStationEnvironmentHistoryTool,
)
from app.tools.jiangsu.result_filter import compact_air_quality_records
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

REVIEW_EVENT_TYPE = "jiangsu.fault_work_order.review_requested"
EVENT_TYPE = REVIEW_EVENT_TYPE
POLL_SCHEDULE = os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_POLL_CRON", "30 8 * * *")
_CREATE_LOOKBACK_HOURS = os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_CREATE_LOOKBACK_HOURS")
POLL_CREATE_LOOKBACK_HOURS = int(
    _CREATE_LOOKBACK_HOURS
    if _CREATE_LOOKBACK_HOURS is not None
    else os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_LOOKBACK_HOURS", "0")
)
MAX_EVENTS_PER_RUN = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_MAX_EVENTS_PER_RUN", "20"))
MAX_QC_TASK_DETAILS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_MAX_QC_TASK_DETAILS", "4"))
EVIDENCE_MAX_RECORDS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_EVIDENCE_MAX_RECORDS", "500"))
EVIDENCE_CALL_TIMEOUT_SECONDS = float(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_CALL_TIMEOUT_SECONDS", "75"))
EVIDENCE_PACKAGE_TIMEOUT_SECONDS = float(
    os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_PACKAGE_TIMEOUT_SECONDS", "300")
)
EVIDENCE_HOUR_CHUNK_DAYS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_HOUR_CHUNK_DAYS", "31"))
EVIDENCE_5MIN_CHUNK_DAYS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_5MIN_CHUNK_DAYS", "7"))
SAME_CITY_SUMMARY_TIMELINE_LIMIT = int(
    os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_SAME_CITY_SUMMARY_TIMELINE_LIMIT", "96")
)
SAME_CITY_SUMMARY_NOTABLE_LIMIT = int(
    os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_SAME_CITY_SUMMARY_NOTABLE_LIMIT", "24")
)
QC_KEYWORDS = (
    "质控",
    "质控任务",
    "零点",
    "跨度",
    "零跨",
    "校准",
    "标气",
    "通零气",
    "自动质控",
    "复测",
    "测量链",
)
TRANSMISSION_KEYWORDS = (
    "站点离线",
    "平台离线",
    "离线",
    "网络",
    "通信",
    "通讯",
    "工控机",
    "数采仪",
    "VPN",
    "路由器",
    "交换机",
    "数据传输",
    "未上传",
    "无数据上传",
    "上传中断",
    "平台未更新",
    "未更新",
    "数据缺失",
    "断点",
    "补传",
    "重传",
    "断点续传",
    "接收中断",
    "接收率",
    "传输率",
)
SOP02_KEYWORDS = (
    "高值",
    "低值",
    "偏高",
    "偏低",
    "离群",
    "零值",
    "恒值",
    "突变",
    "数据异常",
    "冷凝水",
    "采样管",
    "采样总管",
    "堵塞",
    "泄漏",
    "管路",
    "流量",
    "泵",
    "泵膜",
    "制冷",
    "温度",
    "湿度",
    "空调",
    "断电",
    "跳电",
    "供电",
    "电压",
    "电流",
    "UPS",
    "防雷",
    "纸带",
    "切割器",
    "平台抬放",
    "抬放",
)
POLLUTANT_ALIASES = {
    "SO2": ("SO2", "二氧化硫"),
    "NO": ("NO", "一氧化氮"),
    "NO2": ("NO2", "二氧化氮"),
    "NOX": ("NOX", "氮氧化物"),
    "CO": ("CO", "一氧化碳"),
    "O3": ("O3", "臭氧"),
    "PM10": ("PM10",),
    "PM2.5": ("PM2.5", "PM2_5", "PM25"),
}


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            pass
    return None


def _compact_value(value: Any, *, depth: int = 0, max_items: int = 60) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 1600 else value[:1600] + "…[truncated]"
    if depth >= 4:
        return "[nested data omitted]" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if "resources" in key_text or "visuals" in key_text:
                continue
            compact[str(key)] = _compact_value(item, depth=depth + 1, max_items=max_items)
        return compact
    return value


def _compact_result(result: Any, *, max_records: int = EVIDENCE_MAX_RECORDS) -> dict[str, Any]:
    if isinstance(result, BaseException):
        return {"success": False, "status": "failed", "summary": str(result), "data": []}
    if not isinstance(result, dict):
        return {"success": False, "status": "failed", "summary": "返回格式异常", "data": []}
    data = result.get("data")
    if isinstance(data, list):
        compact_data = [_compact_value(item) for item in data[:max_records]]
        record_count = len(data)
    elif isinstance(data, dict):
        compact_data = _compact_value(data)
        if isinstance(data.get("tableData"), list):
            record_count = len(data["tableData"])
        elif isinstance(data.get("records"), list):
            record_count = len(data["records"])
        else:
            record_count = len(data)
    else:
        compact_data = data if data is not None else []
        record_count = 0
    return {
        "success": bool(result.get("success") is True),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "metadata": _compact_value(result.get("metadata") or {}),
        "record_count": record_count,
        "returned_records": min(record_count, max_records) if isinstance(data, list) else record_count,
        "data": compact_data,
    }


def _compact_same_city_monitoring_payload(value: Any) -> Any:
    if not isinstance(value, dict):
        return _compact_result(value)
    compact: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"station_hour_raw", "station_hour_audited"} and isinstance(item, dict):
            records = item.get("data")
            max_records = len(records) if isinstance(records, list) else EVIDENCE_MAX_RECORDS
            compact[key] = _compact_result(item, max_records=max_records)
        else:
            compact[key] = _compact_value(item)
    return compact


def _same_city_raw_record_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key in ("station_hour_raw", "station_hour_audited"):
        item = value.get(key)
        if not isinstance(item, dict):
            continue
        record_count = item.get("record_count")
        if isinstance(record_count, int):
            counts[key] = record_count
            continue
        data = item.get("data")
        counts[key] = len(data) if isinstance(data, list) else 0
    return counts


def _metric_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _pollutant_metric_keys(pollutant: str) -> set[str]:
    aliases = set(POLLUTANT_ALIASES.get(pollutant, (pollutant,)))
    aliases.add(pollutant)
    return {_metric_key(alias) for alias in aliases if str(alias or "").strip()}


def _number_from_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _round_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return round(value, 3)


def _audit_mark_from_value(value: Any) -> str:
    text = str(value or "")
    marks = []
    for mark in re.findall(r"[（(]([^()（）]{1,20})[）)]", text):
        mark_text = mark.strip()
        if mark_text and mark_text not in marks:
            marks.append(mark_text)
    return ",".join(marks)


def _pollutant_reading(row: dict[str, Any], pollutant: str) -> dict[str, Any] | None:
    metric_keys = _pollutant_metric_keys(pollutant)
    if not metric_keys:
        return None
    reading_key = ""
    raw_value = None
    numeric_value = None
    for key, value in row.items():
        if _metric_key(key) not in metric_keys:
            continue
        parsed = _number_from_value(value)
        if parsed is None:
            continue
        reading_key = str(key)
        raw_value = value
        numeric_value = parsed
        break
    if numeric_value is None:
        return None

    audit_mark = _audit_mark_from_value(raw_value)
    for key, value in row.items():
        key_text = str(key)
        if not key_text.endswith("_Mark"):
            continue
        base_key = key_text[: -len("_Mark")]
        if _metric_key(base_key) not in metric_keys:
            continue
        mark_text = str(value or "").strip()
        if mark_text:
            audit_mark = mark_text
            break

    return {
        "field": reading_key,
        "value": _round_number(numeric_value),
        "raw_value": raw_value,
        "audit_mark": audit_mark or None,
    }


def _row_time_text(row: dict[str, Any]) -> str:
    return str(
        row.get("timePoint")
        or row.get("time")
        or row.get("monitorTime")
        or row.get("dateTime")
        or ""
    ).strip()


def _row_station_code(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stationCode") or row.get("station_code") or "").strip()


def _row_station_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("stationName") or row.get("station_name") or "").strip()


def _sort_time_key(value: str) -> tuple[int, Any]:
    parsed = _parse_datetime(value)
    if parsed is not None:
        return (0, parsed)
    return (1, value)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _rank_desc(value: float, values: list[float]) -> int:
    return 1 + sum(1 for item in values if item > value)


def _rank_asc(value: float, values: list[float]) -> int:
    return 1 + sum(1 for item in values if item < value)


def _same_city_classification(target_value: float | None, comparison_values: list[float]) -> str:
    if target_value is None:
        return "target_missing"
    if not comparison_values:
        return "no_comparison_station_value"
    minimum = min(comparison_values)
    maximum = max(comparison_values)
    if target_value > maximum:
        return "target_above_same_city_max"
    if target_value < minimum:
        return "target_below_same_city_min"
    return "within_same_city_range"


def _metadata_summary(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    omitted = {"chunks", "time_points"}
    summary = {str(key): _compact_value(value) for key, value in metadata.items() if key not in omitted}
    time_points = metadata.get("time_points")
    if isinstance(time_points, list) and time_points:
        summary["time_point_range"] = [time_points[0], time_points[-1]]
    chunks = metadata.get("chunks")
    if isinstance(chunks, list):
        failed_chunks = [item for item in chunks if isinstance(item, dict) and item.get("success") is False]
        if failed_chunks:
            summary["failed_chunks"] = _compact_value(failed_chunks[:10])
    return summary


def _same_city_dataset_summary(
    dataset: Any,
    *,
    pollutants: list[str],
    target_station_code: str,
) -> dict[str, Any]:
    if not isinstance(dataset, dict):
        return {"success": False, "status": "failed", "summary": "同城数据返回格式异常"}
    records = dataset.get("data")
    if not isinstance(records, list):
        records = []

    base = {
        "success": bool(dataset.get("success") is True),
        "status": dataset.get("status"),
        "summary": dataset.get("summary"),
        "data_kind": dataset.get("data_kind"),
        "data_type": dataset.get("data_type"),
        "record_count": dataset.get("record_count", len(records)),
        "metadata": _metadata_summary(dataset.get("metadata") or {}),
        "summary_mode": "deterministic_same_city_statistics",
        "pollutant_summaries": [],
    }
    if not pollutants:
        base["summary_note"] = "未从工单文本识别污染物，未生成同城污染物对比摘要。"
        return base

    for pollutant in pollutants:
        grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for row in records:
            if not isinstance(row, dict):
                continue
            time_text = _row_time_text(row)
            if not time_text:
                continue
            reading = _pollutant_reading(row, pollutant)
            if reading is None:
                continue
            grouped.setdefault(time_text, []).append((row, reading))

        timeline = []
        notable_hours = []
        classification_counts: dict[str, int] = {}
        target_hour_count = 0
        compared_hour_count = 0
        missing_target_hour_count = 0
        insufficient_comparison_hour_count = 0
        for time_text in sorted(grouped, key=_sort_time_key):
            rows = grouped[time_text]
            target_entry = None
            comparison_entries = []
            all_values = []
            for row, reading in rows:
                value = _number_from_value(reading.get("value"))
                if value is None:
                    continue
                all_values.append(value)
                entry = (row, reading, value)
                if target_station_code and _row_station_code(row) == target_station_code:
                    target_entry = entry
                else:
                    comparison_entries.append(entry)

            target_value = target_entry[2] if target_entry else None
            if target_value is None:
                missing_target_hour_count += 1
            else:
                target_hour_count += 1
            comparison_values = [entry[2] for entry in comparison_entries]
            if comparison_values:
                compared_hour_count += 1
            else:
                insufficient_comparison_hour_count += 1

            classification = _same_city_classification(target_value, comparison_values)
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            comparison_median = _median(comparison_values)
            delta = target_value - comparison_median if target_value is not None and comparison_median is not None else None
            delta_percent = (
                delta / comparison_median * 100
                if delta is not None and comparison_median not in (None, 0)
                else None
            )
            comparison_station_codes = {
                _row_station_code(row)
                for row, _reading, _value in comparison_entries
                if _row_station_code(row)
            }
            target_payload = None
            if target_entry:
                target_payload = {
                    "station_code": _row_station_code(target_entry[0]),
                    "station_name": _row_station_name(target_entry[0]),
                    "value": target_entry[1]["value"],
                    "raw_value": target_entry[1]["raw_value"],
                    "audit_mark": target_entry[1].get("audit_mark"),
                    "field": target_entry[1].get("field"),
                }
            row_summary = {
                "time": time_text,
                "pollutant": pollutant,
                "target": target_payload,
                "same_city": {
                    "station_count": len(comparison_station_codes),
                    "value_count": len(comparison_values),
                    "min": _round_number(min(comparison_values)) if comparison_values else None,
                    "max": _round_number(max(comparison_values)) if comparison_values else None,
                    "median": _round_number(comparison_median),
                    "average": _round_number(sum(comparison_values) / len(comparison_values))
                    if comparison_values else None,
                },
                "target_rank": {
                    "high": _rank_desc(target_value, all_values) if target_value is not None else None,
                    "low": _rank_asc(target_value, all_values) if target_value is not None else None,
                    "total": len(all_values),
                },
                "delta_from_same_city_median": _round_number(delta),
                "delta_percent_from_same_city_median": _round_number(delta_percent),
                "classification": classification,
            }
            timeline.append(row_summary)
            if (
                classification not in {"within_same_city_range"}
                or (target_payload and target_payload.get("audit_mark"))
            ):
                notable_hours.append(row_summary)

        base["pollutant_summaries"].append({
            "pollutant": pollutant,
            "hour_count": len(grouped),
            "target_hour_count": target_hour_count,
            "compared_hour_count": compared_hour_count,
            "missing_target_hour_count": missing_target_hour_count,
            "insufficient_comparison_hour_count": insufficient_comparison_hour_count,
            "classification_counts": classification_counts,
            "notable_hours": notable_hours[:SAME_CITY_SUMMARY_NOTABLE_LIMIT],
            "notable_hours_truncated": len(notable_hours) > SAME_CITY_SUMMARY_NOTABLE_LIMIT,
            "timeline": timeline[:SAME_CITY_SUMMARY_TIMELINE_LIMIT],
            "timeline_truncated": len(timeline) > SAME_CITY_SUMMARY_TIMELINE_LIMIT,
        })
    return base


def _same_city_agent_payload(
    value: Any,
    *,
    pollutants: list[str],
    target_station_code: str,
    raw_resource: dict[str, Any] | None,
) -> Any:
    if not isinstance(value, dict):
        return _compact_result(value)
    payload: dict[str, Any] = {
        "success": bool(value.get("success") is True),
        "status": value.get("status"),
        "data_kind": value.get("data_kind"),
        "comparison_scope": value.get("comparison_scope") or "same_city",
        "target_station_code": value.get("target_station_code") or target_station_code,
        "city_name": value.get("city_name"),
        "summary_mode": "deterministic_summary_with_raw_resource",
        "pollutants": pollutants,
        "raw_resource": raw_resource,
        "agent_reading_note": "首轮审核优先阅读本摘要；同城小时全量原始记录已外置，通常无需读取。",
        "visualization_hint": {
            "recommended_chart": "target_vs_same_city_hourly_band",
            "series": ["target", "same_city_min", "same_city_median", "same_city_max"],
            "source": "station_hour_raw.pollutant_summaries[].timeline",
        },
    }
    for key in ("station_hour_raw", "station_hour_audited"):
        payload[key] = _same_city_dataset_summary(
            value.get(key),
            pollutants=pollutants,
            target_station_code=target_station_code,
        )
    return payload


def _text_blob(*values: Any) -> str:
    chunks: list[str] = []
    for value in values:
        if isinstance(value, dict):
            chunks.append(json.dumps(value, ensure_ascii=False, default=str))
        elif isinstance(value, list):
            chunks.append(json.dumps(value[:40], ensure_ascii=False, default=str))
        else:
            chunks.append(str(value or ""))
    return "\n".join(chunks)


def _routing_text(order: dict[str, Any], detail: dict[str, Any]) -> str:
    text = _text_blob(order, detail)
    wo = detail.get("wo") if isinstance(detail.get("wo"), dict) else {}
    location_values = [
        order.get("stationName"),
        order.get("stationNameStr"),
        order.get("stationCodeStr"),
        order.get("city"),
        order.get("cityName"),
        order.get("district"),
        order.get("districtName"),
        wo.get("stationName"),
        wo.get("stationNameStr"),
        wo.get("stationCodeStr"),
        wo.get("city"),
        wo.get("cityName"),
        wo.get("district"),
        wo.get("districtName"),
    ]
    for value in location_values:
        label = str(value or "").strip()
        if label:
            text = text.replace(label, "")
    return text


def _is_qc_candidate(order: dict[str, Any]) -> bool:
    text = _text_blob(
        order.get("orderTitle"),
        order.get("orderContent"),
        order.get("otherContent"),
        order.get("deviceInfo"),
        order.get("faultProcessType"),
    )
    return any(keyword in text for keyword in QC_KEYWORDS)


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword and keyword in text]


def _classify_sop02_event_type(text: str) -> str:
    if any(keyword in text for keyword in ("流量", "泵", "泵膜", "采样流量")):
        return "flow"
    if any(keyword in text for keyword in ("跳电", "断电", "供电", "复电", "电压", "电流", "UPS", "防雷", "空开")):
        return "power"
    if any(keyword in text for keyword in ("制冷", "温度", "湿度", "空调", "冷凝")):
        return "temperature"
    if any(keyword in text for keyword in ("无数据", "缺失", "断点", "未上传", "上传中断")):
        return "missing"
    if any(keyword in text for keyword in ("零值", "为0", "为 0")):
        return "zero"
    if any(keyword in text for keyword in ("恒值", "不变")):
        return "constant"
    if any(keyword in text for keyword in ("低值", "偏低", "降低")):
        return "low"
    if any(keyword in text for keyword in ("高值", "偏高", "升高", "离群")):
        return "high"
    return "uncertain"


def _classify_transmission_event_type(text: str) -> str:
    if any(keyword in text for keyword in ("补传", "重传", "断点续传")):
        return "retransmitted"
    if any(keyword in text for keyword in ("时间戳", "重复", "错位", "不连续")):
        return "timestamp_error"
    if any(keyword in text for keyword in ("未上传", "无数据上传", "上传中断", "平台未更新", "未更新", "接收中断")):
        return "not_uploaded"
    if any(keyword in text for keyword in ("离线", "网络", "通信", "通讯", "VPN", "路由器", "交换机", "数采仪", "工控机")):
        return "offline"
    if any(keyword in text for keyword in ("无数据", "缺失", "断点")):
        return "missing"
    return "uncertain"


SOP02_EVENT_TYPE_LABELS = {
    "high": "偏高",
    "low": "偏低",
    "zero": "零值",
    "constant": "恒值",
    "missing": "缺失",
    "flow": "流量异常",
    "power": "供电异常",
    "temperature": "温度异常",
    "uncertain": "待核验",
}


def _review_display_issue(route: dict[str, Any]) -> str:
    """Describe the routed SOP and observed event without a subtype taxonomy."""
    sop_id = str(route.get("sop_id") or "")
    if sop_id == "SOP-01":
        return "质控/校准类异常"
    if sop_id == "SOP-03":
        return "数据传输异常"
    if sop_id == "SOP-02":
        return SOP02_EVENT_TYPE_LABELS.get(str(route.get("fault_event_type") or ""), "监测数据/环境异常")
    return f"{sop_id or 'SOP-UNMAPPED'} 审核事件"


def _detail_from_result(detail_result: Any) -> dict[str, Any]:
    rows = detail_result.get("data") if isinstance(detail_result, dict) else []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {}


def _review_route(order: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any] | None:
    text = _routing_text(order, detail)
    qc_keywords = tuple(keyword for keyword in QC_KEYWORDS if keyword != "复测")
    qc_hits = _keyword_hits(text, qc_keywords)
    transmission_hits = _keyword_hits(text, TRANSMISSION_KEYWORDS)
    sop02_hits = _keyword_hits(text, SOP02_KEYWORDS)
    if sop02_hits:
        return {
            "sop_id": "SOP-02",
            "event_type": REVIEW_EVENT_TYPE,
            "review_type": "fault_work_order_env_sop02",
            "review_submit_tool": "jiangsu_submit_fault_work_order_review",
            "route_reason": "命中监测数据、采样、供电或站房环境异常关键词",
            "keyword_hits": sop02_hits[:30],
            "qc_keyword_hits": qc_hits[:20],
            "fault_event_type": _classify_sop02_event_type(text),
        }
    if qc_hits:
        return {
            "sop_id": "SOP-01",
            "event_type": REVIEW_EVENT_TYPE,
            "review_type": "fault_work_order_qc_sop01",
            "review_submit_tool": "jiangsu_submit_fault_work_order_review",
            "route_reason": "命中质控/校准/仪器测量链关键词，且未命中 SOP-02 采样、供电或站房环境异常关键词",
            "keyword_hits": qc_hits[:20],
        }
    if transmission_hits:
        return {
            "sop_id": "SOP-03",
            "event_type": REVIEW_EVENT_TYPE,
            "review_type": "fault_work_order_transmission_sop03",
            "review_submit_tool": "jiangsu_submit_fault_work_order_review",
            "route_reason": "命中数据传输、平台离线、未上传或补传关键词，且未命中测量/采样/供电类 SOP-02 关键词",
            "keyword_hits": transmission_hits[:30],
            "fault_event_type": _classify_transmission_event_type(text),
        }
    return None


def _extract_pollutants(*values: Any) -> list[str]:
    text = _text_blob(*values).upper().replace(" ", "")
    pollutants: list[str] = []
    for pollutant, aliases in POLLUTANT_ALIASES.items():
        if any(_pollutant_alias_in_text(text, alias) for alias in aliases):
            pollutants.append(pollutant)
    return pollutants


def _pollutant_alias_in_text(text: str, alias: str) -> bool:
    alias_text = alias.upper().replace(" ", "")
    if re.fullmatch(r"[A-Z0-9_.]+", alias_text):
        return re.search(rf"(?<![A-Z0-9_.]){re.escape(alias_text)}(?![A-Z0-9_.])", text) is not None
    return alias_text in text


def _station_from_order(order: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    wo = {}
    if isinstance(detail, dict):
        wo = detail.get("wo") if isinstance(detail.get("wo"), dict) else {}
    return {
        "station_code": str(
            order.get("stationCodeStr")
            or wo.get("stationCodeStr")
            or wo.get("stationCode")
            or ""
        ).strip(),
        "unique_code": str(order.get("uniqueCode") or wo.get("uniqueCode") or "").strip(),
        "station_name": str(order.get("stationName") or wo.get("stationName") or "").strip(),
        "city_name": str(order.get("city") or wo.get("city") or wo.get("cityName") or "").strip(),
    }


def _device_from_order(order: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    wo = {}
    if isinstance(detail, dict):
        wo = detail.get("wo") if isinstance(detail.get("wo"), dict) else {}
    return {
        "device_id": str(
            order.get("deviceId")
            or order.get("deviceID")
            or order.get("devId")
            or wo.get("deviceId")
            or wo.get("deviceID")
            or wo.get("devId")
            or wo.get("deviceCode")
            or ""
        ).strip(),
        "device_type": str(
            order.get("deviceType")
            or order.get("deviceTypeName")
            or wo.get("deviceType")
            or wo.get("deviceTypeName")
            or wo.get("deviceName")
            or ""
        ).strip(),
        "device_info": str(order.get("deviceInfo") or wo.get("deviceInfo") or "").strip(),
    }


def _floor_to_day_start(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _ceil_to_day_end(value: datetime) -> datetime:
    return value.replace(hour=23, minute=59, second=59, microsecond=0)


def _find_fault_process_anchor(detail: dict[str, Any]) -> dict[str, Any] | None:
    rows = detail.get("details") if isinstance(detail.get("details"), list) else []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        step = str(row.get("processStep") or "").strip()
        step_name = str(row.get("processStepName") or "").strip()
        if step != "FaultProcess" and "故障处理" not in step_name:
            continue
        process_time = row.get("processTimeStr")
        parsed = _parse_datetime(process_time)
        if parsed is None:
            continue
        return {
            "time": parsed,
            "processTimeStr": str(process_time).strip(),
            "field": "processTimeStr",
            "source": f"work_order.detail.details[{index}].processTimeStr",
            "step": step,
            "step_name": step_name,
        }
    return None


def _time_entry_payload(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    return {
        "time": _format_time(entry["time"]),
        "field": entry.get("field"),
        "source": entry.get("source"),
        "boundary_time": entry.get("boundary_time"),
        "step": entry.get("step"),
        "step_name": entry.get("step_name"),
    }


def _evidence_window(order: dict[str, Any], detail: dict[str, Any], now: datetime) -> dict[str, Any]:
    create_time = _parse_datetime(order.get("createTime"))
    if create_time is None:
        raise ValueError("工单创建时间缺失，无法计算证据窗口")

    fault_process_anchor = _find_fault_process_anchor(detail)
    if fault_process_anchor is None:
        raise ValueError("未找到故障处理流转记录，无法计算证据窗口")
    process_time = _parse_datetime(fault_process_anchor.get("processTimeStr"))
    if process_time is None:
        raise ValueError("故障处理流转记录缺少 processTimeStr，无法计算证据窗口")

    start = _floor_to_day_start(create_time - timedelta(days=1))
    end = _ceil_to_day_end(process_time)
    if end < start:
        raise ValueError("故障处理时间早于工单创建前一天起点，无法计算证据窗口")
    lifecycle_start = create_time
    lifecycle_end = process_time
    fault_start_anchor = {
        "time": create_time,
        "field": "createTime",
        "source": "work_order.list_item.createTime",
        "derived": "create_time_minus_1_day_midnight",
        "boundary_time": _format_time(start),
    }
    processing_end_anchor = {
        "time": process_time,
        "field": "processTimeStr",
        "source": fault_process_anchor.get("source"),
        "derived": "fault_process_day_235959",
        "boundary_time": _format_time(end),
        "step": fault_process_anchor.get("step"),
        "step_name": fault_process_anchor.get("step_name"),
    }
    return {
        "start": start,
        "end": end,
        "lifecycle_start": lifecycle_start,
        "lifecycle_end": lifecycle_end,
        "query_window_truncated": False,
        "anchor_count": 2,
        "fault_start_anchor": fault_start_anchor,
        "processing_end_anchor": processing_end_anchor,
    }


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _iter_time_chunks(start: datetime, end: datetime, *, max_days: int) -> list[tuple[datetime, datetime]]:
    if start >= end:
        return [(start, end)]
    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    delta = timedelta(days=max(1, max_days))
    while cursor < end:
        chunk_end = min(end, cursor + delta)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def _iter_hour_points(start: datetime, end: datetime) -> list[datetime]:
    if start > end:
        return []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    limit = end.replace(minute=0, second=0, microsecond=0)
    points: list[datetime] = []
    while cursor <= limit:
        points.append(cursor)
        cursor += timedelta(hours=1)
    return points


def _find_first(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in keys and item not in (None, ""):
                return item
        for item in value.values():
            found = _find_first(item, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first(item, keys)
            if found not in (None, ""):
                return found
    return None


def _qc_task_refs(qc_history: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in qc_history.get("data") or []:
        if not isinstance(row, dict):
            continue
        r_id = _find_first(row, {"rId", "RId", "rid", "id"})
        r_start = _find_first(row, {"rStart", "RStart", "startTime", "sStart"})
        end_time = _find_first(row, {"endTime", "EndTime", "finishTime", "finish_time"})
        if not r_id or not r_start:
            continue
        ref = {
            "r_id": str(r_id).strip(),
            "r_start": str(r_start).strip(),
            "end_time": str(end_time or "").strip(),
            "qc_type": str(_find_first(row, {"qcType", "QCType", "qctype"}) or "").strip(),
            "pollutant": str(
                _find_first(row, {"poll", "Poll", "pollutant", "pollutantCode"})
                or ""
            ).strip(),
            "qc_result": str(_find_first(row, {"qcResult", "QCResult", "result"}) or "").strip(),
            "history_detail": _compact_value(_find_first(row, {"HistoryDetail", "historyDetail"}) or {}),
            "data_values": _compact_value(_find_first(row, {"DataValues", "dataValues"}) or []),
            "result_values": _compact_value(_find_first(row, {"ResultValues", "resultValues"}) or []),
            "history_row": _compact_value(row),
        }
        identity = f"{ref['r_start']}::{ref['r_id']}"
        if identity not in {f"{item['r_start']}::{item['r_id']}" for item in refs}:
            refs.append(ref)
        if len(refs) >= MAX_QC_TASK_DETAILS:
            break
    return refs


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _parse_json_blob(value: Any) -> tuple[Any | None, str | None]:
    if isinstance(value, (dict, list)):
        return value, None
    text = str(value or "").strip()
    if not text:
        return None, None
    parse_error: str | None = None
    for candidate in (text, text.replace("\ufeff", "")):
        try:
            return json.loads(candidate), None
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    return None, parse_error


def _qc_step_phase(label: str, detail: str) -> str | None:
    text = f"{label} {detail}".strip()
    if not text:
        return None
    for keywords, phase in (
        (("参数", "检查"), "参数检查"),
        (("开始", "质控"), "开始质控任务"),
        (("进行", "检查"), "质控进行中检查"),
        (("稳定", "读数"), "稳定后读数"),
        (("结束", "质控"), "结束质控任务"),
    ):
        if all(keyword in text for keyword in keywords):
            return phase
    return None


def _qc_step_payload(item: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        label = str(item or "").strip()
        return {
            "index": index + 1,
            "phase": None,
            "label": label or f"步骤 {index + 1}",
            "time": "",
            "status": "",
            "detail": "",
        }
    label = _first_text(
        item.get("stepName"),
        item.get("StepName"),
        item.get("name"),
        item.get("title"),
        item.get("taskName"),
        item.get("processStepName"),
        item.get("eventName"),
        item.get("message"),
        item.get("text"),
    )
    detail = _first_text(
        item.get("detail"),
        item.get("description"),
        item.get("content"),
        item.get("message"),
        item.get("text"),
        item.get("remark"),
    )
    time_text = _first_text(
        item.get("time"),
        item.get("recordTime"),
        item.get("stepTime"),
        item.get("startTime"),
        item.get("endTime"),
        item.get("rStart"),
        item.get("sStart"),
        item.get("createTime"),
    )
    status = _first_text(
        item.get("status"),
        item.get("result"),
        item.get("state"),
        item.get("stepStatus"),
        item.get("qcResult"),
        item.get("outcome"),
    )
    return {
        "index": index + 1,
        "phase": _qc_step_phase(label, detail),
        "label": label or f"步骤 {index + 1}",
        "time": time_text,
        "status": status,
        "detail": detail,
    }


def _qc_status_snapshot(status: Any) -> dict[str, Any]:
    if isinstance(status, BaseException):
        return {
            "success": False,
            "parse_error": str(status),
            "steps": [],
            "history_detail": None,
            "data_values": [],
            "result_values": [],
        }
    if not isinstance(status, dict):
        return {
            "success": False,
            "parse_error": "质控状态返回格式异常",
            "steps": [],
            "history_detail": None,
            "data_values": [],
            "result_values": [],
        }
    data = status.get("data")
    if not isinstance(data, dict):
        return {
            "success": bool(status.get("success") is True),
            "parse_error": "质控状态 data 缺失",
            "steps": [],
            "history_detail": None,
            "data_values": [],
            "result_values": [],
        }
    parsed_json, parse_error = _parse_json_blob(data.get("jsonStr"))
    steps_source: list[Any] = []
    if isinstance(parsed_json, dict):
        for key in ("Steps", "steps", "StepList", "stepList", "TaskSteps", "taskSteps"):
            candidate = parsed_json.get(key)
            if isinstance(candidate, list):
                steps_source = candidate
                break
    elif isinstance(parsed_json, list):
        steps_source = parsed_json
    if not steps_source:
        for key in ("Steps", "steps", "StepList", "stepList", "TaskSteps", "taskSteps"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                steps_source = candidate
                break

    history_detail = None
    data_values: Any = []
    result_values: Any = []
    if isinstance(parsed_json, dict):
        history_detail = parsed_json.get("HistoryDetail") or parsed_json.get("historyDetail")
        data_values = parsed_json.get("DataValues") or parsed_json.get("dataValues") or []
        result_values = parsed_json.get("ResultValues") or parsed_json.get("resultValues") or []
    if history_detail is None:
        history_detail = data.get("HistoryDetail") or data.get("historyDetail")
    if not data_values:
        data_values = data.get("DataValues") or data.get("dataValues") or []
    if not result_values:
        result_values = data.get("ResultValues") or data.get("resultValues") or []

    steps = [
        _qc_step_payload(item, index=index)
        for index, item in enumerate(steps_source[:60] if isinstance(steps_source, list) else [])
    ]
    snapshot: dict[str, Any] = {
        "success": bool(status.get("success") is True),
        "status": _first_text(data.get("status"), data.get("taskStatus"), data.get("qcStatus")),
        "message": _first_text(data.get("msg"), data.get("message"), data.get("summary")),
        "step_count": len(steps),
        "steps": steps,
        "history_detail": _compact_value(history_detail or {}),
        "data_values": _compact_value(data_values or []),
        "result_values": _compact_value(result_values or []),
    }
    if parse_error:
        snapshot["parse_error"] = parse_error
    if isinstance(parsed_json, dict):
        snapshot["json_keys"] = sorted(str(key) for key in parsed_json.keys())
    return snapshot


def _station_data_payload(
    records: list[dict[str, Any]],
    *,
    data_type: int,
    data_kind: str,
    max_records: int = EVIDENCE_MAX_RECORDS,
) -> dict[str, Any]:
    compact, filter_metadata = compact_air_quality_records(records)
    return {
        "success": True,
        "data_kind": data_kind,
        "data_type": data_type,
        "record_count": len(compact),
        "returned_records": min(len(compact), max_records),
        "data": [_compact_value(item) for item in compact[:max_records]],
        "metadata": filter_metadata,
    }


def _has_records(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    record_count = result.get("record_count")
    if isinstance(record_count, int) and record_count > 0:
        return True
    data = result.get("data")
    if isinstance(data, list):
        return bool(data)
    if isinstance(data, dict):
        return any(_has_records(item) for item in data.values())
    return any(_has_records(item) for item in result.values() if isinstance(item, (dict, list)))


def _append_failed_evidence_gaps(
    gaps: list[dict[str, str]],
    *,
    group: str,
    source: dict[str, Any],
    items: dict[str, str],
    role: str = "core",
) -> None:
    for key, label in items.items():
        result = source.get(key)
        if not isinstance(result, dict) or result.get("success") is not False:
            continue
        summary = str(result.get("summary") or result.get("status") or "接口返回失败").strip()
        gaps.append({
            "group": group,
            "item": label,
            "reason": f"{summary}；该证据缺口不得用同组其他数据自动替代。",
            "role": role,
        })


def _sop02_evidence_gaps(
    *,
    route: dict[str, Any],
    station: dict[str, Any],
    pollutants: list[str],
    work_order_detail: dict[str, Any],
    monitoring: dict[str, Any],
    station_alarm: dict[str, Any],
    environment: dict[str, Any],
    same_city_monitoring: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not station.get("station_code"):
        gaps.append({"group": "工单详单", "item": "站点编码", "reason": "无法唯一定位本站监测、告警和动环证据。", "role": "core"})
    if not station.get("city_name"):
        gaps.append({"group": "邻站/同城站", "item": "城市字段", "reason": "无法自动展开同城站小时数据对比。", "role": "supporting"})
    if not pollutants:
        gaps.append({"group": "工单详单", "item": "影响污染物", "reason": "标题、内容和详单中未解析到明确污染物。", "role": "core"})
    if not _has_records(work_order_detail):
        gaps.append({"group": "工单详单", "item": "详单接口", "reason": "详单接口未返回可核验记录。", "role": "core"})
    if not _has_records(monitoring):
        gaps.append({"group": "监测数据", "item": "本站 5 分钟/小时数据", "reason": "未取得可核验的本站时序数据。", "role": "core"})
    _append_failed_evidence_gaps(
        gaps,
        group="监测数据",
        source=monitoring,
        items={
            "station_5minute_raw": "本站 5 分钟原始数据",
            "station_5minute_audited": "本站 5 分钟审核数据",
            "station_hour_raw": "本站小时原始数据",
            "station_hour_audited": "本站小时审核数据",
        },
        role="core",
    )
    if not _has_records(station_alarm):
        gaps.append({"group": "设备参数", "item": "告警/参数记录", "reason": "未取得故障期间流量、泵、制冷、供电或设备告警证据。", "role": "core"})
    if not _has_records(environment):
        gaps.append({"group": "动环与供电", "item": "站房动环历史", "reason": "未取得温湿度、电压、电流或采样参数历史曲线。", "role": "core"})
    if not _has_records(same_city_monitoring):
        gaps.append({"group": "邻站/同城站", "item": "同城小时数据", "reason": "未取得同城站小时对比数据。", "role": "supporting"})
    _append_failed_evidence_gaps(
        gaps,
        group="邻站/同城站",
        source=same_city_monitoring,
        items={
            "station_hour_raw": "同城小时原始数据",
            "station_hour_audited": "同城小时审核数据",
        },
        role="supporting",
    )
    gaps.append({
        "group": "设备参数",
        "item": "流量/泵/制冷等专用历史参数",
        "reason": "当前自动取证尚未接入独立设备参数历史接口；该类参数默认作为辅助/反证证据，只有直接指向故障机理时才升为核心。",
        "role": "supporting",
    })
    return gaps


def _unavailable_evidence(summary: str, *, role: str = "core") -> dict[str, Any]:
    return {
        "success": False,
        "status": "unavailable",
        "summary": summary,
        "metadata": {"role": role, "reason": "not_integrated"},
        "data": [],
    }


def _monitoring_continuity_summary(monitoring: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(monitoring, dict):
        return _unavailable_evidence("监测数据格式无效，无法核验平台时间戳连续性。")
    dataset_counts: dict[str, int] = {}
    failed_datasets: list[str] = []
    for key in ("station_5minute_raw", "station_5minute_audited", "station_hour_raw", "station_hour_audited"):
        item = monitoring.get(key)
        if not isinstance(item, dict):
            dataset_counts[key] = 0
            failed_datasets.append(key)
            continue
        dataset_counts[key] = int(item.get("record_count") or 0)
        if item.get("success") is False:
            failed_datasets.append(key)
    has_records = any(count > 0 for count in dataset_counts.values())
    if not has_records:
        return {
            "success": False,
            "status": "empty",
            "summary": "平台 5 分钟/小时原始与审核数据均未返回记录，无法仅凭平台数据判断断点和补传完整性。",
            "metadata": {"dataset_counts": dataset_counts, "failed_datasets": failed_datasets},
            "data": [],
        }
    status = "partial" if failed_datasets else "available"
    return {
        "success": not failed_datasets,
        "status": status,
        "summary": (
            "已固化平台 5 分钟/小时原始与审核数据，可用于人工核验断点、重复和时间戳连续性；"
            "本地缓存、平台接收明细和补传回执仍需单独证据。"
        ),
        "metadata": {"dataset_counts": dataset_counts, "failed_datasets": failed_datasets},
        "data": [],
    }


def _sop03_evidence_gaps(
    *,
    route: dict[str, Any],
    station: dict[str, Any],
    pollutants: list[str],
    work_order_detail: dict[str, Any],
    monitoring: dict[str, Any],
    station_alarm: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not station.get("station_code"):
        gaps.append({"group": "工单详单", "item": "站点编码", "reason": "无法唯一定位平台监测数据、通信告警和本地证据。", "role": "core"})
    if not pollutants:
        gaps.append({"group": "工单详单", "item": "影响污染物", "reason": "标题、内容和详单中未解析到明确污染物；传输缺失仍需核验各污染物是否同步缺失。", "role": "core"})
    if not _has_records(work_order_detail):
        gaps.append({"group": "工单详单", "item": "详单接口", "reason": "详单接口未返回可核验记录。", "role": "core"})
    if not _has_records(monitoring):
        gaps.append({"group": "平台监测数据", "item": "5 分钟/小时平台数据", "reason": "未取得可核验的平台时序数据，无法判断断点、重复、错位和补传后完整性。", "role": "core"})
    _append_failed_evidence_gaps(
        gaps,
        group="平台监测数据",
        source=monitoring,
        items={
            "station_5minute_raw": "本站 5 分钟原始数据",
            "station_5minute_audited": "本站 5 分钟审核数据",
            "station_hour_raw": "本站小时原始数据",
            "station_hour_audited": "本站小时审核数据",
        },
        role="core",
    )
    if not _has_records(station_alarm):
        gaps.append({"group": "通信告警", "item": "网络/数采/平台链路告警", "reason": "未取得网络、通信、工控机、数采仪或平台链路告警证据。", "role": "core"})
    gaps.extend([
        {
            "group": "本地数据",
            "item": "设备本地数据和缓存状态",
            "reason": "当前自动取证尚未接入设备或工控机本地缓存接口；不能用平台无数据替代本地是否产生数据的判断。",
            "role": "core",
        },
        {
            "group": "平台接收",
            "item": "最后接收/首次恢复接收记录",
            "reason": "当前自动取证尚未接入平台接收明细接口；不能仅凭工单文字确认上传中断和恢复时间。",
            "role": "core",
        },
        {
            "group": "补传记录",
            "item": "补传起止、成功/失败数量和回执",
            "reason": "当前自动取证尚未接入补传/重传记录接口；补传完整性必须转人工或补充证据确认。",
            "role": "core",
        },
    ])
    return gaps


class JiangsuFaultWorkOrderReviewEventFetcher(DataFetcher):
    """Create immutable SOP evidence packages for province-center review."""

    def __init__(
        self,
        *,
        registry_root: Path | None = None,
        event_publisher: Callable[[TaskEvent], Awaitable[Any]] | None = None,
        clock: Callable[[], datetime] = _now,
        work_order_tool: JiangsuFaultWorkOrdersTool | None = None,
        detail_tool: JiangsuFaultWorkOrderDetailTool | None = None,
        station_data_tool: JiangsuStationDataTool | None = None,
        station_alarm_tool: JiangsuStationAlarmLogsTool | None = None,
        environment_tool: JiangsuStationEnvironmentHistoryTool | None = None,
        qc_history_tool: JiangsuQcTaskHistoryTool | None = None,
        qc_status_tool: JiangsuQcTaskStatusTool | None = None,
        qc_run_log_tool: JiangsuQcRunLogTool | None = None,
        qc_curve_tool: JiangsuQcMonitoringCurveTool | None = None,
    ) -> None:
        super().__init__(
            name="jiangsu_fault_work_order_review_event",
            description="每日轮询江苏省中心待审故障工单，固化 SOP 审核证据包并发布审核事件",
            schedule=POLL_SCHEDULE,
            version="1.0.0",
        )
        self.registry_root = registry_root or get_data_registry()
        self.output_root = self.registry_root / "work_order_review_events"
        self.state_path = self.output_root / "poll_state.json"
        self.event_publisher = event_publisher or self._publish_event
        self.clock = clock
        self.work_order_tool = work_order_tool or JiangsuFaultWorkOrdersTool()
        self.detail_tool = detail_tool or JiangsuFaultWorkOrderDetailTool()
        self.station_data_tool = station_data_tool or JiangsuStationDataTool()
        self.station_alarm_tool = station_alarm_tool or JiangsuStationAlarmLogsTool()
        self.environment_tool = environment_tool or JiangsuStationEnvironmentHistoryTool()
        self.qc_history_tool = qc_history_tool or JiangsuQcTaskHistoryTool()
        self.qc_status_tool = qc_status_tool or JiangsuQcTaskStatusTool()
        self.qc_run_log_tool = qc_run_log_tool or JiangsuQcRunLogTool()
        self.qc_curve_tool = qc_curve_tool or JiangsuQcMonitoringCurveTool()

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.clock()
        state = self._read_state()
        query_kwargs: dict[str, Any] = dict(
            current_points=["省中心审核"],
            workflow_statuses=["ToAssign", "ToAccept", "Doing"],
            order_statuses=["Wait", "Doing", "Finish"],
            fetch_all=True,
            page_size=50,
        )
        create_time_filter = None
        if POLL_CREATE_LOOKBACK_HOURS > 0:
            start = now - timedelta(hours=POLL_CREATE_LOOKBACK_HOURS)
            create_time_filter = [_format_time(start), _format_time(now)]
            query_kwargs.update(start_time=create_time_filter[0], end_time=create_time_filter[1])
        list_result = await self.work_order_tool.execute(**query_kwargs)
        if not list_result.get("success"):
            raise RuntimeError(list_result.get("summary") or "江苏故障工单列表查询失败")
        orders = [item for item in list_result.get("data") or [] if isinstance(item, dict)]
        processed = set(str(item) for item in state.get("processed_event_ids") or [])
        published = 0
        skipped_unmapped = 0
        skipped_existing = 0
        skipped_processed = 0
        failed_evidence = 0
        sop01_candidates = 0
        sop02_candidates = 0
        sop03_candidates = 0
        for order in orders:
            code = str(order.get("workingOrderCode") or "").strip()
            if not code:
                continue
            if has_active_review(code):
                skipped_existing += 1
                continue
            try:
                detail_result = await self._with_timeout(
                    self.detail_tool.execute(working_order_code=code),
                    "故障工单详单查询",
                )
            except Exception as exc:
                failed_evidence += 1
                logger.warning(
                    "jiangsu_fault_work_order_review_detail_failed",
                    work_order_code=code,
                    error=str(exc),
                )
                continue
            detail = _detail_from_result(detail_result)
            route = _review_route(order, detail)
            if route is None:
                skipped_unmapped += 1
                continue
            if route["sop_id"] == "SOP-01":
                sop01_candidates += 1
            elif route["sop_id"] == "SOP-02":
                sop02_candidates += 1
            elif route["sop_id"] == "SOP-03":
                sop03_candidates += 1
            event_id = self._event_id(order, route)
            if event_id in processed:
                skipped_processed += 1
                continue
            try:
                event = await asyncio.wait_for(
                    self._write_event_package(
                        order,
                        event_id,
                        now,
                        detail_result=detail_result,
                        detail=detail,
                        route=route,
                    ),
                    timeout=EVIDENCE_PACKAGE_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                failed_evidence += 1
                logger.warning(
                    "jiangsu_fault_work_order_review_evidence_failed",
                    work_order_code=code,
                    event_id=event_id,
                    sop_id=route.get("sop_id"),
                    error=str(exc),
                )
                continue
            await self.event_publisher(event)
            processed.add(event_id)
            published += 1
            state["processed_event_ids"] = sorted(processed)[-10000:]
            state["last_poll_at"] = now.isoformat()
            self._write_json(self.state_path, state)
            if published >= MAX_EVENTS_PER_RUN:
                break
        state.update({
            "last_poll_at": now.isoformat(),
            "processed_event_ids": sorted(processed)[-10000:],
            "last_query": {
                "strategy": "current_province_center_queue",
                "create_time_filter": create_time_filter,
                "current_points": ["省中心审核"],
            },
        })
        self._write_json(self.state_path, state)
        result = {
            "queried_orders": len(orders),
            "sop01_candidates": sop01_candidates,
            "sop02_candidates": sop02_candidates,
            "sop03_candidates": sop03_candidates,
            "published_events": published,
            "skipped_unmapped": skipped_unmapped,
            "skipped_existing_review": skipped_existing,
            "skipped_processed": skipped_processed,
            "failed_evidence": failed_evidence,
        }
        logger.info("jiangsu_fault_work_order_review_poll_completed", **result)
        return result

    async def _write_event_package(
        self,
        order: dict[str, Any],
        event_id: str,
        created_at: datetime,
        *,
        detail_result: dict[str, Any] | None = None,
        detail: dict[str, Any] | None = None,
        route: dict[str, Any] | None = None,
    ) -> TaskEvent:
        code = str(order.get("workingOrderCode") or "").strip()
        event_dir = self.output_root / created_at.strftime("%Y/%m/%d") / event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        if detail_result is None:
            detail_result = await self._with_timeout(
                self.detail_tool.execute(working_order_code=code),
                "故障工单详单查询",
            )
        if detail is None:
            detail = _detail_from_result(detail_result)
        if route is None:
            route = _review_route(order, detail)
        if route is None:
            raise ValueError("工单未命中已配置的 SOP 路由，无法生成审核证据包")
        station = _station_from_order(order, detail)
        station_code = station["station_code"]
        pollutants = _extract_pollutants(order, detail)
        monitoring_pollutants = pollutants if route["sop_id"] == "SOP-01" else []
        window = _evidence_window(order, detail, created_at)
        window_start = window["start"]
        window_end = window["end"]
        start_text = _format_time(window_start)
        end_text = _format_time(window_end)

        qc_history, station_alarm, environment, monitoring, same_city_monitoring, city_weather = await asyncio.gather(
            self._with_timeout(self.qc_history_tool.execute(
                station_codes=[station_code],
                start_time=start_text,
                end_time=end_text,
            ), "质控历史查询") if station_code else self._empty("缺少站点编码，跳过质控历史查询"),
            self._with_timeout(
                self.station_alarm_tool.execute(station_codes=[station_code]),
                "站房告警查询",
            ) if station_code else self._empty("缺少站点编码，跳过站房告警查询"),
            self._fetch_environment(
                station_code=station_code,
                unique_code=station.get("unique_code") or None,
                start_time=start_text,
                end_time=end_text,
            ) if station_code else self._empty("缺少站点编码，跳过动环查询"),
            self._fetch_monitoring(station_code, start_text, end_text, monitoring_pollutants)
            if station_code else self._empty("缺少站点编码，跳过监测数据查询"),
            self._fetch_same_city_monitoring(
                station=station,
                start_time=start_text,
                end_time=end_text,
            ) if route["sop_id"] == "SOP-02" else self._empty("SOP-01 不需要同城站自动对比取证"),
            fetch_city_weather(
                city_name=station.get("city_name"), start_time=start_text, end_time=end_text,
            ) if route["sop_id"] == "SOP-02" else self._empty("当前 SOP 不需要城市气象取证"),
            return_exceptions=True,
        )
        compact_qc_history = _compact_result(qc_history)
        qc_refs = _qc_task_refs(compact_qc_history)
        qc_statuses = []
        qc_logs = []
        qc_curves = []
        qc_task_details = []
        for ref in qc_refs:
            curve_start = _parse_datetime(ref.get("r_start"))
            curve_end = _parse_datetime(ref.get("end_time")) if ref.get("end_time") else None
            curve_start_text = _format_time(curve_start) if curve_start else str(ref.get("r_start") or "")
            curve_end_text = _format_time(curve_end) if curve_end else str(ref.get("end_time") or "")
            status, logs, curve = await asyncio.gather(
                self._with_timeout(
                    self.qc_status_tool.execute(r_start=ref["r_start"], r_id=ref["r_id"]),
                    "质控任务状态查询",
                ),
                self._with_timeout(
                    self.qc_run_log_tool.execute(r_start=ref["r_start"], r_id=ref["r_id"]),
                    "质控运行日志查询",
                ),
                self._with_timeout(
                    self._fetch_qc_curve(station, ref, curve_start_text, curve_end_text),
                    "质控曲线查询",
                ),
                return_exceptions=True,
            )
            status_snapshot = _qc_status_snapshot(status)
            qc_statuses.append({"task": ref, "result": _compact_result(status), "snapshot": status_snapshot})
            qc_logs.append({"task": ref, "result": _compact_result(logs)})
            qc_curves.append({
                "task": ref,
                "window": {
                    "start": curve_start_text,
                    "end": curve_end_text,
                    "source": "quality_control_history.rStart/endTime",
                },
                "result": _compact_result(curve),
            })
            qc_task_details.append({
                "task": ref,
                "history": {
                    "r_id": ref.get("r_id"),
                    "r_start": ref.get("r_start"),
                    "end_time": ref.get("end_time"),
                    "qc_type": ref.get("qc_type"),
                    "pollutant": ref.get("pollutant"),
                    "qc_result": ref.get("qc_result"),
                    "history_detail": ref.get("history_detail"),
                    "data_values": ref.get("data_values"),
                    "result_values": ref.get("result_values"),
                    "history_row": ref.get("history_row"),
                },
                "status": _compact_result(status),
                "status_detail": status_snapshot,
                "run_log": _compact_result(logs),
                "curve": _compact_result(curve),
                "curve_window": {
                    "start": curve_start_text,
                    "end": curve_end_text,
                    "source": "quality_control_history.rStart/endTime",
                },
            })

        sop_id = str(route["sop_id"])
        device = _device_from_order(order, detail)
        work_order_detail_payload = _compact_result(detail_result, max_records=1)
        monitoring_payload = monitoring if isinstance(monitoring, dict) else _compact_result(monitoring)
        station_alarm_payload = _compact_result(station_alarm)
        environment_payload = _compact_result(environment)
        same_city_monitoring_payload = _compact_same_city_monitoring_payload(same_city_monitoring)
        same_city_raw_resource = None
        raw_resources: list[dict[str, Any]] = []
        if sop_id == "SOP-02" and _same_city_raw_record_counts(same_city_monitoring_payload):
            same_city_raw_path = event_dir / "resources" / "same_city_monitoring_raw.json"
            self._write_json(same_city_raw_path, same_city_monitoring_payload)
            same_city_raw_resource = {
                "name": "same_city_monitoring_raw",
                "path": format_agent_path(same_city_raw_path),
                "content_type": "application/json",
                "record_counts": _same_city_raw_record_counts(same_city_monitoring_payload),
                "summary": "同城小时原始/审核全量记录；首轮审核通常阅读 same_city_monitoring 摘要即可。",
            }
            raw_resources.append(same_city_raw_resource)
        sop02_evidence_gaps = []
        sop03_evidence_gaps = []
        if sop_id == "SOP-02":
            sop02_evidence_gaps = _sop02_evidence_gaps(
                route=route,
                station=station,
                pollutants=pollutants,
                work_order_detail=work_order_detail_payload,
                monitoring=monitoring_payload,
                station_alarm=station_alarm_payload,
                environment=environment_payload,
                same_city_monitoring=same_city_monitoring_payload,
            )
        elif sop_id == "SOP-03":
            sop03_evidence_gaps = _sop03_evidence_gaps(
                route=route,
                station=station,
                pollutants=pollutants,
                work_order_detail=work_order_detail_payload,
                monitoring=monitoring_payload,
                station_alarm=station_alarm_payload,
            )
        review_evidence_gaps = sop02_evidence_gaps or sop03_evidence_gaps
        same_city_agent_payload = (
            _same_city_agent_payload(
                same_city_monitoring_payload,
                pollutants=pollutants,
                target_station_code=station_code,
                raw_resource=same_city_raw_resource,
            )
            if sop_id == "SOP-02"
            else None
        )
        transmission_evidence_payload = (
            {
                "local_data": _unavailable_evidence(
                    "当前自动证据包未接入设备或工控机本地数据/缓存状态接口。"
                ),
                "platform_receipt": _unavailable_evidence(
                    "当前自动证据包未接入平台最后接收、首次恢复接收和接收数量明细接口。"
                ),
                "communication_alarms": station_alarm_payload,
                "platform_monitoring": monitoring_payload,
                "retransmission": _unavailable_evidence(
                    "当前自动证据包未接入补传、重传、成功/失败数量和回执接口。"
                ),
                "timestamp_continuity": _monitoring_continuity_summary(monitoring_payload),
            }
            if sop_id == "SOP-03"
            else None
        )
        collection_notes = [
            "本证据包由只读接口自动抓取，不修改江苏运维平台工单和监测数据。",
            "涉及数据剔除时必须确认污染物、异常起止时间、边界来源和合理性。",
            "工单创建时间不能直接作为无效开始时间，维修完成时间不能自动作为无效结束时间。",
            "自动巡检快照不纳入本证据包：该接口只返回查询时刻状态，不按证据窗口对齐。",
            "本站 5 分钟监测数据按平台宽表整行抓取，不传 pollutantCodes；关联污染物仅用于下游审核聚焦。",
        ]
        if sop_id == "SOP-01":
            collection_notes.extend([
                "SOP-01 要求工单审核结论与数据处置结论分开生成。",
                "质控曲线必须按质控任务 rStart/endTime 查询；缺少任务窗口时直接暴露失败。",
            ])
        elif sop_id == "SOP-02":
            collection_notes.extend([
                "SOP-02 要求区分有效异常、伪值、缺失和暂时不可见，不得把工单申请区间直接作为剔除区间。",
                "同城小时数据仅作为 same_city 对比证据；未实现精确邻站自动选择时必须在审核结论中说明。",
            ])
        elif sop_id == "SOP-03":
            collection_notes.extend([
                "SOP-03 要求区分设备未测量、本地已测量未上传、平台暂时不可见、补传成功和时间戳异常。",
                "当前自动证据包尚未接入本地缓存、平台接收明细和补传回执接口；这些缺口必须进入门禁和审核意见。",
                "传输中断但本地数据完整且补传成功时应优先判断 keep；无测量或本地缺失时应优先判断 missing_no_delete。",
            ])
        evidence = {
            "schema_version": 1,
            "input_profile": "agent_slim_v1",
            "event_id": event_id,
            "event_type": route["event_type"],
            "review_type": route["review_type"],
            "sop_id": sop_id,
            "sop_route": _compact_value(route),
            "created_at": created_at.isoformat(),
            "work_order_code": code,
            "summary": str(order.get("orderTitle") or code),
            "station": station,
            "device": device,
            "pollutants_detected_from_text": pollutants,
            "workflow_node": {
                "current_point": order.get("currentPointName"),
                "workflow_status": order.get("workFlowStatus") or order.get("workFlowStatusStr"),
                "order_status": order.get("orderStatus") or order.get("orderStatusStr"),
                "update_time": order.get("updateTime"),
            },
            "evidence_time_window": {
                "start": start_text,
                "end": end_text,
                "lifecycle_start": (
                    _format_time(window["lifecycle_start"]) if window.get("lifecycle_start") else None
                ),
                "lifecycle_end": (
                    _format_time(window["lifecycle_end"]) if window.get("lifecycle_end") else None
                ),
                "query_window_truncated": bool(window.get("query_window_truncated")),
                "anchor_count": window.get("anchor_count"),
                "hour_chunk_days": EVIDENCE_HOUR_CHUNK_DAYS,
                "five_minute_chunk_days": EVIDENCE_5MIN_CHUNK_DAYS,
                "fault_start_anchor": _time_entry_payload(window.get("fault_start_anchor")),
                "processing_end_anchor": _time_entry_payload(window.get("processing_end_anchor")),
                "rule": (
                    "以工单创建时间为锚点，取创建日前一天 00:00:00 作为起点；"
                    "以故障处理流转记录为锚点，取该日 23:59:59 作为终点；"
                    "缺少工单创建时间或故障处理记录时直接失败；不使用运维单位复核和省中心审核时间作为终点。"
                ),
                "boundary_warning": "该窗口仅用于取证；不得直接作为数据剔除开始或结束时间。",
            },
            "work_order": {
                "list_item": _compact_value(order),
                "detail": work_order_detail_payload,
            },
            "quality_control": {
                "history": compact_qc_history,
                "task_statuses": qc_statuses,
                "run_logs": qc_logs,
                "monitoring_curves": qc_curves,
                "task_details": qc_task_details,
            },
            "monitoring": monitoring_payload,
            "station_alarm_logs": station_alarm_payload,
            "station_environment_history": environment_payload,
            "same_city_monitoring": same_city_agent_payload,
            "city_weather": city_weather if isinstance(city_weather, dict) else {
                "status": "unavailable", "data": [], "scope": "supporting",
                "message": "城市气象取证失败",
            },
            "environmental_fault": (
                {
                    "event_type": route.get("fault_event_type") or "uncertain",
                    "required_evidence": [
                        "工单详单",
                        "监测数据",
                        "动环与供电",
                        "关联污染物",
                        "处置与复测",
                    ],
                    "supporting_evidence": [
                        "设备参数（流量、泵、制冷、切割器/纸带、平台抬放）",
                        "邻站/同城站",
                        "附件照片",
                    ],
                    "rebuttal_evidence": [
                        "同城同步或不同步反证",
                        "设备参数正常但监测异常",
                    ],
                    "evidence_gaps": sop02_evidence_gaps,
                }
                if sop_id == "SOP-02"
                else None
            ),
            "transmission_fault": (
                {
                    "event_type": route.get("fault_event_type") or "uncertain",
                    "required_evidence": [
                        "工单详单",
                        "平台 5 分钟/小时监测断点",
                        "设备本地数据和缓存状态",
                        "平台接收记录",
                        "补传记录",
                        "时间戳连续性",
                    ],
                    "supporting_evidence": [
                        "通信/网络/数采仪告警",
                        "自动巡检在线状态",
                        "附件照片或平台截图",
                    ],
                    "rebuttal_evidence": [
                        "本地数据连续但平台暂时不可见",
                        "平台恢复接收但时间戳重复或错位",
                    ],
                    "evidence_gaps": sop03_evidence_gaps,
                }
                if sop_id == "SOP-03"
                else None
            ),
            "transmission_evidence": transmission_evidence_payload,
            "evidence_gaps": review_evidence_gaps,
            "collection_notes": collection_notes,
            "raw_resources": raw_resources,
        }
        evidence_path = event_dir / "review_evidence_pack.json"
        self._write_json(evidence_path, evidence)
        event = TaskEvent(
            event_id=event_id,
            event_type=route["event_type"],
            occurred_at=_parse_datetime(order.get("updateTime")) or created_at,
            attributes={
                "work_order_code": code,
                "station_code": station_code,
                "station_name": station.get("station_name") or "",
                "alarm_type": _review_display_issue(route),
                "summary": str(order.get("orderTitle") or code),
                "current_point": str(order.get("currentPointName") or ""),
                "sop_id": sop_id,
                "fault_event_type": str(route.get("fault_event_type") or ""),
            },
            payload={
                "work_order_code": code,
                "station": station,
                "summary": str(order.get("orderTitle") or code),
                "evidence_pack_path": format_agent_path(evidence_path),
                "evidence_dir": format_agent_path(event_dir),
                "review_submit_tool": route["review_submit_tool"],
                "sop_id": sop_id,
                "exclusion_review_note": "如建议 partial_exclude 或 exclude，必须在 data_impact 写明明确 start/end，并填写剔除异常区间和合理性判断。",
            },
        )
        self._write_json(event_dir / "event.json", event.model_dump(mode="json"))
        self._ensure_feedback_case(event)
        return event

    async def _fetch_environment(
        self,
        *,
        station_code: str,
        unique_code: str | None,
        start_time: str,
        end_time: str,
    ) -> dict[str, Any]:
        parsed_start = _parse_datetime(start_time)
        parsed_end = _parse_datetime(end_time)
        if parsed_start is None or parsed_end is None:
            return {"success": False, "status": "failed", "summary": "站房动环查询时间解析失败", "data": {}}
        chunks = _iter_time_chunks(parsed_start, parsed_end, max_days=31)
        table_data: list[Any] = []
        chart_data: list[Any] = []
        chunk_results: list[dict[str, Any]] = []
        started_at = time.monotonic()
        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            chunk_start_text = _format_time(chunk_start)
            chunk_end_text = _format_time(chunk_end)
            chunk_started_at = time.monotonic()
            try:
                result = await self._with_timeout(
                    self.environment_tool.execute(
                        station_code=station_code,
                        unique_code=unique_code,
                        start_time=chunk_start_text,
                        end_time=chunk_end_text,
                        time_type="h",
                    ),
                    "站房动环查询",
                )
                success = bool(isinstance(result, dict) and result.get("success") is True)
                data = result.get("data") if isinstance(result, dict) else {}
                chunk_table = data.get("tableData") if isinstance(data, dict) else []
                chunk_chart = data.get("chartData") if isinstance(data, dict) else []
                if isinstance(chunk_table, list):
                    table_data.extend(chunk_table)
                if isinstance(chunk_chart, list):
                    chart_data.extend(chunk_chart)
                chunk_results.append({
                    "index": index,
                    "start": chunk_start_text,
                    "end": chunk_end_text,
                    "success": success,
                    "record_count": len(chunk_table) if isinstance(chunk_table, list) else 0,
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                    **({"summary": result.get("summary")} if isinstance(result, dict) else {}),
                })
            except Exception as exc:
                chunk_results.append({
                    "index": index,
                    "start": chunk_start_text,
                    "end": chunk_end_text,
                    "success": False,
                    "record_count": 0,
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                    "error": str(exc),
                })
        failed_chunks = [item for item in chunk_results if not item["success"]]
        succeeded_chunks = len(chunk_results) - len(failed_chunks)
        success = succeeded_chunks > 0
        if not success:
            status = "failed"
        elif table_data or chart_data:
            status = "partial" if failed_chunks else "success"
        else:
            status = "empty"
        summary = (
            f"站房动环历史分片查询完成：{succeeded_chunks}/{len(chunk_results)} 个分片成功，"
            f"返回 {len(table_data)} 条表格记录。"
        )
        if failed_chunks:
            summary += f"{len(failed_chunks)} 个分片失败，证据包已保留失败原因。"
        return {
            "success": success,
            "status": status,
            "data": {
                "tableData": table_data[:EVIDENCE_MAX_RECORDS],
                "chartData": chart_data[:EVIDENCE_MAX_RECORDS],
            },
            "metadata": {
                "time_range": [start_time, end_time],
                "time_type": "h",
                "chunk_days": 31,
                "chunk_count": len(chunk_results),
                "succeeded_chunk_count": succeeded_chunks,
                "failed_chunk_count": len(failed_chunks),
                "record_count": len(table_data),
                "elapsed_seconds": round(time.monotonic() - started_at, 3),
                "chunks": chunk_results[:80],
            },
            "summary": summary,
        }

    async def _fetch_monitoring(
        self,
        station_code: str,
        start_time: str,
        end_time: str,
        pollutants: list[str],
    ) -> dict[str, Any]:
        # 5-minute rows are fetched as a wide table; detected pollutants only
        # guide downstream review and are not sent as pollutantCodes.
        tasks = [
            self._fetch_monitoring_dataset(
                station_code=station_code,
                start_time=start_time,
                end_time=end_time,
                data_kind=data_kind,
                data_type=data_type,
            )
            for data_kind in ("station_5minute", "station_hour")
            for data_type in (0, 1)
        ]
        pairs = await asyncio.gather(*tasks)
        return dict(pairs)

    async def _fetch_same_city_monitoring(
        self,
        *,
        station: dict[str, Any],
        start_time: str,
        end_time: str,
    ) -> dict[str, Any]:
        city_name = str(station.get("city_name") or "").strip()
        station_code = str(station.get("station_code") or "").strip()
        if not city_name:
            return {
                "success": False,
                "status": "failed",
                "summary": "工单详单未返回城市字段，无法自动查询同城站对比。",
                "data": {},
                "metadata": {
                    "comparison_scope": "same_city",
                    "target_station_code": station_code,
                    "missing_field": "station.city_name",
                },
            }
        tasks = [
            self._fetch_same_city_monitoring_dataset(
                city_name=city_name,
                target_station_code=station_code,
                start_time=start_time,
                end_time=end_time,
                data_type=data_type,
            )
            for data_type in (0, 1)
        ]
        pairs = await asyncio.gather(*tasks)
        return {
            "success": any(value.get("success") for _, value in pairs),
            "status": "success" if any(value.get("success") for _, value in pairs) else "failed",
            "data_kind": "station_hour",
            "comparison_scope": "same_city",
            "target_station_code": station_code,
            "city_name": city_name,
            **dict(pairs),
        }

    async def _fetch_same_city_monitoring_dataset(
        self,
        *,
        city_name: str,
        target_station_code: str,
        start_time: str,
        end_time: str,
        data_type: int,
    ) -> tuple[str, dict[str, Any]]:
        key = f"station_hour_{'raw' if data_type == 0 else 'audited'}"
        parsed_start = _parse_datetime(start_time)
        parsed_end = _parse_datetime(end_time)
        if parsed_start is None or parsed_end is None:
            return key, {
                "success": False,
                "status": "failed",
                "summary": "同城站小时数据查询时间解析失败",
                "data_kind": "station_hour",
                "data_type": data_type,
                "record_count": 0,
                "data": [],
            }
        hour_points = _iter_hour_points(parsed_start, parsed_end)
        if not hour_points:
            hour_points = [parsed_start]
        records: list[dict[str, Any]] = []
        chunk_results: list[dict[str, Any]] = []
        started_at = time.monotonic()
        for index, hour_point in enumerate(hour_points, start=1):
            query_text = _format_time(hour_point)
            chunk_started_at = time.monotonic()
            try:
                chunk_records, payload = await asyncio.wait_for(
                    self.station_data_tool.fetch_raw_records(
                        data_kind="station_hour",
                        city_names=[city_name],
                        start_time=query_text,
                        end_time=query_text,
                        data_type=data_type,
                        station_type="全部",
                    ),
                    timeout=EVIDENCE_CALL_TIMEOUT_SECONDS,
                )
                records.extend(chunk_records)
                chunk_results.append({
                    "index": index,
                    "start": query_text,
                    "end": query_text,
                    "success": True,
                    "record_count": len(chunk_records),
                    "station_count": len(payload.get("codes") or []) if isinstance(payload, dict) else None,
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                })
            except Exception as exc:
                chunk_results.append({
                    "index": index,
                    "start": query_text,
                    "end": query_text,
                    "success": False,
                    "record_count": 0,
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                    "error": str(exc),
                })
        failed_chunks = [item for item in chunk_results if not item["success"]]
        succeeded_chunks = len(chunk_results) - len(failed_chunks)
        if not records and failed_chunks and not succeeded_chunks:
            return key, {
                "success": False,
                "status": "failed",
                "summary": f"江苏同城站小时数据分片查询全部失败：{len(failed_chunks)} 个分片失败。",
                "data_kind": "station_hour",
                "data_type": data_type,
                "record_count": 0,
                "returned_records": 0,
                "data": [],
                "metadata": {
                    "comparison_scope": "same_city",
                    "target_station_code": target_station_code,
                    "city_name": city_name,
                    "time_range": [start_time, end_time],
                    "time_point_count": len(hour_points),
                    "time_points": [_format_time(point) for point in hour_points[:120]],
                    "chunk_count": len(chunk_results),
                    "succeeded_chunk_count": succeeded_chunks,
                    "failed_chunk_count": len(failed_chunks),
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                    "chunks": chunk_results[:80],
                },
            }

        payload = _station_data_payload(
            records,
            data_type=data_type,
            data_kind="station_hour",
            max_records=max(len(records), 1),
        )
        payload["status"] = "partial" if failed_chunks else ("success" if records else "empty")
        payload["success"] = succeeded_chunks > 0
        payload["summary"] = (
            f"江苏同城站小时数据按小时查询完成：{succeeded_chunks}/{len(chunk_results)} 个时间点成功，"
            f"返回 {len(records)} 条记录。"
        )
        if failed_chunks:
            payload["summary"] += f"{len(failed_chunks)} 个分片失败，证据包已保留失败原因。"
        payload.setdefault("metadata", {})
        payload["metadata"].update({
            "comparison_scope": "same_city",
            "target_station_code": target_station_code,
            "city_name": city_name,
            "time_range": [start_time, end_time],
            "time_point_count": len(hour_points),
            "time_points": [_format_time(point) for point in hour_points[:120]],
            "chunk_count": len(chunk_results),
            "succeeded_chunk_count": succeeded_chunks,
            "failed_chunk_count": len(failed_chunks),
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "chunks": chunk_results[:80],
            "query_mode": "hourly_snapshot",
        })
        return key, payload

    async def _fetch_monitoring_dataset(
        self,
        *,
        station_code: str,
        start_time: str,
        end_time: str,
        data_kind: str,
        data_type: int,
    ) -> tuple[str, dict[str, Any]]:
        key = f"{data_kind}_{'raw' if data_type == 0 else 'audited'}"
        parsed_start = _parse_datetime(start_time)
        parsed_end = _parse_datetime(end_time)
        if parsed_start is None or parsed_end is None:
            return key, {
                "success": False,
                "status": "failed",
                "summary": "监测数据查询时间解析失败",
                "data_kind": data_kind,
                "data_type": data_type,
                "record_count": 0,
                "data": [],
            }
        chunk_days = EVIDENCE_5MIN_CHUNK_DAYS if data_kind == "station_5minute" else EVIDENCE_HOUR_CHUNK_DAYS
        chunks = _iter_time_chunks(parsed_start, parsed_end, max_days=chunk_days)
        records: list[dict[str, Any]] = []
        chunk_results: list[dict[str, Any]] = []
        started_at = time.monotonic()
        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            chunk_start_text = _format_time(chunk_start)
            chunk_end_text = _format_time(chunk_end)
            chunk_started_at = time.monotonic()
            try:
                chunk_records, _payload = await asyncio.wait_for(
                    self.station_data_tool.fetch_raw_records(
                        data_kind=data_kind,
                        station_codes=[station_code],
                        start_time=chunk_start_text,
                        end_time=chunk_end_text,
                        data_type=data_type,
                        station_type="全部",
                    ),
                    timeout=EVIDENCE_CALL_TIMEOUT_SECONDS,
                )
                records.extend(chunk_records)
                chunk_results.append({
                    "index": index,
                    "start": chunk_start_text,
                    "end": chunk_end_text,
                    "success": True,
                    "record_count": len(chunk_records),
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                })
            except Exception as exc:
                chunk_results.append({
                    "index": index,
                    "start": chunk_start_text,
                    "end": chunk_end_text,
                    "success": False,
                    "record_count": 0,
                    "elapsed_seconds": round(time.monotonic() - chunk_started_at, 3),
                    "error": str(exc),
                })
        failed_chunks = [item for item in chunk_results if not item["success"]]
        succeeded_chunks = len(chunk_results) - len(failed_chunks)
        if not records and failed_chunks and not succeeded_chunks:
            return key, {
                "success": False,
                "status": "failed",
                "summary": f"江苏站点{data_kind}分片查询全部失败：{len(failed_chunks)} 个分片失败。",
                "data_kind": data_kind,
                "data_type": data_type,
                "record_count": 0,
                "returned_records": 0,
                "data": [],
                "metadata": {
                    "time_range": [start_time, end_time],
                    "chunk_days": chunk_days,
                    "chunk_count": len(chunk_results),
                    "succeeded_chunk_count": succeeded_chunks,
                    "failed_chunk_count": len(failed_chunks),
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                    "chunks": chunk_results[:80],
                },
            }

        payload = _station_data_payload(records, data_type=data_type, data_kind=data_kind)
        payload["status"] = "partial" if failed_chunks else ("success" if records else "empty")
        payload["success"] = succeeded_chunks > 0
        payload["summary"] = (
            f"江苏站点{data_kind}分片查询完成：{succeeded_chunks}/{len(chunk_results)} 个分片成功，"
            f"返回 {len(records)} 条记录。"
        )
        if failed_chunks:
            payload["summary"] += f"{len(failed_chunks)} 个分片失败，证据包已保留失败原因。"
        payload.setdefault("metadata", {})
        payload["metadata"].update({
            "time_range": [start_time, end_time],
            "chunk_days": chunk_days,
            "chunk_count": len(chunk_results),
            "succeeded_chunk_count": succeeded_chunks,
            "failed_chunk_count": len(failed_chunks),
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "chunks": chunk_results[:80],
        })
        return key, payload

    async def _fetch_qc_curve(
        self,
        station: dict[str, Any],
        task_ref: dict[str, Any],
        start_time: str,
        end_time: str,
    ) -> dict[str, Any]:
        if not task_ref.get("pollutant") or not task_ref.get("qc_type"):
            return {
                "success": False,
                "status": "skipped",
                "summary": "质控任务缺少 pollutant 或 qc_type，跳过质控曲线查询",
                "data": [],
            }
        if not start_time or not end_time:
            return {
                "success": False,
                "status": "failed",
                "summary": "质控任务缺少 rStart 或 endTime，无法按任务窗口查询曲线",
                "data": [],
            }
        return await self.qc_curve_tool.execute(
            station_codes=[station["station_code"]],
            pollutant=task_ref["pollutant"],
            qc_type=task_ref["qc_type"],
            start_time=start_time,
            end_time=end_time,
        )

    def _event_id(self, order: dict[str, Any], route: dict[str, Any]) -> str:
        sop_id = str(route.get("sop_id") or "").strip().upper()
        if sop_id not in {"SOP-01", "SOP-02", "SOP-03"}:
            raise ValueError("事件路由缺少合法 sop_id")
        identity = {
            "work_order_code": order.get("workingOrderCode"),
            "current_point": order.get("currentPointName"),
            "workflow_status": order.get("workFlowStatus") or order.get("workFlowStatusStr"),
            "update_time": order.get("updateTime") or order.get("createTime"),
            "sop_id": sop_id,
            "event_type": route.get("event_type") or EVENT_TYPE,
        }
        digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return f"jsworev_{digest[:20]}"

    @staticmethod
    async def _empty(summary: str) -> dict[str, Any]:
        return {"success": False, "status": "skipped", "summary": summary, "data": []}

    @staticmethod
    async def _with_timeout(awaitable: Awaitable[Any], label: str) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=EVIDENCE_CALL_TIMEOUT_SECONDS)
        except TimeoutError:
            return {"success": False, "status": "failed", "summary": f"{label}超时", "data": []}

    def _read_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @staticmethod
    async def _publish_event(event: TaskEvent) -> Any:
        from app.scheduled_tasks import get_scheduled_task_service

        dispatch = await get_scheduled_task_service().publish_event(event)
        try:
            from app.services.jiangsu_feedback_loop import get_feedback_loop_store

            accepted = list(getattr(dispatch, "accepted_task_ids", []) or [])
            if accepted:
                get_feedback_loop_store().record(
                    case_id=f"{REVIEW_SCENARIO}:{event.payload.get('work_order_code')}",
                    scenario=REVIEW_SCENARIO,
                    event_type="review_dispatched",
                    to_status="analyzing",
                    source_record_id=event.event_id,
                    payload={
                        "task_ids": accepted,
                        "execution_ids": list(getattr(dispatch, "execution_ids", []) or []),
                    },
                )
        except Exception as exc:
            logger.warning("jiangsu_work_order_review_feedback_dispatch_failed", event_id=event.event_id, error=str(exc))
        return dispatch

    @staticmethod
    def _ensure_feedback_case(event: TaskEvent) -> None:
        try:
            from app.services.jiangsu_feedback_loop import get_feedback_loop_store

            station = event.payload.get("station") or {}
            get_feedback_loop_store().ensure_case(
                case_id=f"{REVIEW_SCENARIO}:{event.payload.get('work_order_code')}",
                scenario=REVIEW_SCENARIO,
                source_record_id=event.event_id,
                subject={
                    "work_order_code": event.payload.get("work_order_code"),
                    "station_code": station.get("station_code"),
                    "station_name": station.get("station_name"),
                    "sop_id": event.payload.get("sop_id") or event.attributes.get("sop_id"),
                },
            )
        except Exception as exc:
            logger.warning("jiangsu_work_order_review_feedback_case_failed", event_id=event.event_id, error=str(exc))
