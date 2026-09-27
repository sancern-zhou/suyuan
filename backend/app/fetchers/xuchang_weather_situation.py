"""Publish a prepared weather outlook evidence package on Monday morning."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.weather.city_air_quality_forecast_fetcher import CityAirQualityForecastFetcher
from app.scenarios.xuchang_weather_report.evidence import EVENT_TYPE, write_evidence_package
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()
TZ = ZoneInfo("Asia/Shanghai")


async def build_weather_evidence_event(_task=None) -> TaskEvent:
    """Build a current snapshot for either the scheduled or manual report."""
    now = datetime.now(TZ)
    package = await asyncio.to_thread(write_evidence_package, now.date())
    return TaskEvent(
        event_id=f"xuchang-weather-{now:%Y%m%d}-{now:%H%M%S}-{uuid4().hex[:8]}",
        event_type=EVENT_TYPE,
        occurred_at=now,
        attributes={"city": "许昌市", "start_date": package["start_date"]},
        payload={"city": "许昌市", **package, "evidence_package_path": package["manifest_path"]},
    )


class XuchangAirQualityForecastFetcher(CityAirQualityForecastFetcher):
    """Keep the Xuchang report's AQ forecast fresh without fetching every city."""

    def __init__(self) -> None:
        super().__init__(cities={"411000": "许昌市"}, delay_factory=lambda: 0)
        self.name = "xuchang_air_quality_forecast_fetcher"
        self.schedule = "30 7 * * *"


class XuchangWeatherSituationEvidenceFetcher(DataFetcher):
    def __init__(self) -> None:
        super().__init__(name="xuchang_weather_situation_evidence_fetcher",
                         description="许昌未来天气与污染扩散报告证据快照",
                         schedule="5 8 * * 1", version="1.0.0")

    async def fetch_and_store(self) -> dict:
        event = await build_weather_evidence_event()
        from app.scheduled_tasks import get_scheduled_task_service

        await get_scheduled_task_service().publish_event(event)
        logger.info("xuchang_weather_evidence_published", **event.payload)
        return event.payload
