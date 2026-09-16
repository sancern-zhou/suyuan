"""Collect read-only evidence packages for Jiangsu smart events.

The event generator only normalizes alarm clues.  This fetcher turns each
event into a bounded, auditable evidence package for a later Agent judgment.
It deliberately records the unavailable video source instead of fabricating
video evidence.

抓取窗口约定（窗口定义见 ``_windows``）：
- ``day``：事件自然日（当天）。小时监测数据、门禁、气象、区域对比、数采报警、
  合规工单、质控记录使用该窗口。
- ``hour``：事件起止时间所在小时构成的完整整点区间（合并事件桶即首末线索所在
  小时之间的全部整点周期）。仪器状态、动环历史使用该窗口；
  动环历史仅在站房设备告警日志出现动环（动力环境）类告警时才抓取。
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, timezone
from typing import Any

from app.fetchers.weather.jiangsu_review_weather import fetch_city_weather
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuFaultWorkOrdersTool,
    JiangsuQcTaskHistoryTool,
    JiangsuStationAlarmLogsTool,
    JiangsuStationEnvironmentHistoryTool,
)
from app.tools.jiangsu.legacy_evidence import JiangsuLegacyEvidenceAdapter, filter_diagnostic_alarm_rows
from app.tools.jiangsu.review_station_selection import select_district_stations
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.tools.jiangsu.station_type import station_type_from_row

EVIDENCE_SCHEMA = "jiangsu_smart_event_evidence/v1"
MAX_INLINE_RECORDS = 500

# 原平台 StationIntegrateAppService.GetAlarmTypeCount 的告警分类：
# 动力环境（动环）= SubCatalog ∈ (1100, 1300)，排除水浸 1205、火警 1207、
# 采样总管温湿度 1218/1219；仪器状态 = (700, 800)。
POWER_ENVIRONMENT_ALARM_EXCLUDED_CODES = {1205, 1207, 1218, 1219}

# 质控记录无严重级别字段（原平台 NewQCHisResult 仅有 QCResult 文本），
# 平台侧质控告警即「质控不合格报警」，因此按文本关键词识别严重记录。
QC_SEVERE_KEYWORDS = ("不合格", "超差", "异常", "失败", "报警", "严重")

# 六项污染物规范名 → 上游字段名别名（按出现顺序取第一个存在的字段）。
POLLUTANT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PM10", ("pM10", "PM10", "pm10")),
    ("PM2.5", ("PM2.5", "pM2_5", "PM2_5", "pm2_5", "PM25", "pm25")),
    ("SO2", ("sO2", "SO2", "so2")),
    ("NO2", ("nO2", "NO2", "no2")),
    ("CO", ("co", "CO", "Co")),
    ("O3", ("o3", "O3")),
)

# 线索文本 → 规范污染物名。NO2 必须先于 NO 匹配，避免子串误命中。
_POLLUTANT_TEXT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PM10", ("PM10", "可吸入颗粒物")),
    ("PM2.5", ("PM2.5", "PM2_5", "PM25", "细颗粒物")),
    ("SO2", ("SO2", "二氧化硫")),
    ("NO2", ("NO2", "二氧化氮")),
    ("NO", ("NO", "一氧化氮")),
    ("CO", ("CO", "一氧化碳")),
    ("O3", ("O3", "臭氧")),
)
_INSTRUMENT_POLLUTANT_CODE_ALIASES: dict[str, tuple[str, ...]] = {
    "PM2.5": ("PM2_5", "PM2.5"),
}


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            pass
    return None


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if number <= -900:  # 上游无效值哨兵。
        return None
    return number


def _record_time(record: dict[str, Any]) -> datetime | None:
    for key in ("timePoint", "TimePoint", "time", "Time"):
        if record.get(key) not in (None, ""):
            return _parse_time(record.get(key))
    return None


def _in_event_window(records: list[dict[str, Any]], window: dict[str, Any]) -> list[dict[str, Any]]:
    start = _parse_time(window.get("start"))
    end = _parse_time(window.get("end"))
    if start is None or end is None:
        return records
    kept: list[dict[str, Any]] = []
    for record in records:
        moment = _record_time(record)
        if moment is not None and start <= moment <= end:
            kept.append(record)
    return kept


def _pollutant_means(records: list[dict[str, Any]]) -> dict[str, float]:
    """按 V3.0 六参顺序计算每项污染物的事件窗口均值。"""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for canonical, aliases in POLLUTANT_FIELDS:
            for alias in aliases:
                if alias not in record:
                    continue
                value = _numeric(record.get(alias))
                if value is not None:
                    sums[canonical] = sums.get(canonical, 0.0) + value
                    counts[canonical] = counts.get(canonical, 0) + 1
                break
    return {
        canonical: round(sums[canonical] / counts[canonical], 3)
        for canonical, _ in POLLUTANT_FIELDS
        if canonical in counts
    }


def _hourly_pollutant_series(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Build timestamp-aligned pollutant means for trend comparison."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for record in records:
        moment = _record_time(record)
        if moment is None:
            continue
        timestamp = moment.strftime("%Y-%m-%dT%H:00:00")
        values = buckets.setdefault(timestamp, {})
        for canonical, aliases in POLLUTANT_FIELDS:
            for alias in aliases:
                if alias not in record:
                    continue
                value = _numeric(record.get(alias))
                if value is not None:
                    values.setdefault(canonical, []).append(value)
                break
    return {
        timestamp: {
            pollutant: round(sum(values) / len(values), 3)
            for pollutant, values in row.items() if values
        }
        for timestamp, row in buckets.items()
    }


def _trend_direction(values: list[float]) -> str:
    if len(values) < 2:
        return "数据不足"
    change = values[-1] - values[0]
    threshold = max(0.001, sum(abs(value) for value in values) / len(values) * 0.05)
    if change > threshold:
        return "上升"
    if change < -threshold:
        return "下降"
    return "基本稳定"


# 事件窗口逐小时对齐序列向前后扩展的小时数，用于呈现异常开始前与结束后的走向。
ALIGNMENT_PADDING_HOURS = 3


def _event_hourly_alignment(
    event_window: dict[str, Any],
    target_records: list[dict[str, Any]],
    peer_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """事件窗口（前后各扩 ``ALIGNMENT_PADDING_HOURS`` 小时）的逐小时对齐序列。

    每行给出同一整点本站（target）与周边站点均值（nearby）的六项污染物值，
    供研判直接核验异常开始、持续、结束时间上是否同步；某侧缺失数据时该侧
    为空对象，保持时间轴对齐。
    """
    start = _parse_time(event_window.get("start"))
    end = _parse_time(event_window.get("end"))
    if start is None or end is None:
        return []
    start = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=ALIGNMENT_PADDING_HOURS)
    end = end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=ALIGNMENT_PADDING_HOURS)
    target = _hourly_pollutant_series(target_records)
    peer = _hourly_pollutant_series(peer_records)
    rows: list[dict[str, Any]] = []
    moment = start
    while moment <= end:
        timestamp = moment.strftime("%Y-%m-%dT%H:00:00")
        rows.append({
            "time": timestamp,
            "target": target.get(timestamp) or {},
            "nearby": peer.get(timestamp) or {},
        })
        moment += timedelta(hours=1)
    return rows


def _build_trend_comparison(
    target_records: list[dict[str, Any]], peer_records: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    target = _hourly_pollutant_series(target_records)
    peer = _hourly_pollutant_series(peer_records)
    result: dict[str, dict[str, Any]] = {}
    for canonical, _ in POLLUTANT_FIELDS:
        common = sorted(set(target) & set(peer))
        target_values = [target[t][canonical] for t in common if canonical in target[t] and canonical in peer[t]]
        peer_values = [peer[t][canonical] for t in common if canonical in target[t] and canonical in peer[t]]
        target_direction = _trend_direction(target_values)
        peer_direction = _trend_direction(peer_values)
        correlation: float | None = None
        if len(target_values) >= 3:
            target_mean = sum(target_values) / len(target_values)
            peer_mean = sum(peer_values) / len(peer_values)
            numerator = sum(
                (mine - target_mean) * (other - peer_mean)
                for mine, other in zip(target_values, peer_values)
            )
            target_scale = sum((value - target_mean) ** 2 for value in target_values) ** 0.5
            peer_scale = sum((value - peer_mean) ** 2 for value in peer_values) ** 0.5
            if target_scale and peer_scale:
                correlation = round(numerator / (target_scale * peer_scale), 3)
        if len(target_values) < 2:
            consistency = "数据不足"
        elif correlation is None:
            consistency = "一致" if target_direction == peer_direction else "不一致"
        elif correlation >= 0.7:
            consistency = "一致"
        elif correlation >= 0.3:
            consistency = "部分一致"
        else:
            consistency = "不一致"
        result[canonical] = {
            "target_direction": target_direction,
            "nearby_direction": peer_direction,
            "direction_consistent": consistency == "一致",
            "consistency": consistency,
            "pearson_correlation": correlation,
            "aligned_hours": len(target_values),
        }
    return result


def _pollutant_in_text(text: str, alias: str) -> bool:
    return (
        re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.IGNORECASE)
        is not None
    )


def _target_pollutants(event: dict[str, Any]) -> list[str]:
    """从全部合并告警提取目标污染物；未识别时查询六项污染物。"""
    texts = [
        str(event.get("primary_clue_tag") or ""),
        str(event.get("alarm_content") or ""),
        str(event.get("source_alarm_rule_type") or ""),
    ]
    for tag in event.get("clue_tags") or []:
        if isinstance(tag, dict) and not tag.get("detected") and (
            tag.get("tag_category") == "报警" or tag.get("tag_source") == "子站报警"
        ):
            texts.extend(
                str(tag.get(key) or "") for key in ("tag_name", "tag_object", "tag_display_text", "alarm_content")
            )
    evidence = event.get("evidence") or {}
    alarms = [*(evidence.get("alarms") or []), evidence.get("alarm")]
    for alarm in alarms:
        if isinstance(alarm, dict):
            texts.extend(str(alarm.get(key) or "") for key in (
                "content", "alarmContent", "description", "pollutantCode", "pollutantName",
            ))
    text = unicodedata.normalize("NFKC", " ".join(texts))
    found = [
        name
        for name, aliases in _POLLUTANT_TEXT_ALIASES
        if any(_pollutant_in_text(text, alias) for alias in aliases)
    ]
    return found or ["PM10", "PM2.5", "SO2", "NO2", "CO", "O3"]


def _instrument_pollutant_codes(pollutants: list[str]) -> list[str]:
    return [
        code
        for name in pollutants
        for code in _INSTRUMENT_POLLUTANT_CODE_ALIASES.get(name, (name,))
    ]


def _is_power_environment_alarm(row: dict[str, Any]) -> bool:
    raw = row.get("AlarmType")
    if raw is None:
        raw = row.get("alarmType")
    if raw is None:
        raw = row.get("SubCatalog")
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return False
    return 1100 < code < 1300 and code not in POWER_ENVIRONMENT_ALARM_EXCLUDED_CODES


def _power_environment_alarms(result: Any) -> list[dict[str, Any]]:
    """从站房设备告警日志结果中提取动环（动力环境）类告警。"""
    rows: list[dict[str, Any]] = []
    data = result.get("data") if isinstance(result, dict) else None
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        inner = item.get("result") if isinstance(item.get("result"), dict) else {}
        for row in inner.get("alarmLogs") or []:
            if isinstance(row, dict) and _is_power_environment_alarm(row):
                rows.append(row)
    return rows


def _filter_station_alarm_noise(result: Any) -> Any:
    """站房设备告警与数采报警同源混入自监控噪声（数据库/进程资源类），入包前复用同一诊断过滤器剔除。"""
    if not isinstance(result, dict) or not isinstance(result.get("data"), list):
        return result
    source_count = 0
    kept_count = 0
    for item in result["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("result"), dict):
            continue
        inner = item["result"]
        rows, stats = filter_diagnostic_alarm_rows(inner.get("alarmLogs") or [])
        inner["alarmLogs"] = rows
        source_count += stats["source_record_count"]
        kept_count += stats["diagnostic_record_count"]
    suppressed = source_count - kept_count
    if not suppressed:
        return result
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    metadata["record_count"] = kept_count
    metadata["alarm_filter"] = {
        "source_record_count": source_count,
        "diagnostic_record_count": kept_count,
        "suppressed_record_count": suppressed,
    }
    result["metadata"] = metadata
    result["summary"] = (
        f"站房告警查询完成：保留 {kept_count} 条诊断告警，"
        f"过滤 {suppressed} 条非诊断性系统告警。"
    )
    return result


def _qc_record_is_severe(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    text = " ".join(
        str(row.get(key) or "")
        for key in ("qcResult", "QCResult", "qc_result", "tstatusStr", "TStatusStr", "result")
    ).strip()
    if not text:
        return False
    if any(keyword in text for keyword in QC_SEVERE_KEYWORDS):
        return True
    return "合格" not in text


def _qc_severe_only(result: dict[str, Any]) -> dict[str, Any]:
    """质控操作记录只保留严重告警类型（不合格/超差等非合格结果）。"""
    data = result.get("data")
    if not isinstance(data, list):
        return result
    total = result.get("record_count")
    total_text = total if total is not None else len(data)
    kept = [row for row in data if _qc_record_is_severe(row)]
    result["data"] = kept
    result["record_count"] = len(kept)
    result["returned_records"] = len(kept)
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    metadata["qc_severe_only"] = True
    metadata["total_record_count"] = total_text
    result["metadata"] = metadata
    result["status"] = "success" if kept else "empty"
    base_summary = str(result.get("summary") or "质控任务查询完成。").rstrip("。")
    result["summary"] = f"{base_summary}；仅保留严重告警类型记录 {len(kept)}/{total_text} 条。"
    return result


def _compact(value: Any, *, depth: int = 0, max_items: int = MAX_INLINE_RECORDS) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 2000 else value[:2000] + "…[truncated]"
    if depth >= 5:
        return "[nested data omitted]" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        return {
            str(key): _compact(item, depth=depth + 1, max_items=max_items)
            for key, item in value.items()
        }
    return value


def _compact_result(result: Any, *, max_records: int = MAX_INLINE_RECORDS) -> dict[str, Any]:
    if isinstance(result, BaseException):
        return {"success": False, "status": "failed", "summary": str(result), "data": []}
    if not isinstance(result, dict):
        return {"success": False, "status": "failed", "summary": "返回格式异常", "data": []}
    data = result.get("data")
    metadata = _compact(result.get("metadata") or {})
    declared_count = metadata.get("record_count") if isinstance(metadata, dict) else None
    try:
        declared_count = int(declared_count) if declared_count is not None else None
    except (TypeError, ValueError):
        declared_count = None
    if isinstance(data, list):
        compact_data = [_compact(item) for item in data[:max_records]]
        record_count = declared_count if declared_count is not None else len(data)
    else:
        compact_data = _compact(data if data is not None else {})
        record_count = len(data) if isinstance(data, dict) else 0
    success = result.get("success")
    if success is None:
        # 气象等源不带 success 键，按正向 status 推断，避免成功结果被记为 gap。
        success = result.get("status") in {"success", "partial"}
    return {
        "success": bool(success),
        "status": result.get("status"),
        # 气象等源用 message 字段承载不可用原因，统一落到 summary 便于 gap 展示。
        "summary": result.get("summary") or result.get("message"),
        "metadata": metadata,
        "record_count": record_count,
        "returned_records": min(len(data), max_records) if isinstance(data, list) else record_count,
        "data": compact_data,
    }


def _profile(event: dict[str, Any]) -> dict[str, Any]:
    trigger = str(event.get("clue_trigger_type") or event.get("event_trigger_type") or "").rsplit(
        ".", 1
    )[-1]
    if trigger not in {"power", "network", "environment", "instrument"}:
        primary = str(event.get("primary_clue_tag") or "")
        if "供电" in primary or "UPS" in primary:
            trigger = "power"
        elif "网络" in primary or "数采" in primary:
            trigger = "network"
        elif "环境" in primary:
            trigger = "environment"
        else:
            trigger = "instrument"
    profiles = {
        "power": {
            "name": "供电/UPS告警证据",
            "fetch": ["monitoring", "station_alarm", "acquisition_alarm", "environment", "comparison", "weather", "door", "compliance"],
        },
        "network": {
            "name": "数采网络告警证据",
            "fetch": ["monitoring", "station_alarm", "acquisition_alarm", "comparison", "weather", "door", "compliance"],
        },
        "environment": {
            "name": "站房环境告警证据",
            "fetch": ["monitoring", "station_alarm", "acquisition_alarm", "environment", "comparison", "weather", "door", "compliance"],
        },
        "instrument": {
            "name": "仪器告警证据",
            "fetch": ["monitoring", "station_alarm", "acquisition_alarm", "instrument_status", "environment", "comparison", "weather", "door", "qc_history", "compliance"],
        },
    }
    selected = profiles[trigger]
    return {"trigger": trigger, **selected}


class JiangsuSmartEventEvidenceFetcher:
    """Fetch one event's evidence with the same bounded style as SOP review."""

    def __init__(
        self,
        *,
        station_data_tool: JiangsuStationDataTool | None = None,
        station_alarm_tool: JiangsuStationAlarmLogsTool | None = None,
        environment_tool: JiangsuStationEnvironmentHistoryTool | None = None,
        work_order_tool: JiangsuFaultWorkOrdersTool | None = None,
        qc_history_tool: JiangsuQcTaskHistoryTool | None = None,
        legacy_adapter: JiangsuLegacyEvidenceAdapter | None = None,
        weather_fetcher: Callable[..., Awaitable[dict[str, Any]]] = fetch_city_weather,
    ) -> None:
        self.station_data_tool = station_data_tool or JiangsuStationDataTool()
        self.station_alarm_tool = station_alarm_tool or JiangsuStationAlarmLogsTool()
        self.environment_tool = environment_tool or JiangsuStationEnvironmentHistoryTool()
        self.work_order_tool = work_order_tool or JiangsuFaultWorkOrdersTool()
        self.qc_history_tool = qc_history_tool or JiangsuQcTaskHistoryTool()
        self.legacy_adapter = legacy_adapter or JiangsuLegacyEvidenceAdapter()
        self.weather_fetcher = weather_fetcher

    @staticmethod
    def _windows(event: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        start = _parse_time(event.get("event_start_time"))
        end = _parse_time(event.get("event_end_time")) or start
        if start is None:
            raise ValueError("事件缺少 event_start_time，无法计算证据窗口")
        end = end or start
        if end < start:
            end = start
        hour_start = start.replace(minute=0, second=0, microsecond=0)
        hour_end = end.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=59, seconds=59)
        day_start = datetime.combine(start.date(), time.min, tzinfo=start.tzinfo)
        day_end = datetime.combine(end.date(), time.max.replace(microsecond=0), tzinfo=end.tzinfo)
        # 凌晨事件的“当日”接口可能只返回已过去的少量小时，向前扩展至少 6 小时。
        # 仅在自然日窗口不足 6 小时时跨日回溯，保证 01:00 从前一日 19:00 起抓取。
        if start - day_start < timedelta(hours=6):
            day_start = start - timedelta(hours=6)
        return {
            "event": {"start": _format_time(start), "end": _format_time(end)},
            "hour": {"start": _format_time(hour_start), "end": _format_time(hour_end)},
            "day": {"start": _format_time(day_start), "end": _format_time(day_end)},
        }

    @staticmethod
    async def _safe(label: str, operation: Awaitable[Any]) -> dict[str, Any]:
        try:
            return _compact_result(await operation)
        except Exception as exc:  # noqa: BLE001 - preserve a visible evidence gap
            return {
                "success": False,
                "status": "failed",
                "summary": f"{label}失败：{exc}",
                "data": [],
            }

    async def _monitoring(self, station_code: str, window: dict[str, Any]) -> dict[str, Any]:
        scopes = {
            "station_hour": (window["day"]["start"], window["day"]["end"], "当天"),
        }

        async def fetch(data_kind: str) -> dict[str, Any]:
            start, end, scope_label = scopes[data_kind]
            try:
                records, payload = await self.station_data_tool.fetch_raw_records(
                    data_kind=data_kind,
                    station_codes=[station_code],
                    start_time=start,
                    end_time=end,
                    data_type=0,
                    station_type="全部",
                )
                return {
                    "success": True,
                    "status": "success" if records else "empty",
                    "summary": f"本站{data_kind}原始数据查询完成（{scope_label}）：{len(records)}条。",
                    "metadata": {
                        "time_range": [start, end],
                        "window_scope": scope_label,
                        "data_type": 0,
                        "station_code": station_code,
                        **_compact(payload),
                    },
                    "record_count": len(records),
                    "data": _compact(records),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "success": False,
                    "status": "failed",
                    "summary": f"本站{data_kind}查询失败：{exc}",
                    "data": [],
                }

        hour = await fetch("station_hour")
        return {
            "success": hour.get("success", False),
            "status": hour["status"],
            "summary": f"本站监测数据采集完成：小时数据（当天）{hour.get('record_count', 0)} 条。" if hour.get("success") else hour["summary"],
            "record_count": int(hour.get("record_count") or 0),
            "data": {"station_hour": hour},
        }

    async def _compliance(self, station_code: str, day_window: dict[str, str]) -> dict[str, Any]:
        """Fetch every work-order type; an empty type list removes the platform filter."""
        return await self._safe(
            "合规工单",
            self.work_order_tool.execute(
                station_codes=[station_code],
                order_types=[],
                start_time=day_window["start"],
                end_time=day_window["end"],
                workflow_statuses=["ToAssign", "ToAccept", "Doing", "Finish"],
                order_statuses=["Wait", "Doing", "Finish"],
                fetch_all=True,
                page_size=50,
            ),
        )

    async def _fetch_hour_records(
        self, codes: list[str], window: dict[str, Any]
    ) -> list[dict[str, Any]]:
        records, _ = await self.station_data_tool.fetch_raw_records(
            data_kind="station_hour",
            station_codes=codes,
            start_time=window["day"]["start"],
            end_time=window["day"]["end"],
            data_type=0,
            station_type="省控",
        )
        rows = [item for item in records if isinstance(item, dict)]
        # The hour-data endpoint omits station identity when querying a
        # single station. The requested code is authoritative in that case.
        if len(codes) == 1:
            for row in rows:
                row.setdefault("stationCode", codes[0])
        return rows

    async def _city_rest_summary(
        self,
        event: dict[str, Any],
        station_code: str,
        directory: list[dict[str, Any]],
        window: dict[str, Any],
    ) -> dict[str, Any]:
        """全市其余省控站点的事件窗口均值（仅聚合，不落原始记录）。"""
        city_name = str(event.get("city_name") or "").strip()
        if not city_name:
            return {
                "status": "skipped",
                "reason": "事件缺少城市信息，无法计算全市背景。",
                "means": {},
            }
        codes: list[str] = []
        for row in directory:
            if not isinstance(row, dict):
                continue
            code = str(row.get("stationCode") or "").strip()
            if not code or code == station_code:
                continue
            if str(row.get("cityName") or "").strip() != city_name:
                continue
            if station_type_from_row(row) != "省控":
                continue
            codes.append(code)
        if not codes:
            return {"status": "empty", "reason": "目录中未找到同城其他省控站点。", "means": {}}
        try:
            records = await self._fetch_hour_records(codes, window)
        except Exception as exc:  # noqa: BLE001 - 全市背景失败不阻塞周边对比
            return {
                "status": "failed",
                "reason": f"全市背景查询失败：{exc}",
                "station_count": len(codes),
                "means": {},
            }
        means = _pollutant_means(_in_event_window(records, window["event"]))
        return {
            "status": "success" if means else "empty",
            "station_count": len(codes),
            "means": means,
        }

    @staticmethod
    def _build_regional_deltas(
        window: dict[str, Any],
        target_records: list[dict[str, Any]],
        peer_records: list[dict[str, Any]],
        city_rest: dict[str, Any],
    ) -> dict[str, Any]:
        """V3.0 4.4：本站均值 - 周边站点/全市其余站点均值及差异比例。

        另附 ``event_trend_comparison``（事件窗口内趋势一致性）与
        ``event_hourly_alignment``（事件窗口逐小时对齐序列），用于核验异常
        开始、持续、结束时间上本站与周边站点是否同步。
        """
        event_window = window["event"]
        target_means = _pollutant_means(_in_event_window(target_records, event_window))
        peer_means = _pollutant_means(_in_event_window(peer_records, event_window))
        city_means = (city_rest or {}).get("means") or {}

        def build(
            other_means: dict[str, float],
        ) -> tuple[dict[str, float], dict[str, float | None]]:
            delta: dict[str, float] = {}
            pct: dict[str, float | None] = {}
            for canonical, _ in POLLUTANT_FIELDS:
                mine = target_means.get(canonical)
                other = other_means.get(canonical)
                if mine is None or other is None:
                    continue
                delta[canonical] = round(mine - other, 3)
                pct[canonical] = round((mine - other) / other * 100, 1) if other else None
            return delta, pct

        nearby_delta, nearby_pct = build(peer_means)
        city_delta, city_pct = build(city_means)
        nearby_trend = _build_trend_comparison(target_records, peer_records)
        event_trend = _build_trend_comparison(
            _in_event_window(target_records, event_window),
            _in_event_window(peer_records, event_window),
        )
        event_alignment = _event_hourly_alignment(event_window, target_records, peer_records)
        peer_codes = {
            str(record.get("stationCode") or record.get("code") or "").strip()
            for record in peer_records
        } - {""}
        return {
            "window": dict(event_window),
            "pollutant_order": [name for name, _ in POLLUTANT_FIELDS],
            "target_station": {"means": target_means},
            "nearby_stations": {
                "station_count": len(peer_codes),
                "means": peer_means,
                "status": "success" if peer_means else "empty",
            },
            "city_rest_stations": city_rest,
            "nearby_station_delta": nearby_delta,
            "nearby_station_delta_pct": nearby_pct,
            "same_city_delta": city_delta,
            "same_city_delta_pct": city_pct,
            "trend_comparison": nearby_trend,
            "event_trend_comparison": event_trend,
            "event_hourly_alignment": event_alignment,
            "trend_window": dict(window["day"]),
        }

    async def _comparison(
        self, event: dict[str, Any], station_code: str, window: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            directory = await self.station_data_tool.fetch_station_directory()
            station = {
                "station_code": station_code,
                "station_name": event.get("site_name") or station_code,
                "city_name": event.get("city_name"),
                "district_name": event.get("district_name"),
            }
            selection = select_district_stations(station, directory)
            codes = list(dict.fromkeys(selection.get("station_codes") or []))
            if not codes:
                return {"success": True, "status": "empty", **selection, "data": []}
            peer_codes = [code for code in codes if code != station_code]
            target_task = self._fetch_hour_records([station_code], window)
            if peer_codes:
                peer_tasks = [self._fetch_hour_records([code], window) for code in peer_codes]
                target_records, *peer_batches = await asyncio.gather(target_task, *peer_tasks)
                peer_records = [row for batch in peer_batches for row in batch]
            else:
                target_records, peer_records = await target_task, []
            station_names = {
                str(row.get("stationCode") or "").strip(): str(
                    row.get("positionName") or row.get("stationName") or row.get("station_code") or ""
                ).strip()
                for row in directory
                if isinstance(row, dict) and str(row.get("stationCode") or "").strip()
            }
            station_names.setdefault(station_code, str(event.get("site_name") or station_code))
            for row in [*target_records, *peer_records]:
                code = str(row.get("stationCode") or row.get("code") or "").strip()
                if code:
                    row.setdefault("stationCode", code)
                    row.setdefault("stationName", station_names.get(code) or code)
            city_rest = await self._city_rest_summary(event, station_code, directory, window)
            regional_deltas = self._build_regional_deltas(
                window, target_records, peer_records, city_rest
            )
            records = peer_records + target_records
            payload = {
                "station_codes": codes,
                "peer_station_count": len(peer_codes),
                "city_rest_station_count": (city_rest or {}).get("station_count"),
            }
            return {
                "success": True,
                "status": "success" if records else "empty",
                **selection,
                "regional_deltas": regional_deltas,
                "metadata": {
                    "time_range": [window["day"]["start"], window["day"]["end"]],
                    **_compact(payload),
                },
                "record_count": len(records),
                "data": _compact(records),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "status": "failed",
                "summary": f"区域背景查询失败：{exc}",
                "data": [],
            }

    async def _instrument_status(self, event: dict[str, Any], station_code: str, window: dict[str, Any]) -> dict[str, Any]:
        """先查询仪器告警；回看七天以覆盖跨小时、跨日尚未恢复的告警。"""
        start = datetime.fromisoformat(window["hour"]["start"])
        end = datetime.fromisoformat(window["hour"]["end"])
        lookback = (start - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        alarm_result = await self.legacy_adapter.instrument_alarm_logs(
            station_code=station_code, start_time=lookback, end_time=window["hour"]["end"],
        )
        gate = {"available": alarm_result.get("success") is True,
                "query_start": lookback, "query_end": window["hour"]["end"], "lookback_days": 7,
                "rule": "700 < subCatalog < 800，告警与事件整点窗口重叠"}
        if not gate["available"]:
            return {"success": False, "status": "failed", "record_count": 0, "data": [], "gate": gate,
                    "summary": "仪器告警查询失败，无法判定是否需要抓取状态数据。", "metadata": alarm_result.get("metadata", {})}
        targets = _target_pollutants(event)
        matched = []
        alarm_pollutants = set()
        def parse_time(value):
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
                return parsed
            except ValueError:
                return None
        for row in alarm_result.get("data") or []:
            try:
                code = int(row.get("subCatalog", row.get("SubCatalog", 0)))
            except (ValueError, TypeError):
                continue
            if not 700 < code < 800:
                continue
            began = parse_time(row.get("lauchTime", row.get("LauchTime")))
            resumed = parse_time(row.get("resumeTime", row.get("ResumeTime")))
            if began is None:
                return {"success": False, "status": "failed", "record_count": 0, "data": [], "gate": gate,
                        "summary": "仪器告警发生时间无效，无法判定是否需要抓取状态数据。"}
            if began > end or (resumed and resumed.year > 1900 and resumed < start):
                continue
            alarm_targets = _target_pollutants({"alarm_content": " ".join(str(row.get(k) or "") for k in (
                "source", "Source", "descriptionDE", "DescriptionDE",
            ))})
            if not set(targets).intersection(alarm_targets):
                continue
            alarm_pollutants.update(set(targets).intersection(alarm_targets))
            matched.append(row)
        query_targets = [name for name in targets if name in alarm_pollutants]
        gate["pollutants"] = query_targets
        gate.update(alarm_count=len(matched), alarms=matched)
        if not matched:
            return {"success": True, "status": "skipped", "summary": "事件时段未命中目标污染物的仪器告警，未抓取仪器状态。",
                    "record_count": 0, "data": [], "gate": gate}
        result = await self.legacy_adapter.instrument_status(
            station_code=station_code, start_time=window["hour"]["start"], end_time=window["hour"]["end"],
            pollutant_codes=_instrument_pollutant_codes(query_targets),
        )
        result["gate"] = gate
        return result

    async def _environment(
        self,
        event: dict[str, Any],
        station_code: str,
        window: dict[str, Any],
        gate: Awaitable[dict[str, Any]],
    ) -> dict[str, Any]:
        """动环历史按门控抓取：站房设备告警日志出现动环类告警才查询。"""
        try:
            alarm_result = await gate
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "status": "failed",
                "summary": f"动环告警判定失败：{exc}",
                "record_count": 0,
                "data": [],
            }
        if not isinstance(alarm_result, dict) or alarm_result.get("success") is not True:
            reason = alarm_result.get("summary") if isinstance(alarm_result, dict) else None
            return {
                "success": False,
                "status": "failed",
                "summary": "站房设备告警日志不可用，无法判定是否存在动环类告警，动环历史未抓取。",
                "record_count": 0,
                "data": [],
                "gate": {"available": False, "reason": reason},
            }
        env_alarms = _power_environment_alarms(alarm_result)
        if not env_alarms:
            return {
                "success": True,
                "status": "skipped",
                "summary": "当天站房设备告警中无动环（动力环境）类告警，未抓取动环历史。",
                "record_count": 0,
                "data": [],
                "gate": {"environment_alarm_count": 0},
            }
        result = await self._safe(
            "站房动环",
            self.environment_tool.execute(
                station_code=station_code,
                unique_code=event.get("unique_code"),
                start_time=window["hour"]["start"],
                end_time=window["hour"]["end"],
                time_type="h",
            ),
        )
        result["gate"] = {
            "environment_alarm_count": len(env_alarms),
            "alarms": _compact(env_alarms[:10]),
        }
        return result

    async def _resolve_city(self, station_code: str) -> str:
        """上游告警行可能不带城市名；从站点目录按站点编码补齐，供气象与区域对比使用。"""
        try:
            directory = await self.station_data_tool.fetch_station_directory()
        except Exception:  # noqa: BLE001 - 城市补齐失败不阻塞其余证据源
            return ""
        for row in directory:
            if isinstance(row, dict) and str(row.get("stationCode") or "").strip() == station_code:
                return str(row.get("cityName") or "").strip()
        return ""

    async def fetch(
        self, event: dict[str, Any], *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        station_code = str(event.get("site_id") or "").strip()
        windows = self._windows(event, config)
        profile = _profile(event)
        target_pollutants = _target_pollutants(event)
        package: dict[str, Any] = {
            "schema_version": EVIDENCE_SCHEMA,
            "package_version": 2,
            "event_id": event.get("event_id"),
            "event_context": {
                "site_id": event.get("site_id"),
                "site_name": event.get("site_name"),
                "event_type": event.get("event_type"),
                "primary_clue_tag": event.get("primary_clue_tag"),
                "source_alarm_id": event.get("source_alarm_id"),
            },
            "collected_at": datetime.now().astimezone().isoformat(),
            "profile": profile,
            "time_windows": windows,
            "collection_policy": {
                "monitoring_data_type": 0,
                "monitoring_station_type": "全部",
                "hour_window_scope": "事件起止时间所在整点小时区间",
                "day_window_scope": "事件自然日（当天）",
                "instrument_target_pollutants": target_pollutants,
                "instrument_gated_by": "目标污染物仪器告警（700 < subCatalog < 800）",
                "instrument_alarm_lookback_days": 7,
                "environment_gated_by": "站房设备告警日志中的动环（动力环境）类告警",
                "qc_severe_only": True,
                "compliance_scope": "event_natural_day",
                "max_inline_records": MAX_INLINE_RECORDS,
            },
            "sources": {},
            "gaps": [
                {
                    "source": "video",
                    "status": "unavailable",
                    "reason": "原始视频线索接口尚未接入，暂不抓取。",
                }
            ],
        }
        if not station_code:
            package["status"] = "failed"
            package["gaps"].append(
                {"source": "station", "status": "failed", "reason": "事件缺少站点编码。"}
            )
            return package

        hour_window = windows["hour"]
        day_window = windows["day"]
        # 上游告警常缺城市名，先补齐再抓气象/区域对比。
        if not str(event.get("city_name") or "").strip():
            resolved_city = await self._resolve_city(station_code)
            if resolved_city:
                event = {**event, "city_name": resolved_city}
        sources: dict[str, Awaitable[Any]] = {}
        fetch_set = set(profile["fetch"])
        station_alarm_task: Awaitable[dict[str, Any]] | None = None
        if "station_alarm" in fetch_set or "environment" in fetch_set:
            # 站房设备告警接口原生按查询当日返回（原平台固定 TimePoint=今天00:00~明天00:00）。
            station_alarm_task = asyncio.ensure_future(
                self._safe(
                    "站房告警", self.station_alarm_tool.execute(station_codes=[station_code])
                )
            )
            if "station_alarm" in fetch_set:

                async def station_alarm_source() -> dict[str, Any]:
                    return _filter_station_alarm_noise(await station_alarm_task)

                sources["station_alarm"] = station_alarm_source()
        if "monitoring" in fetch_set:
            sources["monitoring"] = self._monitoring(station_code, windows)
        if "acquisition_alarm" in fetch_set:
            sources["acquisition_alarm"] = self.legacy_adapter.acquisition_alarms(
                station_code=station_code,
                start_time=day_window["start"],
                end_time=day_window["end"],
            )
        if "instrument_status" in fetch_set:
            sources["instrument_status"] = self._instrument_status(event, station_code, windows)
        if "environment" in fetch_set:
            sources["environment"] = self._environment(
                event,
                station_code,
                windows,
                station_alarm_task
                or asyncio.ensure_future(
                    self._safe(
                        "站房告警", self.station_alarm_tool.execute(station_codes=[station_code])
                    )
                ),
            )
        if "compliance" in fetch_set:
            sources["compliance"] = self._compliance(station_code, day_window)
        if "qc_history" in fetch_set:

            async def qc_history() -> dict[str, Any]:
                result = await self._safe(
                    "质控历史",
                    self.qc_history_tool.execute(
                        station_codes=[station_code],
                        start_time=day_window["start"],
                        end_time=day_window["end"],
                    ),
                )
                return _qc_severe_only(result)

            sources["qc_history"] = qc_history()
        if "comparison" in fetch_set:
            sources["comparison"] = self._comparison(event, station_code, windows)
        if "weather" in fetch_set:
            sources["weather"] = self._safe(
                "城市气象",
                self.weather_fetcher(
                    city_name=event.get("city_name"),
                    start_time=day_window["start"],
                    end_time=day_window["end"],
                ),
            )
        if "door" in fetch_set:
            sources["door"] = self.legacy_adapter.door_records(
                station_code=station_code,
                start_time=day_window["start"],
                end_time=day_window["end"],
            )

        results = await asyncio.gather(*sources.values(), return_exceptions=True)
        for name, result in zip(sources, results, strict=True):
            package["sources"][name] = (
                result if isinstance(result, dict) else _compact_result(result)
            )
            if not package["sources"][name].get("success", False):
                package["gaps"].append(
                    {
                        "source": name,
                        "status": package["sources"][name].get("status", "failed"),
                        "reason": package["sources"][name].get("summary") or "未返回有效证据",
                    }
                )
        package["source_alarm"] = _compact(event.get("evidence", {}).get("alarm"))
        merged_alarms = event.get("evidence", {}).get("alarms")
        if isinstance(merged_alarms, list) and merged_alarms:
            package["source_alarms"] = _compact(merged_alarms)
        package["required_sources"] = list(profile["fetch"])
        package["source_status"] = {
            name: value.get("status", "failed") for name, value in package["sources"].items()
        }
        package["missing_sources"] = [
            name for name in profile["fetch"] if name not in package["sources"]
        ]
        package["status"] = "partial" if package["gaps"] else "success"
        package["collection_notes"] = [
            "小时监测数据、门禁记录、城市气象、区域对比、数采报警、合规工单、质控记录均按事件自然日（当天）抓取。",
            "仪器状态、动环历史按事件起止时间所在整点小时区间抓取（合并桶即首末线索所在小时之间）。",
            "仪器状态仅在事件窗口命中目标污染物仪器告警时抓取；告警回看七天并按恢复时间判断重叠，查询失败不视为无告警。",
            "动环历史仅在站房设备告警日志出现动环（动力环境）类告警时抓取。",
            "质控操作记录仅保留严重告警类型（不合格/超差等非合格结果）。",
            "站房设备告警接口原生仅返回查询当日数据。",
            "平台告警源已移除：原 ALMsummary 仓储无平台 API 可查。",
            "合规工单按事件涉及自然日查询，用于判断同站点同日操作是否能够解释异常线索。",
            "区域对比按同区县省控站点取原始记录；全市其余省控站点仅计算事件窗口均值与差值，不落原始记录。",
            "视频线索接口尚未接入，已显式记录为 evidence gap，不推断视频结论。",
        ]
        return package
