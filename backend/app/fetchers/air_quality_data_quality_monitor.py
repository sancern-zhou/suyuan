"""
Scheduled fetcher wrapper for station-level air-quality data quality checks.

This fetcher does not use local statistical report recomputation. It delegates to
the data quality monitor service, which queries recent station hourly data and
persists issue packages only when suspicious data-quality signals are detected.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.air_quality_data_quality_monitor import (
    DataQualityMonitorConfig,
    run_air_quality_data_quality_monitor,
)

logger = structlog.get_logger()


def _csv_env(name: str, default: str) -> List[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class AirQualityDataQualityFetcher(DataFetcher):
    """Hourly scheduled wrapper for deterministic station data quality checks."""

    def __init__(self):
        super().__init__(
            name="air_quality_data_quality_fetcher",
            description="空气质量站点小时数据质量巡检",
            schedule=os.getenv("AIR_QUALITY_DATA_QUALITY_CRON", "15 * * * *"),
            version="1.0.0",
        )

    async def fetch_and_store(self):
        cities = _csv_env("AIR_QUALITY_DATA_QUALITY_CITIES", "广州")
        hours = max(6, _int_env("AIR_QUALITY_DATA_QUALITY_HOURS", 24))
        station_type = os.getenv("AIR_QUALITY_DATA_QUALITY_STATION_TYPE", "国控")
        output_root = self._optional_path(os.getenv("AIR_QUALITY_DATA_QUALITY_OUTPUT_ROOT"))

        logger.info(
            "air_quality_data_quality_fetcher_run",
            cities=cities,
            hours=hours,
            station_type=station_type,
            output_root=str(output_root) if output_root else None,
        )

        config = DataQualityMonitorConfig(
            cities=cities,
            hours=hours,
            station_type=station_type,
            output_root=output_root,
        )
        return await run_air_quality_data_quality_monitor(config=config)

    @staticmethod
    def _optional_path(value: Optional[str]) -> Optional[Path]:
        return Path(value) if value else None


__all__ = ["AirQualityDataQualityFetcher"]
