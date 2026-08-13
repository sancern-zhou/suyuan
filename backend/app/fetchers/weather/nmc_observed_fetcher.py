"""NMC hourly observed weather fetcher for target cities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
import structlog

from app.config.weather_targets import (
    ObservedWeatherStationTarget,
    get_observed_station_targets,
)
from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.weather.observed_fetcher import ObservedDataPoint

logger = structlog.get_logger()

NMC_WEATHER_URL = "https://www.nmc.cn/rest/weather"
NMC_SENTINEL = 9999.0


# Compatibility aliases. The shared target catalog is the single definition site.
NMCCityStation = ObservedWeatherStationTarget
NMC_CITY_STATIONS: dict[str, NMCCityStation] = get_observed_station_targets(provider="NMC")


def _normalize_nmc_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number >= NMC_SENTINEL:
        return None
    return number


def _parse_nmc_time(value: Any) -> datetime:
    if not value:
        raise ValueError("NMC passedchart row is missing time")
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M")


def parse_nmc_passedchart_row(station: NMCCityStation, row: dict[str, Any]) -> ObservedDataPoint:
    """Map one NMC passedchart row into the existing observed weather DTO."""
    temperature = _normalize_nmc_number(row.get("temperature"))
    humidity = _normalize_nmc_number(row.get("humidity"))
    pressure = _normalize_nmc_number(row.get("pressure"))
    precipitation = _normalize_nmc_number(row.get("rain1h"))
    wind_direction = _normalize_nmc_number(row.get("windDirection"))
    wind_speed = _normalize_nmc_number(row.get("windSpeed"))

    core_values = (temperature, humidity, wind_direction, wind_speed)
    data_quality = "good" if all(value is not None for value in core_values) else "partial"

    return ObservedDataPoint(
        station_id=station.station_id,
        time=_parse_nmc_time(row.get("time")),
        lat=station.lat,
        lon=station.lon,
        station_name=station.station_name,
        temperature_2m=temperature,
        relative_humidity_2m=humidity,
        wind_speed_10m=wind_speed,
        wind_direction_10m=wind_direction,
        surface_pressure=pressure,
        precipitation=precipitation,
        data_source="NMC",
        data_quality=data_quality,
    )


class NMCObservedWeatherClient:
    def __init__(self, base_url: str = NMC_WEATHER_URL, session: requests.Session | None = None):
        self.base_url = base_url
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            }
        )

    def fetch_weather(self, station_id: str) -> dict[str, Any]:
        response = self.session.get(
            self.base_url,
            params={"stationid": station_id},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"NMC weather API returned non-success response: {payload.get('msg')}")
        return payload


class NMCObservedWeatherFetcher(DataFetcher):
    """Fetch NMC hourly observed meteorology and store it in observed_weather_data."""

    def __init__(
        self,
        client: NMCObservedWeatherClient | None = None,
        repo: WeatherRepository | None = None,
        stations: dict[str, NMCCityStation] | None = None,
    ):
        super().__init__(
            name="nmc_observed_weather_fetcher",
            description="NMC hourly observed weather fetcher for Xuchang and Yuncheng",
            schedule="8 * * * *",
            version="1.0.0",
        )
        self.client = client or NMCObservedWeatherClient()
        self.repo = repo or WeatherRepository()
        self.stations = stations or NMC_CITY_STATIONS

    async def fetch_and_store(self) -> dict[str, int]:
        result = {
            "cities": len(self.stations),
            "fetched_rows": 0,
            "saved": 0,
            "skipped": 0,
            "failed_rows": 0,
            "failed_cities": 0,
        }

        for station in self.stations.values():
            try:
                payload = self.client.fetch_weather(station.station_id)
                rows = payload.get("data", {}).get("passedchart") or []
                result["fetched_rows"] += len(rows)
            except Exception as exc:
                result["failed_cities"] += 1
                logger.warning(
                    "nmc_observed_city_fetch_failed",
                    station_id=station.station_id,
                    city=station.station_name,
                    error=str(exc),
                )
                continue

            for row in rows:
                try:
                    data_point = parse_nmc_passedchart_row(station, row)
                except Exception as exc:
                    result["skipped"] += 1
                    logger.warning(
                        "nmc_observed_row_parse_failed",
                        station_id=station.station_id,
                        city=station.station_name,
                        row=row,
                        error=str(exc),
                    )
                    continue

                try:
                    saved = await self.repo.save_observed_data(data_point)
                except Exception as exc:
                    result["failed_rows"] += 1
                    logger.warning(
                        "nmc_observed_row_save_failed",
                        station_id=station.station_id,
                        city=station.station_name,
                        time=data_point.time.isoformat(),
                        error=str(exc),
                    )
                    continue

                if saved:
                    result["saved"] += 1
                else:
                    result["failed_rows"] += 1

        if result["failed_cities"] == len(self.stations):
            raise RuntimeError("All NMC observed weather city fetches failed")

        logger.info("nmc_observed_weather_fetch_complete", **result)
        return result
