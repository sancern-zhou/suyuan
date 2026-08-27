"""Project-owned API for the Xuchang hourly air-quality workspace."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
import pyodbc

from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client


router = APIRouter(prefix="/api/air-quality-forecast", tags=["xuchang-air-quality"])

_XUCHANG_CITY_CODE = "411000"


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row(row: dict[str, Any], time_field: str) -> dict[str, Any]:
    return {
        "time": _json_value(row.get(time_field)),
        "aqi": row.get("AQI") if "AQI" in row else row.get("aqi"),
        "pm25": row.get("PM2_5") if "PM2_5" in row else row.get("pm25"),
        "pm10": row.get("PM10") if "PM10" in row else row.get("pm10"),
        "o3": row.get("O3") if "O3" in row else row.get("o3"),
        "no2": row.get("NO2") if "NO2" in row else row.get("no2"),
        "so2": row.get("SO2") if "SO2" in row else row.get("so2"),
        "co": row.get("CO") if "CO" in row else row.get("co"),
    }


def _load_daily_forecasts(cursor: pyodbc.Cursor, days: int = 5) -> list[dict[str, Any]]:
    """Load the next N daily AQI forecasts from SQL Server WeatherForecast7Day."""
    today = datetime.now().date()
    cursor.execute(
        """
        SELECT TimePoint, DayTitle, MinAqi, MaxAqi, MaxPollution, UpdateDate
        FROM dbo.WeatherForecast7Day
        WHERE CityCode = ?
          AND UpdateDate = (
              SELECT MAX(UpdateDate)
              FROM dbo.WeatherForecast7Day AS latest
              WHERE latest.CityCode = ?
          )
        ORDER BY TimePoint ASC
        """,
        _XUCHANG_CITY_CODE,
        _XUCHANG_CITY_CODE,
    )
    columns = [column[0] for column in cursor.description]
    batch = [dict(zip(columns, values)) for values in cursor.fetchall()]

    upcoming = [row for row in batch if row["TimePoint"].date() >= today]
    # Upstream batches can lag behind; fall back to the most recent days available.
    selected = upcoming if len(upcoming) >= days else batch[-days:]
    selected = selected[-days:]

    daily = []
    for row in selected:
        min_aqi = row.get("MinAqi")
        max_aqi = row.get("MaxAqi")
        if min_aqi is not None and max_aqi is not None:
            aqi = round((min_aqi + max_aqi) / 2)
        else:
            aqi = min_aqi if min_aqi is not None else max_aqi
        daily.append(
            {
                "date": row["TimePoint"].date().isoformat() if row.get("TimePoint") else None,
                "day_title": row.get("DayTitle"),
                "min_aqi": min_aqi,
                "max_aqi": max_aqi,
                "aqi": aqi,
                "primary_pollutant": row.get("MaxPollution"),
            }
        )
    return daily


@router.get("/xuchang-hourly")
async def get_xuchang_hourly_forecast() -> dict[str, Any]:
    """Return the current forecast run plus recent Xuchang observations."""
    client = get_sql_server_client()
    now = datetime.now()
    window_start = now - timedelta(hours=96)
    try:
        observations = client.query(
            ["许昌"],
            window_start.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            "CityAQIPublishHistory",
        )
        connection = pyodbc.connect(client.connection_string, timeout=30)
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT forecast_time, aqi, pm25, pm10, o3, no2, so2, co
            FROM dbo.OpenMeteoAirQualityForecast72h
            WHERE city_key = ?
              AND forecast_time >= ?
            ORDER BY forecast_time ASC
            """,
            "xuchang",
            window_start.strftime("%Y-%m-%d %H:%M:%S"),
        )
        columns = [column[0] for column in cursor.description]
        forecasts = [dict(zip(columns, values)) for values in cursor.fetchall()]
        daily_forecasts = _load_daily_forecasts(cursor, 5)
        cursor.close()
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="许昌空气质量预报数据暂不可用") from exc

    return {
        "reference_time": now.isoformat(),
        "daily_forecasts": daily_forecasts,
        "observations": [_row(row, "TimePoint") for row in observations],
        "forecasts": [_row(row, "forecast_time") for row in forecasts],
    }
