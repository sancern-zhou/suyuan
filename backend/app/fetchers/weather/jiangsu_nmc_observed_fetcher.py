"""Jiangsu-project NMC observed weather ingestion.

The NMC province catalog is the station source of truth.  The Jiangsu platform
region directory supplies the city/district relationship; neither source is
copied into a second static station list.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
import structlog

from app.db.repositories.jiangsu_nmc_weather_repo import JiangsuNMCWeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.jiangsu.query_tools import JiangsuGeographyResolverTool

logger = structlog.get_logger(__name__)

NMC_PROVINCE_URL = "https://www.nmc.cn/rest/province/AJS"
NMC_WEATHER_URL = "https://www.nmc.cn/rest/weather"
NMC_SENTINEL = 9999.0
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
FETCH_SCHEDULE = os.getenv("JIANGSU_NMC_OBSERVED_CRON", "12 * * * *")
MINIMUM_DIRECTORY_STATIONS = int(os.getenv("JIANGSU_NMC_MINIMUM_STATIONS", "60"))
MAX_CONCURRENCY = int(os.getenv("JIANGSU_NMC_MAX_CONCURRENCY", "8"))


def _normalise_area_name(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").rstrip("省市区县")


def _normalise_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number >= NMC_SENTINEL else number


@dataclass(frozen=True)
class NMCJiangsuDirectoryStation:
    station_id: str
    province_name: str
    location_name: str
    forecast_url: str | None


@dataclass(frozen=True)
class JiangsuNMCStationTarget:
    station_id: str
    province_name: str
    city_code: str
    city_name: str
    district_code: str | None
    district_name: str | None
    location_level: str
    nmc_location_name: str
    forecast_url: str | None


@dataclass(frozen=True)
class JiangsuNMCObservedRecord:
    time: datetime
    station: JiangsuNMCStationTarget
    temperature_2m: float | None
    relative_humidity_2m: float | None
    wind_speed_10m: float | None
    wind_direction_10m: float | None
    surface_pressure: float | None
    precipitation: float | None
    data_quality: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "station_id": self.station.station_id,
            "province_name": self.station.province_name,
            "city_code": self.station.city_code,
            "city_name": self.station.city_name,
            "district_code": self.station.district_code,
            "district_name": self.station.district_name,
            "location_level": self.station.location_level,
            "nmc_location_name": self.station.nmc_location_name,
            "forecast_url": self.station.forecast_url,
            "temperature_2m": self.temperature_2m,
            "relative_humidity_2m": self.relative_humidity_2m,
            "wind_speed_10m": self.wind_speed_10m,
            "wind_direction_10m": self.wind_direction_10m,
            "surface_pressure": self.surface_pressure,
            "precipitation": self.precipitation,
            "data_source": "NMC",
            "data_quality": self.data_quality,
        }


def parse_passedchart_row(
    station: JiangsuNMCStationTarget,
    row: dict[str, Any],
) -> JiangsuNMCObservedRecord:
    time_value = row.get("time")
    if not time_value:
        raise ValueError("NMC passedchart row is missing time")
    observed_at = datetime.strptime(str(time_value), "%Y-%m-%d %H:%M").replace(
        tzinfo=CHINA_TIMEZONE
    )
    temperature = _normalise_number(row.get("temperature"))
    humidity = _normalise_number(row.get("humidity"))
    wind_direction = _normalise_number(row.get("windDirection"))
    wind_speed = _normalise_number(row.get("windSpeed"))
    quality = (
        "good"
        if all(value is not None for value in (temperature, humidity, wind_direction, wind_speed))
        else "partial"
    )
    return JiangsuNMCObservedRecord(
        time=observed_at,
        station=station,
        temperature_2m=temperature,
        relative_humidity_2m=humidity,
        wind_speed_10m=wind_speed,
        wind_direction_10m=wind_direction,
        surface_pressure=_normalise_number(row.get("pressure")),
        precipitation=_normalise_number(row.get("rain1h")),
        data_quality=quality,
    )


class RegionDirectory(Protocol):
    async def fetch_regions(self) -> list[dict[str, Any]]: ...


class JiangsuPlatformRegionDirectory:
    """Adapter over the Jiangsu platform's live administrative directory."""

    def __init__(self, tool: JiangsuGeographyResolverTool | None = None) -> None:
        self.tool = tool or JiangsuGeographyResolverTool()

    async def fetch_regions(self) -> list[dict[str, Any]]:
        result = await self.tool.execute(area_names=None, target_level=None)
        if not result.get("success"):
            raise RuntimeError(result.get("summary") or "江苏行政区划目录读取失败")
        rows = result.get("data") or []
        if not isinstance(rows, list):
            raise RuntimeError("江苏行政区划目录返回格式异常")
        return [row for row in rows if isinstance(row, dict)]


