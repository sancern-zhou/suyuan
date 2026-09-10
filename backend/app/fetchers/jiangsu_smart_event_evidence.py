"""Collect read-only evidence packages for Jiangsu smart events.

The event generator only normalizes alarm clues.  This fetcher turns each
event into a bounded, auditable evidence package for a later Agent judgment.
It deliberately records the unavailable video source instead of fabricating
video evidence.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, time, timedelta
from typing import Any, Awaitable, Callable

from app.fetchers.weather.jiangsu_review_weather import fetch_city_weather
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuFaultWorkOrdersTool,
    JiangsuQcTaskHistoryTool,
    JiangsuStationAlarmLogsTool,
    JiangsuStationEnvironmentHistoryTool,
)
from app.tools.jiangsu.legacy_evidence import JiangsuLegacyEvidenceAdapter
from app.tools.jiangsu.review_station_selection import select_district_stations
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.tools.jiangsu.station_type import station_type_from_row


EVIDENCE_SCHEMA = "jiangsu_smart_event_evidence/v1"
EVENT_WINDOW_EXTENSION_MINUTES = int(os.getenv("JIANGSU_SMART_EVENT_WINDOW_EXTENSION_MINUTES", "30"))
MAX_INLINE_RECORDS = 500

# 六项污染物规范名 → 上游字段名别名（按出现顺序取第一个存在的字段）。
POLLUTANT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PM10", ("pM10", "PM10", "pm10")),
    ("PM2.5", ("pM2_5", "PM2_5", "pm2_5", "PM25", "pm25")),
    ("SO2", ("sO2", "SO2", "so2")),
    ("NO2", ("nO2", "NO2", "no2")),
    ("CO", ("co", "CO", "Co")),
    ("O3", ("o3", "O3")),
)


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


def _compact(value: Any, *, depth: int = 0, max_items: int = MAX_INLINE_RECORDS) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 2000 else value[:2000] + "…[truncated]"
    if depth >= 5:
        return "[nested data omitted]" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        return {str(key): _compact(item, depth=depth + 1, max_items=max_items) for key, item in value.items()}
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
    return {
        "success": bool(result.get("success") is True),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "metadata": metadata,
        "record_count": record_count,
        "returned_records": min(len(data), max_records) if isinstance(data, list) else record_count,
        "data": compact_data,
    }


def _profile(event: dict[str, Any]) -> dict[str, Any]:
    trigger = str(event.get("clue_trigger_type") or event.get("event_trigger_type") or "").rsplit(".", 1)[-1]
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
            "fetch": ["monitoring", "station_alarm", "platform_alarm", "acquisition_alarm", "environment", "door", "compliance"],
        },
        "network": {
            "name": "数采网络告警证据",
            "fetch": ["monitoring", "station_alarm", "platform_alarm", "acquisition_alarm", "door", "compliance"],
        },
        "environment": {
            "name": "站房环境告警证据",
            "fetch": ["monitoring", "station_alarm", "platform_alarm", "acquisition_alarm", "environment", "comparison", "weather", "door", "compliance"],
        },
        "instrument": {
            "name": "仪器告警证据",
            "fetch": ["monitoring", "station_alarm", "platform_alarm", "acquisition_alarm", "instrument_status", "environment", "door", "qc_history", "compliance"],
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
        before_minutes = int((config or {}).get("event_before_extend_minutes") or EVENT_WINDOW_EXTENSION_MINUTES)
        after_minutes = int((config or {}).get("event_after_extend_minutes") or EVENT_WINDOW_EXTENSION_MINUTES)
        query_start = start - timedelta(minutes=before_minutes)
        query_end = end + timedelta(minutes=after_minutes)
        compliance_start = datetime.combine(start.date(), time.min, tzinfo=start.tzinfo)
        compliance_end = datetime.combine(end.date(), time.max.replace(microsecond=0), tzinfo=end.tzinfo)
        return {
            "event": {"start": _format_time(start), "end": _format_time(end)},
            "query": {"start": _format_time(query_start), "end": _format_time(query_end)},
            "compliance": {"start": _format_time(compliance_start), "end": _format_time(compliance_end)},
            "extension_minutes": before_minutes,
        }

    @staticmethod
    async def _safe(label: str, operation: Awaitable[Any]) -> dict[str, Any]:
        try:
            return _compact_result(await operation)
        except Exception as exc:  # noqa: BLE001 - preserve a visible evidence gap
            return {"success": False, "status": "failed", "summary": f"{label}失败：{exc}", "data": []}

    async def _monitoring(self, station_code: str, window: dict[str, Any]) -> dict[str, Any]:
        start, end = window["query"]["start"], window["query"]["end"]

        async def fetch(data_kind: str) -> dict[str, Any]:
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
                    "summary": f"本站{data_kind}原始数据查询完成：{len(records)}条。",
                    "metadata": {"time_range": [start, end], "data_type": 0, "station_code": station_code, **_compact(payload)},
                    "record_count": len(records),
                    "data": _compact(records),
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "status": "failed", "summary": f"本站{data_kind}查询失败：{exc}", "data": []}

        hour, five_minute = await asyncio.gather(fetch("station_hour"), fetch("station_5minute"))
        successful = [item for item in (hour, five_minute) if item.get("success") is True]
        return {
            "success": bool(successful),
            "status": "success" if all(item.get("status") == "success" for item in (hour, five_minute)) else ("partial" if successful else "failed"),
            "summary": f"本站监测数据采集完成：小时数据 {hour.get('record_count', 0)} 条，5分钟数据 {five_minute.get('record_count', 0)} 条。",
            "record_count": sum(int(item.get("record_count") or 0) for item in (hour, five_minute)),
            "data": {"station_hour": hour, "station_5minute": five_minute},
        }

    async def _fetch_hour_records(self, codes: list[str], window: dict[str, Any]) -> list[dict[str, Any]]:
        records, _ = await self.station_data_tool.fetch_raw_records(
            data_kind="station_hour",
            station_codes=codes,
            start_time=window["query"]["start"],
            end_time=window["query"]["end"],
            data_type=0,
            station_type="省控",
        )
        return [item for item in records if isinstance(item, dict)]

    async def _city_rest_summary(
        self, event: dict[str, Any], station_code: str,
        directory: list[dict[str, Any]], window: dict[str, Any],
    ) -> dict[str, Any]:
        """全市其余省控站点的事件窗口均值（仅聚合，不落原始记录）。"""
        city_name = str(event.get("city_name") or "").strip()
        if not city_name:
            return {"status": "skipped", "reason": "事件缺少城市信息，无法计算全市背景。", "means": {}}
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
            return {"status": "failed", "reason": f"全市背景查询失败：{exc}", "station_count": len(codes), "means": {}}
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
        """V3.0 4.4：本站均值 - 周边站点/全市其余站点均值及差异比例。"""
        event_window = window["event"]
        target_means = _pollutant_means(_in_event_window(target_records, event_window))
        peer_means = _pollutant_means(_in_event_window(peer_records, event_window))
        city_means = (city_rest or {}).get("means") or {}

        def build(other_means: dict[str, float]) -> tuple[dict[str, float], dict[str, float | None]]:
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
        }

    async def _comparison(self, event: dict[str, Any], station_code: str, window: dict[str, Any]) -> dict[str, Any]:
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
                target_records, peer_records = await asyncio.gather(
                    target_task, self._fetch_hour_records(peer_codes, window)
                )
            else:
                target_records, peer_records = await target_task, []
            city_rest = await self._city_rest_summary(event, station_code, directory, window)
            regional_deltas = self._build_regional_deltas(window, target_records, peer_records, city_rest)
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
                "metadata": {"time_range": [window["query"]["start"], window["query"]["end"]], **_compact(payload)},
                "record_count": len(records),
                "data": _compact(records),
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "failed", "summary": f"区域背景查询失败：{exc}", "data": []}

    async def fetch(self, event: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        station_code = str(event.get("site_id") or "").strip()
        windows = self._windows(event, config)
        profile = _profile(event)
        package: dict[str, Any] = {
            "schema_version": EVIDENCE_SCHEMA,
            "package_version": 1,
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
                "event_extension_minutes": windows.get("extension_minutes", EVENT_WINDOW_EXTENSION_MINUTES),
                "compliance_scope": "event_natural_day",
                "max_inline_records": MAX_INLINE_RECORDS,
            },
            "sources": {},
            "gaps": [
                {"source": "video", "status": "unavailable", "reason": "原始视频线索接口尚未接入，暂不抓取。"}
            ],
        }
        if not station_code:
            package["status"] = "failed"
            package["gaps"].append({"source": "station", "status": "failed", "reason": "事件缺少站点编码。"})
            return package

        query = windows["query"]
        compliance = windows["compliance"]
        sources: dict[str, Awaitable[Any]] = {}
        fetch_set = set(profile["fetch"])
        if "monitoring" in fetch_set:
            sources["monitoring"] = self._monitoring(station_code, windows)
        if "station_alarm" in fetch_set:
            sources["station_alarm"] = self._safe(
                "站房告警", self.station_alarm_tool.execute(station_codes=[station_code])
            )
        if "platform_alarm" in fetch_set:
            sources["platform_alarm"] = self.legacy_adapter.platform_alarms(
                station_code=station_code, start_time=query["start"], end_time=query["end"]
            )
        if "acquisition_alarm" in fetch_set:
            sources["acquisition_alarm"] = self.legacy_adapter.acquisition_alarms(
                station_code=station_code, start_time=query["start"], end_time=query["end"]
            )
        if "instrument_status" in fetch_set:
            sources["instrument_status"] = self.legacy_adapter.instrument_status(
                station_code=station_code, start_time=query["start"], end_time=query["end"]
            )
        if "environment" in fetch_set:
            sources["environment"] = self._safe(
                "站房动环", self.environment_tool.execute(
                    station_code=station_code,
                    unique_code=event.get("unique_code"),
                    start_time=query["start"],
                    end_time=query["end"],
                    time_type="h",
                )
            )
        if "compliance" in fetch_set:
            sources["compliance"] = self._safe(
                "合规工单", self.work_order_tool.execute(
                    station_codes=[station_code],
                    start_time=compliance["start"],
                    end_time=compliance["end"],
                    workflow_statuses=["ToAssign", "ToAccept", "Doing", "Finish"],
                    order_statuses=["Wait", "Doing", "Finish"],
                    fetch_all=True,
                    page_size=50,
                )
            )
        if "qc_history" in fetch_set:
            sources["qc_history"] = self._safe(
                "质控历史", self.qc_history_tool.execute(
                    station_codes=[station_code],
                    start_time=compliance["start"],
                    end_time=compliance["end"],
                )
            )
        if "comparison" in fetch_set:
            sources["comparison"] = self._comparison(event, station_code, windows)
        if "weather" in fetch_set:
            sources["weather"] = self._safe(
                "城市气象", self.weather_fetcher(
                    city_name=event.get("city_name"),
                    start_time=query["start"],
                    end_time=query["end"],
                )
            )
        if "door" in fetch_set:
            sources["door"] = self.legacy_adapter.door_records(
                station_code=station_code, start_time=query["start"], end_time=query["end"]
            )

        results = await asyncio.gather(*sources.values(), return_exceptions=True)
        for name, result in zip(sources, results, strict=True):
            package["sources"][name] = result if isinstance(result, dict) else _compact_result(result)
            if not package["sources"][name].get("success", False):
                package["gaps"].append({
                    "source": name,
                    "status": package["sources"][name].get("status", "failed"),
                    "reason": package["sources"][name].get("summary") or "未返回有效证据",
                })
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
            "事件查询窗口为事件起止时间前后各扩展 30 分钟。",
            "合规工单按事件涉及自然日查询，用于判断同站点同日操作是否能够解释异常线索。",
            "区域对比按同区县省控站点取原始记录；全市其余省控站点仅计算事件窗口均值与差值，不落原始记录。",
            "视频线索接口尚未接入，已显式记录为 evidence gap，不推断视频结论。",
        ]
        return package
