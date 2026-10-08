"""NMC hourly observed weather fetcher for target cities."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
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
NMC_REQUEST_INTERVAL_SECONDS = 3.0
NMC_RETRY_BACKOFF_SECONDS = 15.0
NMC_MAX_ATTEMPTS = 2


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
            raise RuntimeError(
                f"NMC weather API returned non-success response: {payload.get('msg')}"
            )
        return payload


class NMCObservedWeatherFetcher(DataFetcher):
    """Fetch NMC hourly observed meteorology and store it in observed_weather_data."""

    def __init__(
        self,
        client: NMCObservedWeatherClient | None = None,
        repo: WeatherRepository | None = None,
        stations: dict[str, NMCCityStation] | None = None,
        request_interval_seconds: float = NMC_REQUEST_INTERVAL_SECONDS,
        retry_backoff_seconds: float = NMC_RETRY_BACKOFF_SECONDS,
        max_attempts: int = NMC_MAX_ATTEMPTS,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        super().__init__(
            name="nmc_observed_weather_fetcher",
            description="Conservative NMC hourly observed weather fetcher for target cities",
            schedule="8 * * * *",
            version="1.1.0",
        )
        self.client = client or NMCObservedWeatherClient()
        self.repo = repo or WeatherRepository()
        self.stations = stations or NMC_CITY_STATIONS
        self.request_interval_seconds = max(0.0, request_interval_seconds)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.max_attempts = max(1, max_attempts)
        self.sleeper = sleeper

    @staticmethod
    def _is_platform_limit_error(exc: Exception) -> bool:
        return (
            isinstance(exc, requests.HTTPError)
            and exc.response is not None
            and exc.response.status_code in {403, 429}
        )

    async def _fetch_station_weather(self, station: NMCCityStation) -> dict[str, Any]:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.client.fetch_weather(station.station_id)
            except Exception as exc:
                if self._is_platform_limit_error(exc) or attempt == self.max_attempts:
                    raise

                delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "nmc_observed_city_fetch_retry",
                    station_id=station.station_id,
                    city=station.station_name,
                    attempt=attempt,
                    retry_in_seconds=delay,
                    error=str(exc),
                )
                await self.sleeper(delay)

        raise RuntimeError("NMC observed weather retry loop ended unexpectedly")

    async def fetch_and_store(self) -> dict[str, int]:
        result = {
            "cities": len(self.stations),
            "fetched_rows": 0,
            "saved": 0,
            "skipped": 0,
            "failed_rows": 0,
            "failed_cities": 0,
            "deferred_cities": 0,
            "rate_limited": 0,
        }

        stations = list(self.stations.values())
        for index, station in enumerate(stations):
            if index:
                await self.sleeper(self.request_interval_seconds)

            try:
                payload = await self._fetch_station_weather(station)
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
                if self._is_platform_limit_error(exc):
                    result["rate_limited"] = 1
                    result["deferred_cities"] = len(stations) - index - 1
                    logger.warning(
                        "nmc_observed_fetch_deferred_after_platform_limit",
                        station_id=station.station_id,
                        deferred_cities=result["deferred_cities"],
                    )
                    break
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

        if result["failed_cities"] == len(self.stations) and not result["rate_limited"]:
            raise RuntimeError("All NMC observed weather city fetches failed")

        logger.info("nmc_observed_weather_fetch_complete", **result)
        return result