def resolve_station_targets(
    stations: list[NMCJiangsuDirectoryStation],
    regions: list[dict[str, Any]],
) -> tuple[list[JiangsuNMCStationTarget], list[str]]:
    """Join the two live directories without a separately maintained mapping."""
    cities: dict[str, list[dict[str, Any]]] = {}
    districts: dict[str, list[dict[str, Any]]] = {}
    cities_by_code: dict[str, dict[str, Any]] = {}
    for row in regions:
        code = str(row.get("area_code") or "").strip()
        name = str(row.get("area_name") or "").strip()
        level = row.get("level")
        if not code or not name:
            continue
        if level == 2:
            cities.setdefault(_normalise_area_name(name), []).append(row)
            cities_by_code[code] = row
        elif level == 3:
            districts.setdefault(_normalise_area_name(name), []).append(row)

    resolved: list[JiangsuNMCStationTarget] = []
    unmatched: list[str] = []
    station_name_counts = Counter(
        _normalise_area_name(station.location_name) for station in stations
    )
    station_name_seen: Counter[str] = Counter()
    for station in stations:
        key = _normalise_area_name(station.location_name)
        city_matches = cities.get(key, [])
        district_matches = districts.get(key, [])
        occurrence_index = station_name_seen[key]
        station_name_seen[key] += 1
        # NMC currently exposes separate 淮安市 and 淮安区 observations with
        # the same display name.  When both administrative levels exist and
        # NMC repeats the name, keep the first as the city and subsequent one
        # as the district instead of collapsing two distinct station IDs.
        prefer_district = (
            bool(district_matches)
            and len(city_matches) == 1
            and station_name_counts[key] > 1
            and occurrence_index > 0
        )
        if len(city_matches) == 1 and not prefer_district:
            city = city_matches[0]
            resolved.append(
                JiangsuNMCStationTarget(
                    station_id=station.station_id,
                    province_name=station.province_name,
                    city_code=str(city["area_code"]),
                    city_name=str(city["area_name"]),
                    district_code=None,
                    district_name=None,
                    location_level="city",
                    nmc_location_name=station.location_name,
                    forecast_url=station.forecast_url,
                )
            )
            continue
        district_parent_codes = {str(match.get("parent_code") or "") for match in district_matches}
        # The provincial directory can retain an old county code beside its
        # replacement (for example 海门市/海门区).  They still represent one
        # NMC location when they share the same prefecture parent.  Preserve
        # directory priority and use its first canonical row.
        if district_matches and len(district_parent_codes) == 1:
            district = district_matches[0]
            city = cities_by_code.get(next(iter(district_parent_codes)))
            if city:
                resolved.append(
                    JiangsuNMCStationTarget(
                        station_id=station.station_id,
                        province_name=station.province_name,
                        city_code=str(city["area_code"]),
                        city_name=str(city["area_name"]),
                        district_code=str(district["area_code"]),
                        district_name=str(district["area_name"]),
                        location_level="district",
                        nmc_location_name=station.location_name,
                        forecast_url=station.forecast_url,
                    )
                )
                continue
        unmatched.append(station.location_name)
    return resolved, unmatched


class NMCJiangsuWeatherClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            },
        )

    async def fetch_station_directory(self) -> list[NMCJiangsuDirectoryStation]:
        response = await self.client.get(NMC_PROVINCE_URL)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("NMC 江苏站点目录返回格式异常")
        stations = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            station_id = str(row.get("code") or "").strip()
            location_name = str(row.get("city") or "").strip()
            if not station_id or not location_name:
                continue
            stations.append(
                NMCJiangsuDirectoryStation(
                    station_id=station_id,
                    province_name=str(row.get("province") or "江苏省").strip(),
                    location_name=location_name,
                    forecast_url=str(row.get("url") or "").strip() or None,
                )
            )
        return stations

    async def fetch_weather(self, station_id: str) -> dict[str, Any]:
        response = await self.client.get(NMC_WEATHER_URL, params={"stationid": station_id})
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(
                f"NMC weather API returned non-success response: {payload.get('msg')}"
            )
        return payload


