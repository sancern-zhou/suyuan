"""Deterministic pollutant-composition features for Xuchang station alerts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from statistics import pstdev
from typing import Any

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _hour_key(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
    return value.replace(minute=0, second=0, microsecond=0)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def calculate_pollutant_source_features(
    rows: Iterable[dict[str, Any]], station_id: str
) -> dict[str, Any]:
    """Classify the latest station composition against its own history."""
    rows = list(rows)
    # Station alerts use 5-minute observations for the supporting pollutants,
    # while PM2.5 is published at hourly resolution. Build an hourly PM2.5
    # lookup so a minute sample can be composed without mixing time bases.
    hourly_pm25: dict[datetime, float] = {}
    for row in rows:
        if row.get("data_source") != "hour":
            continue
        timestamp = _hour_key(row.get("data_time"))
        pm25 = _number(row.get("pm25"))
        if timestamp is not None and pm25 is not None:
            hourly_pm25[timestamp] = pm25

    samples = []
    for row in rows:
        if str(row.get("station_id") or "") != station_id:
            continue
        pm10 = _number(row.get("pm10"))
        pm25 = _number(row.get("pm25"))
        if row.get("data_source") == "minute":
            timestamp = _hour_key(row.get("data_time"))
            # Current-hour PM2.5 is not available yet; use the latest
            # completed hourly value (the preceding整点).
            hourly_value = (
                hourly_pm25.get(timestamp - timedelta(hours=1))
                if timestamp is not None else None
            )
            if hourly_value is not None:
                pm25 = hourly_value
        so2, no2, co = (_number(row.get(field)) for field in ("so2", "no2", "co"))
        if None in (pm10, pm25, so2, no2, co) or pm10 < pm25:
            continue
        pm = pm10 - pm25
        row_sum = so2 + no2 + co + pm25 + pm
        if row_sum <= 0:
            continue
        samples.append({
            "PM": pm / row_sum,
            "SO2": so2 / row_sum,
            "NO2": no2 / row_sum,
            "CO": co / row_sum,
            "PM2.5": pm25 / row_sum,
        })
    if len(samples) < 2:
        return {
            "status": "insufficient_samples",
            "sample_count": len(samples),
            "required_samples": 2,
            "classification": "indeterminate",
            "reason": "at_least_two_complete_composition_samples_required",
        }
    latest = samples[-1]
    means = {key: sum(item[key] for item in samples) / len(samples) for key in latest}
    stddevs = {key: pstdev([item[key] for item in samples]) for key in latest}
    flags = {key: int(latest[key] > means[key] + stddevs[key]) for key in latest}
    flag_tuple = tuple(flags[key] for key in ("SO2", "NO2", "CO", "PM2.5", "PM"))
    classifications = {
        (0, 0, 0, 0, 0): "偏综合型",
        (0, 0, 0, 1, 0): "偏二次型",
        (0, 0, 1, 0, 0): "偏机动车型",
        (1, 0, 0, 0, 0): "偏燃煤型",
        (0, 0, 0, 0, 1): "偏扬尘型",
    }
    return {
        "status": "calculated",
        "sample_count": len(samples),
        "components": {key: round(value, 6) for key, value in latest.items()},
        "historical_means": {key: round(value, 6) for key, value in means.items()},
        "historical_standard_deviations": {key: round(value, 6) for key, value in stddevs.items()},
        "flags": flags,
        "classification": classifications.get(flag_tuple, "其他类型"),
        "flag_rule": "current_proportion > historical_mean + historical_standard_deviation",
        "formula": "ROW_SUM=SO2+NO2+CO+PM2.5+(PM10-PM2.5); PM=PM10-PM2.5",
        "granularity": "minute pollutants (PM10/SO2/NO2/CO) + previous-hour PM2.5 for minute samples",
        "pm25_matching_rule": "minute sample at hour H uses hourly PM2.5 from H-1 because current-hour PM2.5 is unavailable",
    }
