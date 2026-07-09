"""
Generate a daily pollution evidence package for Pollution Reasoning Analysis.

The script writes raw query outputs to /tmp/溯源分析/{target_date}/ by default and
updates /tmp/溯源分析/latest.json plus latest.txt. It is intended to be called by
cron/APScheduler before the reasoning skill runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
for path in (str(BACKEND_DIR), str(REPO_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.utils.component_station_directory import PM25_DOMAIN, VOCS_DOMAIN, resolve_component_station_names

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


GUANGDONG_CITIES = [
    "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名",
    "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮",
]

CITY_COORDS = {
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "珠海": (22.2711, 113.5767),
    "汕头": (23.3541, 116.6819),
    "佛山": (23.0219, 113.1214),
    "韶关": (24.8104, 113.5975),
    "湛江": (21.2707, 110.3594),
    "肇庆": (23.0472, 112.4650),
    "江门": (22.5787, 113.0819),
    "茂名": (21.6630, 110.9255),
    "惠州": (23.1115, 114.4152),
    "梅州": (24.2886, 116.1226),
    "汕尾": (22.7862, 115.3753),
    "河源": (23.7437, 114.7007),
    "阳江": (21.8579, 111.9826),
    "清远": (23.6818, 113.0560),
    "东莞": (23.0205, 113.7518),
    "中山": (22.5176, 113.3928),
    "潮州": (23.6567, 116.6226),
    "揭阳": (23.5497, 116.3727),
    "云浮": (22.9151, 112.0445),
}

POLLUTANT_FIELDS = ["PM2_5", "PM2.5", "PM10", "O3_8h", "O3", "NO2", "SO2", "CO"]
PM_POLLUTANTS = {"PM2_5", "PM2.5", "PM10"}
O3_POLLUTANTS = {"O3", "O3_8h"}


class DataRef(str):
    """String data_id that also supports dict-style access used by some tools."""

    def __new__(cls, data_id: str, file_path: Path) -> "DataRef":
        obj = str.__new__(cls, data_id)
        obj.data_id = data_id
        obj.file_path = str(file_path)
        return obj

    def __getitem__(self, key: str) -> str:
        if key == "data_id":
            return self.data_id
        if key == "file_path":
            return self.file_path
        raise KeyError(key)


class SimpleDataHandle:
    def __init__(self, data_id: str, file_path: Path, record_count: int) -> None:
        self.data_id = data_id
        self.file_path = str(file_path)
        self.record_count = record_count


def json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\s]+", "_", value.strip())
    return value.strip("_") or "unknown"


def normalize_city(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    text = text.replace("广东省", "").replace("市", "")
    for city in GUANGDONG_CITIES:
        if city in text:
            return city
    return text or None


def as_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(float(value)) else float(value)
    text = str(value).strip().replace("%", "").replace("—", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def get_nested(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def find_records(payload: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of record lists from heterogeneous tool output."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("data"),
        payload.get("result"),
        get_nested(payload, "data.result"),
        get_nested(payload, "data.results"),
        get_nested(payload, "result.data"),
        get_nested(payload, "result.resultOne"),
        get_nested(payload, "result.resultData"),
    ]
    for candidate in candidates:
        records = find_records(candidate)
        if records:
            return records

    best: list[dict[str, Any]] = []
    for value in payload.values():
        if isinstance(value, (dict, list)):
            records = find_records(value)
            if len(records) > len(best):
                best = records
    return best


def extract_city_stats(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = find_records(result)
    stats: dict[str, dict[str, Any]] = {}

    # Many report tools return a mapping keyed by city under result/data/result.
    for container in (
        result,
        result.get("data") if isinstance(result, dict) else None,
        result.get("result") if isinstance(result, dict) else None,
        get_nested(result, "data.result"),
    ):
        if not isinstance(container, dict):
            continue
        for key, value in container.items():
            city = normalize_city(key)
            if city in GUANGDONG_CITIES and isinstance(value, dict):
                stats[city] = value

    for record in records:
        city = normalize_city(
            record.get("city")
            or record.get("cityName")
            or record.get("CityName")
            or record.get("districtName")
            or record.get("DistrictName")
            or record.get("city_name")
            or record.get("城市")
            or record.get("城市名称")
            or record.get("area_name")
            or record.get("AreaName")
        )
        if city in GUANGDONG_CITIES:
            stats[city] = record
    return stats


def infer_main_pollutant(record: dict[str, Any]) -> str | None:
    change_rates = record.get("change_rates")
    if isinstance(change_rates, dict):
        candidates = {k: as_number(v) for k, v in change_rates.items() if k in POLLUTANT_FIELDS}
        candidates = {k: v for k, v in candidates.items() if v is not None}
        if candidates:
            return max(candidates, key=lambda k: candidates[k] or -1e9)

    primary = (
        record.get("primary_pollutant")
        or record.get("首要污染物")
        or record.get("main_pollutant")
        or record.get("PrimaryPollutant")
    )
    if primary:
        text = str(primary)
        if "PM2" in text or "细颗粒" in text:
            return "PM2_5"
        if "PM10" in text or "颗粒物" in text:
            return "PM10"
        if "臭氧" in text or "O3" in text or "O₃" in text:
            return "O3_8h"
        if "NO2" in text or "NO₂" in text:
            return "NO2"
        if "SO2" in text or "SO₂" in text:
            return "SO2"
        if "CO" in text:
            return "CO"

    values = {field: as_number(record.get(field)) for field in POLLUTANT_FIELDS}
    for field, aliases in {
        "PM2_5": ("PM2_5_Increase", "pm2_5_Increase", "PM2_5Increase"),
        "PM10": ("PM10_Increase", "pm10_Increase", "PM10Increase"),
        "O3_8h": ("O3_8h_Increase", "o3_8h_Increase", "O3_8hIncrease"),
        "NO2": ("NO2_Increase", "no2_Increase", "NO2Increase"),
        "SO2": ("SO2_Increase", "so2_Increase", "SO2Increase"),
        "CO": ("CO_Increase", "co_Increase", "COIncrease"),
    }.items():
        values[field] = values.get(field) or next(
            (as_number(record.get(alias)) for alias in aliases if as_number(record.get(alias)) is not None),
            None,
        )
    values = {k: v for k, v in values.items() if v is not None}
    return max(values, key=lambda k: values[k] or -1e9) if values else None


def rank_top_cities(compare_result: dict[str, Any], city_day_result: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    compare_stats = extract_city_stats(compare_result)
    day_stats = extract_city_stats(city_day_result)

    rows = []
    for city in GUANGDONG_CITIES:
        compare_record = compare_stats.get(city, {})
        day_record = day_stats.get(city, {})
        record = {**day_record, **compare_record}
        change_rates = compare_record.get("change_rates") if isinstance(compare_record, dict) else None
        composite_change = None
        if isinstance(change_rates, dict):
            composite_change = as_number(change_rates.get("composite_index"))
        if composite_change is None:
            composite_change = as_number(
                record.get("CompositeIndex_Increase")
                or record.get("compositeIndex_Increase")
                or record.get("composite_index_Increase")
                or record.get("CompositeIndexIncrease")
            )
        composite_index = as_number(
            record.get("CompositeIndex")
            or record.get("compositeIndex")
            or record.get("composite_index")
        )
        aqi = as_number(record.get("AQI") or record.get("aqi") or record.get("FineRate") or record.get("fineRate"))
        score = (
            composite_change
            if composite_change is not None
            else composite_index
            if composite_index is not None
            else aqi
            if aqi is not None
            else -1e9
        )
        if score == -1e9:
            continue
        rows.append(
            {
                "city": city,
                "rank_score": score,
                "rank_basis": (
                    "change_rates.composite_index"
                    if composite_change is not None
                    else "composite_index"
                    if composite_index is not None
                    else "AQI"
                ),
                "composite_index_yoy_change": composite_change,
                "composite_index": composite_index,
                "AQI": aqi,
                "main_pollutant": infer_main_pollutant(record),
                "raw_record": record,
            }
        )

    rows.sort(key=lambda item: item["rank_score"], reverse=True)
    return rows[:top_n]


def station_name(record: dict[str, Any]) -> str | None:
    for key in ("station_name", "StationName", "站点名称", "station", "name", "Name"):
        if record.get(key):
            return str(record[key])
    return None


def station_city(record: dict[str, Any]) -> str | None:
    return normalize_city(
        record.get("city")
        or record.get("city_name")
        or record.get("城市")
        or record.get("城市名称")
        or record.get("CityName")
    )


def pick_high_value_station(station_day_result: dict[str, Any], city: str, pollutant: str | None) -> dict[str, Any] | None:
    records = [r for r in find_records(station_day_result) if station_city(r) in (None, city) or city in str(r)]
    if not records:
        return None

    field_order = []
    if pollutant:
        field_order.extend([pollutant, pollutant.replace("_", "."), pollutant.replace(".", "_")])
    field_order.extend(["AQI", "aqi", "composite_index", "PM2_5", "PM2.5", "PM10", "O3_8h", "O3"])

    def station_score(record: dict[str, Any]) -> float:
        for field in field_order:
            value = as_number(record.get(field))
            if value is not None:
                return value
        return -1e9

    best = max(records, key=station_score)
    return {
        "city": city,
        "station": station_name(best),
        "main_pollutant": pollutant,
        "rank_score": station_score(best),
        "raw_record": best,
    }


def summarize_wind(records: list[dict[str, Any]]) -> dict[str, Any]:
    speed_values = []
    direction_values = []
    direction_bins: Counter[str] = Counter()

    def direction_bin(deg: float) -> str:
        names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return names[int(((deg + 22.5) % 360) // 45)]

    for record in records:
        measurements = record.get("measurements") if isinstance(record.get("measurements"), dict) else {}
        speed = as_number(
            record.get("wind_speed")
            or record.get("wind_speed_10m")
            or record.get("风速")
            or measurements.get("wind_speed")
            or measurements.get("wind_speed_10m")
        )
        direction = as_number(
            record.get("wind_direction")
            or record.get("wind_direction_10m")
            or record.get("风向")
            or measurements.get("wind_direction")
            or measurements.get("wind_direction_10m")
        )
        if speed is not None:
            speed_values.append(speed)
        if direction is not None:
            direction_values.append(direction)
            direction_bins[direction_bin(direction)] += 1

    return {
        "record_count": len(records),
        "wind_speed_count": len(speed_values),
        "wind_direction_count": len(direction_values),
        "wind_speed_mean": sum(speed_values) / len(speed_values) if speed_values else None,
        "wind_speed_max": max(speed_values) if speed_values else None,
        "dominant_direction": direction_bins.most_common(1)[0][0] if direction_bins else None,
        "direction_bins": dict(direction_bins),
    }


class EvidenceContext:
    """Small context compatible with Context-Aware tools used by this script."""

    def __init__(self, session_id: str, data_dir: Path) -> None:
        self.session_id = session_id
        self.iteration = 0
        self.data_manager = self
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.available_data_ids: list[str] = []
        self._data_files: dict[str, Path] = {}

    def save_data(
        self,
        data: Any,
        schema: str,
        field_stats: Any = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> DataRef:
        data_id = f"{schema}:evidence:{datetime.now().strftime('%H%M%S%f')}"
        path = self.data_dir / f"{safe_name(data_id)}.json"
        write_json(path, {"data_id": data_id, "schema": schema, "metadata": metadata or {}, "data": data})
        self.available_data_ids.append(data_id)
        self._data_files[data_id] = path
        return DataRef(data_id, path)

    def get_raw_data(self, data_id: str) -> Any:
        path = self._data_files.get(data_id)
        if not path:
            raise KeyError(data_id)
        return json.loads(path.read_text(encoding="utf-8")).get("data")

    def get_data(self, data_id: str, expected_schema: str | None = None) -> Any:
        return self.get_raw_data(data_id)

    def get_handle(self, data_id: str) -> Any:
        raw = self.get_raw_data(data_id)
        return SimpleDataHandle(
            data_id=data_id,
            file_path=self._data_files[data_id],
            record_count=len(raw) if isinstance(raw, list) else 1,
        )


class EvidencePackageBuilder:
    def __init__(self, target_date: date, output_root: Path, top_n: int, include_weather_map: bool) -> None:
        self.target_date = target_date
        self.output_root = output_root
        self.package_dir = output_root / target_date.isoformat()
        self.raw_dir = self.package_dir / "raw"
        self.refs_dir = self.package_dir / "data_refs"
        self.context = EvidenceContext(f"pollution_evidence_{target_date.isoformat()}", self.refs_dir)
        self.top_n = top_n
        self.include_weather_map = include_weather_map
        self.manifest: dict[str, Any] = {
            "schema_version": "pollution_evidence_package/v1",
            "target_date": target_date.isoformat(),
            "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "output_dir": str(self.package_dir),
            "raw_dir": str(self.raw_dir),
            "data_refs_dir": str(self.refs_dir),
            "status": "running",
            "tasks": {},
            "warnings": [],
            "data_ids": [],
        }

    async def run_tool(self, name: str, filename: str, call: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        started = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        try:
            result = await call()
            success = bool(result.get("success", result.get("status") == "success")) if isinstance(result, dict) else False
            if isinstance(result, dict) and result.get("status") in {"failed", "empty"}:
                success = False
            payload = {
                "tool": name,
                "success": success,
                "started_at": started,
                "completed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "result": result,
            }
        except Exception as exc:
            payload = {
                "tool": name,
                "success": False,
                "started_at": started,
                "completed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            self.manifest["warnings"].append(f"{name} failed: {exc}")

        path = self.raw_dir / filename
        write_json(path, payload)
        self.manifest["tasks"][name] = {
            "success": payload["success"],
            "file": str(path.relative_to(self.package_dir)),
            "error": payload.get("error") or (payload.get("result") or {}).get("error"),
        }
        result = payload.get("result", {})
        if isinstance(result, dict) and result.get("data_id"):
            self.manifest["data_ids"].append(result["data_id"])
        return result if isinstance(result, dict) else {}

    async def query_station_day_with_fallback(self, tool: Any, city: str) -> dict[str, Any]:
        last_result: dict[str, Any] = {}
        for station_type in ("国控", "省控", "市控", "4.0", "5.0", "6.0", "7.0", "8.0", "9.0", "15.0"):
            result = await tool.execute(
                self.context,
                cities=[city],
                station_type=station_type,
                start_date=self.target_date.isoformat(),
                end_date=self.target_date.isoformat(),
            )
            last_result = result
            if find_records(result):
                result.setdefault("metadata", {})["selected_station_type"] = station_type
                return result
        return last_result

    async def query_station_hour_with_fallback(self, tool: Any, city: str, station: str | None, start_time: str, end_time: str) -> dict[str, Any]:
        if station:
            return await tool.execute(
                self.context,
                stations=[station],
                start_time=start_time,
                end_time=end_time,
                include_weather=True,
            )
        last_result: dict[str, Any] = {}
        for station_type in ("国控", "省控", "市控", "4.0", "5.0", "6.0", "7.0", "8.0", "9.0", "15.0"):
            result = await tool.execute(
                self.context,
                cities=[city],
                station_type=station_type,
                start_time=start_time,
                end_time=end_time,
                include_weather=True,
            )
            last_result = result
            if find_records(result):
                result.setdefault("metadata", {})["selected_station_type"] = station_type
                return result
        return last_result

    async def build(self) -> dict[str, Any]:
        from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool
        from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool
        from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool
        from app.tools.query.get_universal_meteorology.tool import UniversalMeteorologyTool
        from app.tools.query.get_vocs_data import GetVOCsDataTool
        from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool
        from app.tools.query.get_weather_situation_map.tool import GetWeatherSituationMapTool
        from app.tools.query.query_city_standard_report.tool import (
            QueryCityStandardReportTool,
            QueryCityStandardYoyReportTool,
        )
        from app.tools.query.query_gd_suncere.tool_wrapper import (
            QueryGDSuncereStationDayTool,
            QueryGDSuncereStationHourTool,
        )

        self.package_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        start_time = f"{self.target_date.isoformat()} 00:00:00"
        end_time = f"{self.target_date.isoformat()} 23:59:59"
        try:
            comparison_date = self.target_date.replace(year=self.target_date.year - 1)
        except ValueError:
            comparison_date = self.target_date - timedelta(days=365)

        city_report = await self.run_tool(
            "city_standard_report",
            "city_standard_report.json",
            lambda: QueryCityStandardReportTool().execute(
                self.context,
                cities=GUANGDONG_CITIES,
                start_time=self.target_date.isoformat(),
                end_time=self.target_date.isoformat(),
                ns_type=2,
                time_type=8,
                data_source=1,
                sand_type=1,
            ),
        )
        city_compare = await self.run_tool(
            "city_yoy_compare",
            "city_yoy_compare.json",
            lambda: QueryCityStandardYoyReportTool().execute(
                self.context,
                cities=GUANGDONG_CITIES,
                time_point=[self.target_date.isoformat(), self.target_date.isoformat()],
                contrast_time=[comparison_date.isoformat(), comparison_date.isoformat()],
                ns_type=2,
                time_type=8,
                data_source=1,
                sand_type=1,
            ),
        )

        top_cities = rank_top_cities(city_compare, city_report, self.top_n)
        if not top_cities:
            self.manifest["warnings"].append("No top cities could be ranked from city report outputs.")
        write_json(self.package_dir / "top_cities.json", top_cities)

        high_stations: list[dict[str, Any]] = []
        station_hourly_by_city: dict[str, dict[str, Any]] = {}
        station_day_by_city: dict[str, dict[str, Any]] = {}

        station_day_tasks = [
            self.run_tool(
                f"station_day_{city['city']}",
                f"station_day_{safe_name(city['city'])}.json",
                lambda city=city: self.query_station_day_with_fallback(QueryGDSuncereStationDayTool(), city["city"]),
            )
            for city in top_cities
        ]
        station_day_results = await asyncio.gather(*station_day_tasks)
        for city, result in zip(top_cities, station_day_results):
            station_day_by_city[city["city"]] = result
            picked = pick_high_value_station(result, city["city"], city.get("main_pollutant"))
            if not picked:
                picked = {
                    "city": city["city"],
                    "station": None,
                    "main_pollutant": city.get("main_pollutant"),
                    "rank_score": None,
                    "raw_record": None,
                    "warning": "No station-level record found; downstream tasks will use city-level/component mapped station where possible.",
                }
                self.manifest["warnings"].append(f"No high-value station found for {city['city']}.")
            high_stations.append(picked)
        write_json(self.package_dir / "high_value_stations.json", high_stations)

        station_hour_tasks = []
        for item in high_stations:
            city = item["city"]
            station = item.get("station")
            station_hour_tasks.append(
                self.run_tool(
                    f"station_hour_{city}",
                    f"station_hour_{safe_name(city)}.json",
                    lambda city=city, station=station: self.query_station_hour_with_fallback(
                        QueryGDSuncereStationHourTool(),
                        city,
                        station,
                        start_time,
                        end_time,
                    ),
                )
            )
        station_hour_results = await asyncio.gather(*station_hour_tasks)
        for item, result in zip(high_stations, station_hour_results):
            station_hourly_by_city[item["city"]] = result

        weather_tasks = []
        meteo_tasks = []
        meteo_task_cities = []
        for city in top_cities:
            coords = CITY_COORDS.get(city["city"])
            if not coords:
                self.manifest["warnings"].append(f"No coordinates configured for {city['city']}; weather skipped.")
                continue
            lat, lon = coords
            weather_tasks.append(
                self.run_tool(
                    f"weather_forecast_15d_{city['city']}",
                    f"weather_forecast_15d_{safe_name(city['city'])}.json",
                    lambda city=city, lat=lat, lon=lon: GetWeatherForecastTool().execute(
                        self.context,
                        lat=lat,
                        lon=lon,
                        location_name=city["city"],
                        forecast_days=15,
                        past_days=1,
                        hourly=True,
                        daily=True,
                    ),
                )
            )
            meteo_tasks.append(
                self.run_tool(
                    f"universal_meteorology_{city['city']}",
                    f"universal_meteorology_{safe_name(city['city'])}.json",
                    lambda city=city, lat=lat, lon=lon: UniversalMeteorologyTool().execute(
                        self.context,
                        lat=lat,
                        lon=lon,
                        station_name=city["city"],
                        include_wind_profile=True,
                        include_forecast=True,
                        include_historical=True,
                    ),
                )
            )
            meteo_task_cities.append(city["city"])
        meteo_results = await asyncio.gather(*meteo_tasks) if meteo_tasks else []
        meteo_by_city = dict(zip(meteo_task_cities, meteo_results))
        if weather_tasks:
            await asyncio.gather(*weather_tasks)

        if self.include_weather_map:
            await self.run_tool(
                "weather_situation_map",
                "weather_situation_map.json",
                lambda: GetWeatherSituationMapTool().execute(
                    date=self.target_date.strftime("%Y%m%d"),
                    analysis_focus="广东省污染扩散条件和区域输送背景",
                ),
            )

        wind_summaries = {}
        for city, result in station_hourly_by_city.items():
            records = find_records(result)
            if not records:
                records = find_records(meteo_by_city.get(city, {}))
            wind_summaries[city] = summarize_wind(records)
        write_json(self.package_dir / "wind_field_summary.json", wind_summaries)

        component_tasks = []
        for city in top_cities:
            pollutant = city.get("main_pollutant") or ""
            task_prefix = f"component_{city['city']}"
            if pollutant in O3_POLLUTANTS:
                vocs_stations = resolve_component_station_names(city["city"], data_domain=VOCS_DOMAIN)
                if not vocs_stations:
                    self.manifest["warnings"].append(
                        f"{city['city']} has no configured VOCs component stations; skipped."
                    )
                    continue
                component_tasks.append(
                    self.run_tool(
                        f"{task_prefix}_vocs",
                        f"component_vocs_{safe_name(city['city'])}.json",
                        lambda city=city, vocs_stations=vocs_stations: GetVOCsDataTool().execute(
                            self.context,
                            locations=vocs_stations,
                            start_time=start_time,
                            end_time=end_time,
                            table_type=1,
                            data_type=0,
                        ),
                    )
                )
            elif pollutant in PM_POLLUTANTS or not pollutant:
                pm_stations = resolve_component_station_names(city["city"], data_domain=PM25_DOMAIN)
                if not pm_stations:
                    self.manifest["warnings"].append(
                        f"{city['city']} has no configured PM2.5 component stations; skipped."
                    )
                    continue
                component_tasks.extend(
                    [
                        self.run_tool(
                            f"{task_prefix}_pm25_ionic",
                            f"component_pm25_ionic_{safe_name(city['city'])}.json",
                            lambda city=city, pm_stations=pm_stations: GetPM25IonicTool().execute(
                                self.context,
                                locations=pm_stations,
                                start_time=start_time,
                                end_time=end_time,
                                data_type=0,
                                time_type=1,
                            ),
                        ),
                        self.run_tool(
                            f"{task_prefix}_pm25_carbon",
                            f"component_pm25_carbon_{safe_name(city['city'])}.json",
                            lambda city=city, pm_stations=pm_stations: GetPM25CarbonTool().execute(
                                self.context,
                                locations=pm_stations,
                                start_time=start_time,
                                end_time=end_time,
                                data_type=0,
                                time_granularity=1,
                            ),
                        ),
                        self.run_tool(
                            f"{task_prefix}_pm25_crustal",
                            f"component_pm25_crustal_{safe_name(city['city'])}.json",
                            lambda city=city, pm_stations=pm_stations: GetPM25CrustalTool().execute(
                                self.context,
                                locations=pm_stations,
                                start_time=start_time,
                                end_time=end_time,
                                data_type=1,
                                time_granularity=0,
                            ),
                        ),
                    ]
                )
            else:
                self.manifest["warnings"].append(
                    f"{city['city']} main pollutant {pollutant} has no configured component query; skipped."
                )
        if component_tasks:
            await asyncio.gather(*component_tasks)

        self.manifest["status"] = "success" if not self.manifest["warnings"] else "partial_success"
        self.manifest["top_cities_file"] = "top_cities.json"
        self.manifest["high_value_stations_file"] = "high_value_stations.json"
        self.manifest["wind_field_summary_file"] = "wind_field_summary.json"
        self.manifest["data_ids"] = sorted(set(str(x) for x in self.manifest["data_ids"] + self.context.available_data_ids))
        write_json(self.package_dir / "evidence_manifest.json", self.manifest)

        latest = {
            "target_date": self.target_date.isoformat(),
            "package_dir": str(self.package_dir),
            "manifest": str(self.package_dir / "evidence_manifest.json"),
            "status": self.manifest["status"],
            "generated_at": self.manifest["generated_at"],
        }
        write_json(self.output_root / "latest.json", latest)
        (self.output_root / "latest.txt").write_text(str(self.package_dir), encoding="utf-8")
        return self.manifest


def parse_args() -> argparse.Namespace:
    yesterday = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()
    parser = argparse.ArgumentParser(description="Generate pollution evidence package for reasoning analysis.")
    parser.add_argument("--target-date", default=yesterday, help="Date to collect, format YYYY-MM-DD. Default: yesterday in Asia/Shanghai.")
    parser.add_argument("--output-root", default="/tmp/溯源分析", help="Root directory for evidence packages.")
    parser.add_argument("--top-n", type=int, default=3, help="Number of top cities to collect detailed evidence for.")
    parser.add_argument("--skip-weather-map", action="store_true", help="Skip AI weather situation map interpretation.")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    target = datetime.strptime(args.target_date, "%Y-%m-%d").date()
    builder = EvidencePackageBuilder(
        target_date=target,
        output_root=Path(args.output_root),
        top_n=args.top_n,
        include_weather_map=not args.skip_weather_map,
    )
    manifest = await builder.build()
    print(json.dumps({
        "status": manifest["status"],
        "target_date": manifest["target_date"],
        "output_dir": manifest["output_dir"],
        "warnings": manifest["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] in {"success", "partial_success"} else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
