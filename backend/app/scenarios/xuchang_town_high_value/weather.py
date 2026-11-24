"""NMC 许昌站 ZzMTA 实况证据，供既有气象文案函数复用。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.db.repositories.weather_repo import WeatherRepository


async def load_weather_evidence(
    repository: WeatherRepository,
    hour: datetime,
    *,
    lookback_hours: int = 3,
) -> dict[str, Any]:
    try:
        records = await repository.get_observed_data(
            "ZzMTA", hour - timedelta(hours=lookback_hours), hour
        )
        serialized = [
            {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in {
                    "time": getattr(row, "time", None),
                    "station_id": getattr(row, "station_id", None),
                    "data_quality": getattr(row, "data_quality", None),
                    "temperature_2m": getattr(row, "temperature_2m", None),
                    "relative_humidity_2m": getattr(row, "relative_humidity_2m", None),
                    "wind_direction_10m": getattr(row, "wind_direction_10m", None),
                    "wind_speed_10m": getattr(row, "wind_speed_10m", None),
                }.items()
            }
            for row in records
        ]
        return {
            "observed_meteorology": {
                "status": "success" if serialized else "unavailable",
                "source": "NMC",
                "station_hour_records": serialized,
            }
        }
    except Exception:
        return {"observed_meteorology": {"status": "unavailable", "station_hour_records": []}}