class JiangsuNMCObservedWeatherFetcher(DataFetcher):
    """Discover and ingest all NMC Jiangsu city/county observation stations."""

    def __init__(
        self,
        *,
        client: NMCJiangsuWeatherClient | None = None,
        region_directory: RegionDirectory | None = None,
        repo: JiangsuNMCWeatherRepository | None = None,
        minimum_directory_stations: int = MINIMUM_DIRECTORY_STATIONS,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> None:
        super().__init__(
            name="jiangsu_nmc_observed_weather_fetcher",
            description="NMC observed weather fetcher for Jiangsu cities and counties",
            schedule=FETCH_SCHEDULE,
            version="1.0.0",
        )
        self.client = client or NMCJiangsuWeatherClient()
        self.region_directory = region_directory or JiangsuPlatformRegionDirectory()
        self.repo = repo or JiangsuNMCWeatherRepository()
        self.minimum_directory_stations = minimum_directory_stations
        self.max_concurrency = max(1, max_concurrency)

    async def fetch_and_store(self) -> dict[str, Any]:
        stations, regions = await asyncio.gather(
            self.client.fetch_station_directory(),
            self.region_directory.fetch_regions(),
        )
        if len(stations) < self.minimum_directory_stations:
            raise RuntimeError(
                f"NMC 江苏站点目录仅返回 {len(stations)} 个站，低于安全阈值 "
                f"{self.minimum_directory_stations}"
            )
        targets, unmatched = resolve_station_targets(stations, regions)
        if not targets:
            raise RuntimeError("NMC 江苏站点未能与江苏行政区划目录匹配")

        result: dict[str, Any] = {
            "stations_discovered": len(stations),
            "stations_resolved": len(targets),
            "city_stations": sum(target.location_level == "city" for target in targets),
            "district_stations": sum(target.location_level == "district" for target in targets),
            "unmatched_locations": sorted(set(unmatched)),
            "fetched_rows": 0,
            "saved": 0,
            "skipped_rows": 0,
            "failed_rows": 0,
            "failed_stations": 0,
        }
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def fetch_target(target: JiangsuNMCStationTarget) -> dict[str, int]:
            station_result = {
                "fetched_rows": 0,
                "saved": 0,
                "skipped_rows": 0,
                "failed_rows": 0,
                "failed_stations": 0,
            }
            async with semaphore:
                try:
                    payload = await self.client.fetch_weather(target.station_id)
                    rows = payload.get("data", {}).get("passedchart") or []
                    if not isinstance(rows, list):
                        raise RuntimeError("NMC passedchart 返回格式异常")
                    station_result["fetched_rows"] = len(rows)
                except Exception as exc:
                    station_result["failed_stations"] = 1
                    logger.warning(
                        "jiangsu_nmc_station_fetch_failed",
                        station_id=target.station_id,
                        location=target.nmc_location_name,
                        error=str(exc),
                    )
                    return station_result

                records: list[JiangsuNMCObservedRecord] = []
                for row in rows:
                    try:
                        if not isinstance(row, dict):
                            raise ValueError("passedchart row is not an object")
                        records.append(parse_passedchart_row(target, row))
                    except Exception as exc:
                        station_result["skipped_rows"] += 1
                        logger.warning(
                            "jiangsu_nmc_row_parse_failed",
                            station_id=target.station_id,
                            row=row,
                            error=str(exc),
                        )
                try:
                    station_result["saved"] = await self.repo.save_records(records)
                except Exception as exc:
                    station_result["failed_rows"] = len(records)
                    logger.warning(
                        "jiangsu_nmc_station_save_failed",
                        station_id=target.station_id,
                        records=len(records),
                        error=str(exc),
                    )
                return station_result

        station_results = await asyncio.gather(*(fetch_target(target) for target in targets))
        for station_result in station_results:
            for key, value in station_result.items():
                result[key] += value

        if result["failed_stations"] == len(targets):
            raise RuntimeError("全部 NMC 江苏站点抓取失败")
        parsed_rows = result["fetched_rows"] - result["skipped_rows"]
        if parsed_rows > 0 and result["saved"] == 0 and result["failed_rows"] > 0:
            raise RuntimeError("NMC 江苏观测数据全部写入失败")
        logger.info("jiangsu_nmc_observed_weather_fetch_complete", **result)
        return result
