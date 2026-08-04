"""Project-owned API for the Xuchang hourly air-quality workspace."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
import pyodbc

from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client


router = APIRouter(prefix="/api/air-quality-forecast", tags=["xuchang-air-quality"])


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


@router.get("/xuchang-hourly")
def get_xuchang_hourly_forecast() -> dict[str, Any]:
    """Return the current forecast run plus recent Xuchang observations."""
    client = get_sql_server_client()
    now = datetime.now()
    try:
        observations = client.query(
            ["许昌"],
            (now - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S"),
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
            ORDER BY forecast_time ASC
            """,
            "xuchang",
        )
        columns = [column[0] for column in cursor.description]
        forecasts = [dict(zip(columns, values)) for values in cursor.fetchall()]
        cursor.close()
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="许昌空气质量预报数据暂不可用") from exc

    return {
        "reference_time": now.isoformat(),
        "observations": [_row(row, "TimePoint") for row in observations],
        "forecasts": [_row(row, "forecast_time") for row in forecasts],
    }
