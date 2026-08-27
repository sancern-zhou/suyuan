"""Fetch CNEMC published station hour and day metrics for Xuchang."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string

logger = structlog.get_logger()
CNEMC_LIVE_URL = "https://air.cnemc.cn:18007/CityData/GetAQIDataPublishLive"
XUCHANG_CITY_NAME = "许昌市"
XUCHANG_CITY_AREA_CODE = "411000"
MISSING_VALUE = -99


def _number(value: Any) -> float | int | None:
    if value in (None, "", "NA", "—", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _time(value: Any) -> datetime:
    if not value:
        raise ValueError("CNEMC row is missing TimePoint")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None, minute=0, second=0, microsecond=0)


class XuchangCnemcStationHourFetcher(DataFetcher):
    """Persist official hour observations and source-published rolling day metrics."""

    def __init__(self, session: requests.Session | None = None) -> None:
        super().__init__(
            name="xuchang_cnemc_station_hour_fetcher",
            description="抓取中国环境监测总站许昌市点位小时发布数据",
            schedule="10 * * * *",
            version="1.0.0",
        )
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "suyuan-xuchang-station-fetcher/1.0", "Accept": "application/json"})

    def _fetch(self) -> list[dict[str, Any]]:
        response = self.session.get(CNEMC_LIVE_URL, params={"cityName": XUCHANG_CITY_NAME}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("CNEMC station endpoint returned a non-list payload")
        return payload

    @staticmethod
    def _record(row: dict[str, Any]) -> dict[str, Any] | None:
        station_id = str(row.get("StationCode") or "").strip()
        lat = _number(row.get("Latitude"))
        lon = _number(row.get("Longitude"))
        if not station_id or lat is None or lon is None:
            return None
        return {
            "station_id": station_id,
            "name": str(row.get("PositionName") or station_id).strip(),
            "lon": float(lon),
            "lat": float(lat),
            # dat_station_hour numeric columns are NOT NULL. Retain the
            # source's missing-value semantics without fabricating a zero.
            "aqi": _number(row.get("AQI")) if _number(row.get("AQI")) is not None else MISSING_VALUE,
            "aqi_level": row.get("Quality"),
            "pm10": _number(row.get("PM10")) if _number(row.get("PM10")) is not None else MISSING_VALUE,
            "pm25": _number(row.get("PM2_5")) if _number(row.get("PM2_5")) is not None else MISSING_VALUE,
            "no2": _number(row.get("NO2")) if _number(row.get("NO2")) is not None else MISSING_VALUE,
            "so2": _number(row.get("SO2")) if _number(row.get("SO2")) is not None else MISSING_VALUE,
            "co": _number(row.get("CO")) if _number(row.get("CO")) is not None else float(MISSING_VALUE),
            "o3": _number(row.get("O3")) if _number(row.get("O3")) is not None else MISSING_VALUE,
            "pollutant": row.get("PrimaryPollutant"),
            "data_time": _time(row.get("TimePoint")),
            "city_area_code": XUCHANG_CITY_AREA_CODE,
        }

    @staticmethod
    def _day_record(row: dict[str, Any]) -> dict[str, Any] | None:
        station_id = str(row.get("StationCode") or "").strip()
        lat = _number(row.get("Latitude"))
        lon = _number(row.get("Longitude"))
        if not station_id or lat is None or lon is None:
            return None

        def daily_value(field: str) -> float | int:
            value = _number(row.get(field))
            return value if value is not None else MISSING_VALUE

        data_time = _time(row.get("TimePoint")).replace(hour=0)
        return {
            "station_id": station_id,
            "name": str(row.get("PositionName") or station_id).strip(),
            "lon": float(lon),
            "lat": float(lat),
            "aqi": daily_value("AQI"),
            "aqi_level": row.get("Quality"),
            "pm10": daily_value("PM10_24h"),
            "pm25": daily_value("PM2_5_24h"),
            "no2": daily_value("NO2_24h"),
            "so2": daily_value("SO2_24h"),
            "co": float(daily_value("CO_24h")),
            "o3": daily_value("O3_24h"),
            "o3_8h": daily_value("O3_8h_24h"),
            "pollutant": row.get("PrimaryPollutant"),
            "data_time": data_time,
            "city_area_code": XUCHANG_CITY_AREA_CODE,
        }

    @staticmethod
    def _upsert(cursor: pyodbc.Cursor, record: dict[str, Any]) -> None:
        cursor.execute(
            """
            MERGE dbo.dat_station_hour AS target
            USING (SELECT ? AS station_id, ? AS data_time) AS source
              ON target.station_id = source.station_id AND target.data_time = source.data_time
            WHEN MATCHED THEN UPDATE SET
              name=?, lon=?, lat=?, aqi=?, aqi_level=?, pm10=?, pm25=?, no2=?, so2=?, co=?, o3=?, pollutant=?, city_area_code=?, CreateTime=GETDATE()
            WHEN NOT MATCHED THEN INSERT
              (station_id, name, lon, lat, aqi, aqi_level, pm10, pm25, no2, so2, co, o3, pollutant, data_time, city_area_code, CreateTime)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
            """,
            record["station_id"], record["data_time"],
            record["name"], record["lon"], record["lat"], record["aqi"], record["aqi_level"], record["pm10"], record["pm25"], record["no2"], record["so2"], record["co"], record["o3"], record["pollutant"], record["city_area_code"],
            record["station_id"], record["name"], record["lon"], record["lat"], record["aqi"], record["aqi_level"], record["pm10"], record["pm25"], record["no2"], record["so2"], record["co"], record["o3"], record["pollutant"], record["data_time"], record["city_area_code"],
        )

    @staticmethod
    def _upsert_day(cursor: pyodbc.Cursor, record: dict[str, Any]) -> None:
        cursor.execute(
            """
            MERGE dbo.dat_station_day AS target
            USING (SELECT ? AS station_id, ? AS data_time) AS source
              ON target.station_id = source.station_id AND target.data_time = source.data_time
            WHEN MATCHED THEN UPDATE SET
              name=?, lon=?, lat=?, aqi=?, aqi_level=?, pm10=?, pm25=?, no2=?, so2=?,
              co=?, o3=?, O38h=?, pollutant=?, city_area_code=?, CreateTime=GETDATE()
            WHEN NOT MATCHED THEN INSERT
              (station_id, name, lon, lat, aqi, aqi_level, pm10, pm25, no2, so2,
               co, o3, O38h, pollutant, data_time, city_area_code, CreateTime)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE());
            """,
            record["station_id"], record["data_time"],
            record["name"], record["lon"], record["lat"], record["aqi"],
            record["aqi_level"], record["pm10"], record["pm25"], record["no2"],
            record["so2"], record["co"], record["o3"], record["o3_8h"],
            record["pollutant"], record["city_area_code"],
            record["station_id"], record["name"], record["lon"], record["lat"],
            record["aqi"], record["aqi_level"], record["pm10"], record["pm25"],
            record["no2"], record["so2"], record["co"], record["o3"],
            record["o3_8h"], record["pollutant"], record["data_time"],
            record["city_area_code"],
        )

    async def fetch_and_store(self) -> dict[str, int | str]:
        rows = self._fetch()
        records = [record for row in rows if (record := self._record(row)) is not None]
        day_records = [
            record for row in rows if (record := self._day_record(row)) is not None
        ]
        if not records:
            raise ValueError("CNEMC returned no usable Xuchang station rows")
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            for record in records:
                self._upsert(cursor, record)
            for record in day_records:
                self._upsert_day(cursor, record)
            connection.commit()
        finally:
            connection.close()
        result = {
            "city": XUCHANG_CITY_NAME,
            "fetched": len(rows),
            "saved": len(records),
            "daily_saved": len(day_records),
            "time": records[0]["data_time"].isoformat(),
        }
        logger.info("xuchang_cnemc_station_hour_fetch_completed", **result)
        return result
