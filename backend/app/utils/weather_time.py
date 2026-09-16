"""Explicit time and unit contracts for Open-Meteo historical weather."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
OPEN_METEO_SOURCE = "Open-Meteo Best Match"
WEATHER_UNITS = {
    "boundary_layer_height": "m",
    "temperature_2m": "degC",
    "relative_humidity_2m": "%",
    "dew_point_2m": "degC",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "degree",
    "wind_gusts_10m": "m/s",
    "surface_pressure": "hPa",
    "precipitation": "mm",
    "precipitation_probability": "%",
    "cloud_cover": "%",
    "visibility": "m",
    "shortwave_radiation": "W/m2",
}
WEATHER_ALIASES = {
    "temperature": "temperature_2m",
    "humidity": "relative_humidity_2m",
    "dew_point": "dew_point_2m",
    "wind_speed": "wind_speed_10m",
    "wind_direction": "wind_direction_10m",
    "wind_gusts": "wind_gusts_10m",
}
WEATHER_RECORD_CONTRACT = "weather_hourly_v1"
WEATHER_QUERY_GUIDANCE = """
【共同数据契约 weather_hourly_v1】
历史网格和预报的timestamp统一为ISO 8601（例如2026-09-07T08:00:00+08:00）。
气象值统一读取measurements，使用temperature_2m、relative_humidity_2m、wind_speed_10m、boundary_layer_height、shortwave_radiation等字段；来源读取data_source，单位读取units。
兼容旧文件时，用datetime.fromisoformat(ts.replace('Z', '+00:00'))解析后按时间对象合并、排序和截止时间过滤，禁止用原始时间字符串匹配。
data_complete只说明返回明细是否完整，不代表用户时段无缺失；data_complete=false时必须读取file_path中的完整数组，不能依据首尾预览判断中间小时缺失或计算全时段统计。
先检查success、status、error_code和warnings。success=false表示查询失败，不能解释为气象数据缺失；有保存失败警告时使用完整内联数据，不得声称文件已保存。
"""


def normalize_weather_record(record: dict) -> dict:
    """Normalize final wire/file records, retaining legacy aliases for consumers."""
    output = dict(record)
    value = output["timestamp"]
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    output["timestamp"] = weather_output_time(parsed)
    measurements = dict(output.get("measurements") or {})
    for alias, canonical in WEATHER_ALIASES.items():
        if canonical not in measurements and alias in measurements:
            measurements[canonical] = measurements[alias]
    for field in (*WEATHER_UNITS, "weather_code"):
        if field not in measurements:
            measurements[field] = output.get(field)
        output[field] = measurements[field]
    for alias, canonical in WEATHER_ALIASES.items():
        measurements[alias] = measurements[canonical]
    metadata = dict(output.get("metadata") or {})
    source = output.get("data_source") or metadata.get("data_source") or "legacy_unverified"
    units = {**WEATHER_UNITS, **{alias: WEATHER_UNITS[key] for alias, key in WEATHER_ALIASES.items()}}
    output.update(measurements=measurements, data_source=source, timezone="Asia/Shanghai", units=units)
    metadata.update(data_source=source, timezone="Asia/Shanghai", units=units,
                    record_contract=WEATHER_RECORD_CONTRACT)
    output["metadata"] = metadata
    return output


def weather_data_structure(record_count: int, returned_records: int, externalized: bool) -> dict:
    return {
        "record_contract": WEATHER_RECORD_CONTRACT,
        "root_type": "array",
        "record_type": "object",
        "record_count": record_count,
        "returned_records": returned_records,
        "data_complete": not externalized,
        "sample_strategy": "head_tail" if externalized else "complete",
        "record_schema": {
            "timestamp": "ISO 8601 YYYY-MM-DDTHH:mm:ss+08:00",
            "lat": "number|null", "lon": "number|null",
            "station_name": "string|null",
            "data_source": "string", "timezone": "Asia/Shanghai", "units": "object",
            "measurements": {key: "number|null" for key in (*WEATHER_UNITS, *WEATHER_ALIASES, "weather_code")},
            "metadata": "object",
        },
        "file_root_type": "array" if externalized else None,
        "usage_note": "Load file_path before statistics or missing-hour checks when data_complete=false; parse timestamps before merging or filtering.",
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
        "record_contract": WEATHER_RECORD_CONTRACT,
        "timezone": "Asia/Shanghai",
        "units": WEATHER_UNITS.copy(),
        "sources": sources,
        "source": sources[0] if len(sources) == 1 else "mixed_weather_sources",
        "actual_time_range": {"start": times[0], "end": times[-1]} if times else None,
        "source_note": "Use data_source per record; legacy ERA5 labels do not verify the model or timezone.",
    }
