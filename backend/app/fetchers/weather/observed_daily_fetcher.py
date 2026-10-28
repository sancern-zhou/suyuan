"""Aggregate NMC hourly observations into daily weather statistics.

日界为日历日 00-24 时（北京时间），与空气质量业务日对齐；聚合规则见
ObservedWeatherDaily 模型注释（aggregation_version='v1'）。数据写独立气象库
（WEATHER_DATABASE_URL / weather_engine），与小时表同库。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import text

from app.db.weather_database import weather_engine
from app.fetchers.base.fetcher_interface import DataFetcher

logger = structlog.get_logger()

# 当日有效小时数达到该阈值才产出日值（约 80%，缺测分布非随机，低于阈值硬算会引入偏倚）
MIN_VALID_HOURS = 20
AGGREGATION_VERSION = "v1"
# 每次重算最近 N 个北京日（覆盖 NMC 迟到补传与抓取器停摆后的回补）
DEFAULT_LOOKBACK_DAYS = 3

DDL = """
CREATE TABLE IF NOT EXISTS observed_weather_daily (
    station_id VARCHAR(50) NOT NULL,
    obs_date DATE NOT NULL,
    station_name VARCHAR(100),
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    temperature_2m_avg DOUBLE PRECISION,
    temperature_2m_max DOUBLE PRECISION,
    temperature_2m_min DOUBLE PRECISION,
    relative_humidity_2m_avg DOUBLE PRECISION,
    dew_point_2m_avg DOUBLE PRECISION,
    surface_pressure_avg DOUBLE PRECISION,
    wind_speed_10m_avg DOUBLE PRECISION,
    wind_speed_10m_max DOUBLE PRECISION,
    wind_direction_10m_vector_avg DOUBLE PRECISION,
    precipitation_sum DOUBLE PRECISION,
    cloud_cover_avg DOUBLE PRECISION,
    visibility_avg DOUBLE PRECISION,
    valid_hours INTEGER,
    data_quality VARCHAR(20),
    aggregation_version VARCHAR(10) DEFAULT 'v1',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (station_id, obs_date)
);
CREATE INDEX IF NOT EXISTS idx_observed_daily_date ON observed_weather_daily (obs_date);
"""

UPSERT_SQL = f"""
WITH src AS (
    SELECT
        station_id,
        (time AT TIME ZONE 'Asia/Shanghai')::date AS obs_date,
        max(station_name) AS station_name,
        max(lat) AS lat,
        max(lon) AS lon,
        count(*) AS valid_hours,
        avg(temperature_2m) AS temperature_2m_avg,
        max(temperature_2m) AS temperature_2m_max,
        min(temperature_2m) AS temperature_2m_min,
        avg(relative_humidity_2m) AS relative_humidity_2m_avg,
        avg(dew_point_2m) AS dew_point_2m_avg,
        avg(surface_pressure) AS surface_pressure_avg,
        avg(wind_speed_10m) AS wind_speed_10m_avg,
        max(wind_speed_10m) AS wind_speed_10m_max,
        CASE
            WHEN count(wind_direction_10m) > 0 THEN
                MOD(
                    CAST(degrees(atan2(
                        -avg(sin(radians(wind_direction_10m))),
                        -avg(cos(radians(wind_direction_10m)))
                    )) + 360 AS numeric),
                    360
                )
        END AS wind_direction_10m_vector_avg,
        sum(precipitation) AS precipitation_sum,
        avg(cloud_cover) AS cloud_cover_avg,
        avg(visibility) AS visibility_avg
    FROM observed_weather_data
    WHERE (time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN :start_date AND :end_date
    GROUP BY station_id, (time AT TIME ZONE 'Asia/Shanghai')::date
)
INSERT INTO observed_weather_daily (
    station_id, obs_date, station_name, lat, lon,
    temperature_2m_avg, temperature_2m_max, temperature_2m_min,
    relative_humidity_2m_avg, dew_point_2m_avg, surface_pressure_avg,
    wind_speed_10m_avg, wind_speed_10m_max, wind_direction_10m_vector_avg,
    precipitation_sum, cloud_cover_avg, visibility_avg,
    valid_hours, data_quality, aggregation_version
)
SELECT
    station_id, obs_date, station_name, lat, lon,
    CASE WHEN valid_hours >= :min_hours THEN temperature_2m_avg END,
    CASE WHEN valid_hours >= :min_hours THEN temperature_2m_max END,
    CASE WHEN valid_hours >= :min_hours THEN temperature_2m_min END,
    CASE WHEN valid_hours >= :min_hours THEN relative_humidity_2m_avg END,
    CASE WHEN valid_hours >= :min_hours THEN dew_point_2m_avg END,
    CASE WHEN valid_hours >= :min_hours THEN surface_pressure_avg END,
    CASE WHEN valid_hours >= :min_hours THEN wind_speed_10m_avg END,
    CASE WHEN valid_hours >= :min_hours THEN wind_speed_10m_max END,
    CASE WHEN valid_hours >= :min_hours THEN wind_direction_10m_vector_avg END,
    CASE WHEN valid_hours >= :min_hours THEN precipitation_sum END,
    CASE WHEN valid_hours >= :min_hours THEN cloud_cover_avg END,
    CASE WHEN valid_hours >= :min_hours THEN visibility_avg END,
    valid_hours,
    CASE WHEN valid_hours >= 24 THEN 'good' ELSE 'partial' END,
    :aggregation_version
FROM src
ON CONFLICT (station_id, obs_date) DO UPDATE SET
    station_name = EXCLUDED.station_name,
    lat = EXCLUDED.lat,
    lon = EXCLUDED.lon,
    temperature_2m_avg = EXCLUDED.temperature_2m_avg,
    temperature_2m_max = EXCLUDED.temperature_2m_max,
    temperature_2m_min = EXCLUDED.temperature_2m_min,
    relative_humidity_2m_avg = EXCLUDED.relative_humidity_2m_avg,
    dew_point_2m_avg = EXCLUDED.dew_point_2m_avg,
    surface_pressure_avg = EXCLUDED.surface_pressure_avg,
    wind_speed_10m_avg = EXCLUDED.wind_speed_10m_avg,
    wind_speed_10m_max = EXCLUDED.wind_speed_10m_max,
    wind_direction_10m_vector_avg = EXCLUDED.wind_direction_10m_vector_avg,
    precipitation_sum = EXCLUDED.precipitation_sum,
    cloud_cover_avg = EXCLUDED.cloud_cover_avg,
    visibility_avg = EXCLUDED.visibility_avg,
    valid_hours = EXCLUDED.valid_hours,
    data_quality = EXCLUDED.data_quality,
    aggregation_version = EXCLUDED.aggregation_version,
    updated_at = now()
"""


def beijing_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


async def ensure_daily_table() -> None:
    async with weather_engine.begin() as connection:
        for statement in DDL.split(";"):
            if statement.strip():
                await connection.execute(text(statement))


async def upsert_observed_weather_daily(
    start_date: date,
    end_date: date,
    *,
    min_valid_hours: int = MIN_VALID_HOURS,
) -> dict[str, Any]:
    """重算 [start_date, end_date]（北京日历日）内所有站点的日值并幂等入库。"""
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    async with weather_engine.begin() as connection:
        result = await connection.execute(
            text(UPSERT_SQL),
            {
                "start_date": start_date,
                "end_date": end_date,
                "min_hours": min_valid_hours,
                "aggregation_version": AGGREGATION_VERSION,
            },
        )
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "upserted_station_days": result.rowcount or 0,
        "min_valid_hours": min_valid_hours,
    }


class ObservedWeatherDailyFetcher(DataFetcher):
    """Recompute recent observed_weather_daily station-days from hourly rows."""

    def __init__(
        self,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        min_valid_hours: int = MIN_VALID_HOURS,
    ):
        super().__init__(
            name="observed_weather_daily_fetcher",
            description="Aggregate hourly observed weather into daily statistics (calendar-day Beijing)",
            schedule="40 * * * *",
            version="1.0.0",
        )
        self.lookback_days = max(1, lookback_days)
        self.min_valid_hours = min_valid_hours

    async def fetch_and_store(self) -> dict[str, Any]:
        await ensure_daily_table()
        today = beijing_today()
        start = today - timedelta(days=self.lookback_days - 1)
        result = await upsert_observed_weather_daily(
            start, today, min_valid_hours=self.min_valid_hours
        )
        logger.info("observed_weather_daily_upsert_complete", **result)
        return result
