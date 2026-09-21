"""Load Xuchang township-station hourly rows from the air-data platform."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.tools.xuchang.airdata_platform.client import (
    AirDataPlatformClient,
    get_airdata_platform_client,
)
from app.tools.xuchang.station_catalog.catalog import split_township_name

TOWNSHIP_HOURLY_VIEW = "v_t_h_src"
TOWNSHIP_DATA_SOURCE = f"airdata_platform:{TOWNSHIP_HOURLY_VIEW}"
TOWNSHIP_HOURLY_FIELDS = ("code", "name", "timepoint", "pm2_5", "pm10", "so2", "no2", "co", "o3", "aqi")
DISTRICT_NAMES = (
    "魏都区", "建安区", "鄢陵县", "襄城县", "禹州市", "长葛市",
    "示范区", "东城区", "经济技术开发区",
)
MAX_TOWNSHIP_ROWS = 5000
MISSING_SENTINEL_BELOW = 0.0


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= MISSING_SENTINEL_BELOW else None


def _parse_timepoint(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return parsed.replace(second=0, microsecond=0)


def load_township_hourly_rows(
    start: datetime,
    end: datetime,
    client_factory: Callable[[], AirDataPlatformClient] = get_airdata_platform_client,
) -> dict[str, Any]:
    """Fetch township hourly PM2.5-focused rows in [start, end].

    Returns a status envelope; platform failures degrade to
    ``not_available`` so the daily review can proceed with regular stations.
    """
    try:
        client = client_factory()
        result = client.query_all(
            TOWNSHIP_HOURLY_VIEW,
            filters=[
                {"field": "timepoint", "operator": "gte", "value": start.strftime("%Y-%m-%d %H:%M:%S")},
                {"field": "timepoint", "operator": "lte", "value": end.strftime("%Y-%m-%d %H:%M:%S")},
            ],
            selected_fields=list(TOWNSHIP_HOURLY_FIELDS),
            max_rows=MAX_TOWNSHIP_ROWS,
        )
    except Exception as exc:  # platform/network failures must not kill the review
        return {
            "status": "not_available",
            "reason": f"township_hourly_query_failed: {type(exc).__name__}: {exc}",
            "source": TOWNSHIP_DATA_SOURCE,
            "rows": [],
        }
    rows: list[dict[str, Any]] = []
    for raw in result.get("rows") or []:
        data_time = _parse_timepoint(raw.get("timepoint"))
        station_id = str(raw.get("code") or "").strip()
        name = str(raw.get("name") or "").strip()
        if data_time is None or not station_id:
            continue
        district, _town = split_township_name(name, list(DISTRICT_NAMES))
        rows.append({
            "station_id": station_id,
            "name": name,
            "district": district,
            "data_time": data_time,
            "pm25": _number(raw.get("pm2_5")),
            "pm10": _number(raw.get("pm10")),
            "so2": _number(raw.get("so2")),
            "no2": _number(raw.get("no2")),
            "co": _number(raw.get("co")),
            "o3": _number(raw.get("o3")),
            "aqi": _number(raw.get("aqi")),
            "station_type": "township",
            "lat": None,
            "lon": None,
        })
    station_ids = {row["station_id"] for row in rows}
    return {
        "status": "available" if rows else "not_available",
        "reason": None if rows else "township_hourly_rows_empty_for_window",
        "source": TOWNSHIP_DATA_SOURCE,
        "query_window": {"start": start.isoformat(), "end": end.isoformat()},
        "station_count": len(station_ids),
        "rows": rows,
    }
