"""
Scheduled fetcher wrapper for city pollution process event monitoring.

This fetcher does not use local statistical report recomputation. It delegates to
the pollution event monitor service, which queries recent city/station hourly
data and collects evidence packs for detected pollution processes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.pollution_event_monitor import MonitorConfig, run_pollution_event_monitor

logger = structlog.get_logger()


def _csv_env(name: str, default: str) -> List[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class CityPollutionEventFetcher(DataFetcher):
    """Hourly scheduled wrapper for deterministic city pollution event detection."""

    def __init__(self):
        super().__init__(
            name="city_pollution_event_fetcher",
            description="城市污染过程告警与证据包采集",
            schedule=os.getenv("CITY_POLLUTION_EVENT_CRON", "20 * * * *"),
            version="1.0.0",
        )

    async def fetch_and_store(self):
        cities = _csv_env("CITY_POLLUTION_EVENT_CITIES", "广州")
        hours = max(2, _int_env("CITY_POLLUTION_EVENT_HOURS", 24))
        station_types = _csv_env("CITY_POLLUTION_EVENT_STATION_TYPES", "国控,省控")
        output_root = self._optional_path(os.getenv("CITY_POLLUTION_EVENT_OUTPUT_ROOT"))
        force_collect = _bool_env("CITY_POLLUTION_EVENT_FORCE_COLLECT", False)
        include_components = _bool_env("CITY_POLLUTION_EVENT_INCLUDE_COMPONENTS", True)

        logger.info(
            "city_pollution_event_fetcher_run",
            cities=cities,
            hours=hours,
            station_types=station_types,
            output_root=str(output_root) if output_root else None,
            force_collect=force_collect,
            include_components=include_components,
        )

        config = MonitorConfig(
            cities=cities,
            hours=hours,
            station_type=station_types,
            output_root=output_root,
            force_collect=force_collect,
            include_components=include_components,
        )
        return await run_pollution_event_monitor(config=config)

    @staticmethod
    def _optional_path(value: Optional[str]) -> Optional[Path]:
        return Path(value) if value else None


__all__ = ["CityPollutionEventFetcher"]
