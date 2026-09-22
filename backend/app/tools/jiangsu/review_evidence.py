"""工单审核证据图表的共享装配：污染物序列提取与同城区间带。

与事件审核抓取器共用同一套站点选择（``select_district_stations``）与口径：
- 数据源：``station_hour``、``data_type=0``（原始实况）、``station_type='省控'``；
- 无效标记 -99/-999 过滤（仅保留 > -90 的值）；
- 同城带取同区按距离最近的 3 个站 + 目标站，逐小时计算 min/median/max。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.tools.jiangsu.review_station_selection import select_district_stations

POLLUTANT_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "PM10": ("PM10", "pM10", "pm10"),
    "PM2.5": ("PM2.5", "PM2_5", "pM2_5", "pm2_5", "PM25"),
    "SO2": ("SO2", "sO2"),
    "NO": ("NO", "no"),
    "NO2": ("NO2", "nO2"),
    "CO": ("CO", "co"),
    "O3": ("O3", "o3"),
}
POLLUTANT_UNITS: dict[str, str] = {"PM10": "μg/m³", "PM2.5": "μg/m³", "SO2": "μg/m³",
                                   "NO": "μg/m³", "NO2": "μg/m³", "CO": "mg/m³", "O3": "μg/m³"}
CALL_TIMEOUT_SECONDS = 75
FETCH_CONCURRENCY = 6
MAX_COMPARISON_STATIONS = 3


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def iter_hour_points(start: datetime, end: datetime) -> list[datetime]:
    if start > end:
        return []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    limit = end.replace(minute=0, second=0, microsecond=0)
    points: list[datetime] = []
    while cursor <= limit:
        points.append(cursor)
        cursor += timedelta(hours=1)
    return points


def numeric(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_value(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        candidate = numeric(row.get(key)) if isinstance(row, dict) else None
        if candidate is not None:
            return candidate
    return None


def _row_time(row: dict[str, Any]) -> str:
    return str(row.get("timePoint") or row.get("time") or row.get("monitorTime") or "").strip()


def _row_station_code(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stationCode") or row.get("station_code") or "").strip()


def pollutant_points(records: list[Any], pollutant: str) -> list[dict[str, Any]]:
    """Flatten raw hourly rows into chart points, dropping invalid markers."""
    keys = POLLUTANT_ROW_KEYS.get(str(pollutant or "").upper(), (pollutant,))
    points: list[dict[str, Any]] = []
    for row in records or []:
        if not isinstance(row, dict):
            continue
        value = _row_value(row, keys)
        time_text = _row_time(row)
        if time_text and value is not None and value > -90:
            points.append({"time": time_text, "value": value})
    points.sort(key=lambda item: item["time"])
    return points


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def same_city_band(records: list[Any], *, target_station_code: str, pollutant: str) -> list[dict[str, Any]]:
    """Per-hour target value plus same-city min/median/max band rows."""
    keys = POLLUTANT_ROW_KEYS.get(str(pollutant or "").upper(), (pollutant,))
    grouped: dict[str, list[tuple[str, float]]] = {}
    for row in records or []:
        if not isinstance(row, dict):
            continue
        value = _row_value(row, keys)
        time_text = _row_time(row)
        if value is None or value <= -90 or not time_text:
            continue
        grouped.setdefault(time_text, []).append((_row_station_code(row), value))

    band: list[dict[str, Any]] = []
    for time_text in sorted(grouped):
        entries = grouped[time_text]
        target = next((value for code, value in entries if code and code == target_station_code), None)
        comparisons = [value for code, value in entries if not code or code != target_station_code]
        if target is None and not comparisons:
            continue
        band.append({
            "time": time_text,
            "target": target,
            "min": min(comparisons) if comparisons else None,
            "median": median(comparisons),
            "max": max(comparisons) if comparisons else None,
        })
    return band


def band_series(band: list[dict[str, Any]], *, unit: str = "", target_name: str = "本站") -> list[dict[str, Any]]:
    """Turn band rows into chart series (target + same-city min/median/max)."""
    if not band:
        return []
    def points(key: str) -> list[dict[str, Any]]:
        return [{"time": row["time"], "value": row[key]} for row in band if row.get(key) is not None]
    series = [{"name": target_name, "unit": unit, "color": "#2f86e0", "points": points("target")}]
    for key, name, color in (("min", "同城最低", "#94a3b8"), ("median", "同城中位", "#61d394"),
                             ("max", "同城最高", "#f6bd4a")):
        values = points(key)
        if values:
            series.append({"name": name, "unit": unit, "color": color, "points": values})
    return [item for item in series if item["points"]]


async def fetch_hour_records(
    station_data_tool: Any,
    station_codes: list[str],
    start_time: str,
    end_time: str,
    *,
    data_type: int = 0,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch hourly raw records per hour with bounded concurrency."""
    parsed_start = parse_datetime(start_time)
    parsed_end = parse_datetime(end_time)
    if parsed_start is None or parsed_end is None:
        raise ValueError("时间范围解析失败")
    hour_points = iter_hour_points(parsed_start, parsed_end) or [parsed_start]
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    failures: list[str] = []

    async def _fetch_one(hour_point: datetime) -> list[dict[str, Any]]:
        query_text = format_time(hour_point)
        try:
            async with semaphore:
                records, _payload = await asyncio.wait_for(
                    station_data_tool.fetch_raw_records(
                        data_kind="station_hour", station_codes=station_codes,
                        start_time=query_text, end_time=query_text,
                        data_type=data_type, station_type="省控",
                    ),
                    timeout=CALL_TIMEOUT_SECONDS,
                )
            return [row for row in (records or []) if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001 - 单小时失败不应中断整段取证
            failures.append(f"{query_text}：{exc}")
            return []

    batches = await asyncio.gather(*(_fetch_one(point) for point in hour_points))
    return [row for batch in batches for row in batch], failures


async def fetch_same_city_band(
    station: dict[str, Any],
    start_time: str,
    end_time: str,
    pollutant: str,
    *,
    station_data_tool: Any = None,
) -> dict[str, Any]:
    """Same-district comparison band for one pollutant (shared selection logic)."""
    from app.tools.jiangsu.station_data import JiangsuStationDataTool

    tool = station_data_tool or JiangsuStationDataTool()
    target_station_code = str(station.get("station_code") or "").strip()
    directory = await asyncio.wait_for(tool.fetch_station_directory(), timeout=CALL_TIMEOUT_SECONDS)
    selection = select_district_stations(station, directory)
    comparison = [item for item in selection.get("comparison_stations") or []
                  if item.get("distance_km") is not None][:MAX_COMPARISON_STATIONS]
    station_codes = [item["station_code"] for item in comparison if item.get("station_code")]
    if not station_codes or not target_station_code:
        return {"status": "empty", "scope": selection.get("comparison_scope") or "same_district",
                "station_codes": [], "band": [], "message": "同区无可比较站点"}

    records, failures = await fetch_hour_records(
        tool, station_codes + [target_station_code], start_time, end_time,
    )
    band = same_city_band(records, target_station_code=target_station_code, pollutant=pollutant)
    return {
        "status": "success" if band else "empty",
        "scope": selection.get("comparison_scope") or "same_district",
        "district_name": selection.get("district_name"),
        "station_codes": station_codes,
        "station_count": len(station_codes),
        "band": band,
        "failures": failures[:5],
        "message": f"同区 {len(station_codes)} 个站参与对比，{len(band)} 小时区间",
    }
