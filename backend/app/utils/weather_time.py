"""Explicit time and unit contracts for Open-Meteo historical weather."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
OPEN_METEO_SOURCE = "Open-Meteo Best Match"
WEATHER_UNITS = {
    "boundary_layer_height": "m",
    "temperature_2m": "degC",
    "relative_humidity_2m": "%",
    "wind_speed_10m": "m/s",
    "wind_gusts_10m": "m/s",
    "shortwave_radiation": "W/m2",
}


def weather_query_time(value: str | datetime) -> datetime:
    """Interpret unqualified user times as Beijing time, independently of TZ."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(timezone.utc)


def open_meteo_time(value: str, response: dict) -> datetime:
    """ISO timestamps use the response offset even when they have no suffix."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if "utc_offset_seconds" in response:
            tz = timezone(timedelta(seconds=int(response["utc_offset_seconds"])))
        elif response.get("timezone") in {"UTC", "GMT"}:
            tz = timezone.utc
        else:
            raise ValueError("Open-Meteo response is missing its timezone offset")
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def weather_output_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Stored weather timestamp must include a timezone")
    return value.astimezone(BEIJING).isoformat(timespec="seconds")


def weather_output_metadata(records: list[dict]) -> dict:
    times = sorted(record["timestamp"] for record in records if record.get("timestamp"))
    sources = sorted({record.get("data_source", "legacy_unverified") for record in records})
    return {
        "timezone": "Asia/Shanghai",
        "units": WEATHER_UNITS.copy(),
        "sources": sources,
        "source": sources[0] if len(sources) == 1 else "mixed_weather_sources",
        "actual_time_range": {"start": times[0], "end": times[-1]} if times else None,
        "source_note": "Use data_source per record; legacy ERA5 labels do not verify the model or timezone.",
    }
