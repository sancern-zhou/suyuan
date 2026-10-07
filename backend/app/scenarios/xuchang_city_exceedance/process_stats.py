"""Deterministic city-day statistics behind the Xuchang exceedance report.

All functions are pure and row-based so the daily exceedance evidence can be
frozen once and re-rendered without re-querying databases.  Segments follow
the report template: 夜间 0-8 时 and 午后 12-17 时.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")

NIGHT_HOURS = frozenset(range(0, 9))
AFTERNOON_HOURS = frozenset(range(12, 18))
NIGHT_LABEL = "0-8时"
AFTERNOON_LABEL = "12-17时"
CALM_WIND_MS = 0.5
MIN_CORRELATION_PAIRS = 8
CORRELATION_FIELDS = ("pm25", "pm10", "o3", "no2", "so2", "co")
CORRELATION_LABELS = {
    "pm25": "PM2.5", "pm10": "PM10", "o3": "O3",
    "no2": "NO2", "so2": "SO2", "co": "CO",
}
POLLUTANT_FIELD = {"PM2.5": "pm25", "PM10": "pm10", "O3": "o3"}
COMPASS = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


def _local_hour(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(TZ)
    else:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.replace(minute=0, second=0, microsecond=0)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 3)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 3)


def compass_name(degrees: float) -> str:
    return COMPASS[int(((degrees + 22.5) % 360) // 45)]


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < MIN_CORRELATION_PAIRS:
        return None
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    var_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if var_x <= 0 or var_y <= 0:
        return None
    return round(cov / math.sqrt(var_x * var_y), 3)


def station_series(rows: list[dict[str, Any]], field: str) -> dict[str, list[tuple[datetime, float]]]:
    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        hour = _local_hour(row.get("data_time") or row.get("time"))
        value = _number(row.get(field))
        station_id = str(row.get("station_id") or "").strip()
        if hour is None or value is None or not station_id:
            continue
        grouped[station_id].append((hour, value))
    return {station: sorted(samples) for station, samples in grouped.items()}


def city_hourly_curve(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    by_hour: dict[datetime, list[float]] = defaultdict(list)
    for samples in station_series(rows, field).values():
        for hour, value in samples:
            by_hour[hour].append(value)
    curve = []
    for hour in sorted(by_hour):
        values = by_hour[hour]
        curve.append({
            "time": hour.isoformat(),
            "mean": round(sum(values) / len(values), 2),
            "peak": round(max(values), 2),
            "min": round(min(values), 2),
            "station_count": len(values),
        })
    return curve


def district_hourly_curves(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    by_district_hour: dict[tuple[str, datetime], list[float]] = defaultdict(list)
    for row in rows:
        district = str(row.get("district") or "").strip()
        hour = _local_hour(row.get("data_time") or row.get("time"))
        value = _number(row.get(field))
        if not district or hour is None or value is None:
            continue
        by_district_hour[(district, hour)].append(value)
    curves: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (district, hour), values in by_district_hour.items():
        curves[district].append({
            "time": hour.isoformat(),
            "mean": round(sum(values) / len(values), 2),
            "station_count": len(values),
        })
    return [
        {"district": district, "points": sorted(points, key=lambda item: item["time"])}
        for district, points in sorted(curves.items())
    ]


def _segment_stats(hours: frozenset[int], city: list[tuple[datetime, float]], meteo: list[dict[str, Any]]) -> dict[str, Any]:
    city_values = [value for hour, value in city if hour.hour in hours]
    wind_vectors: list[tuple[float, float, float]] = []
    low_speed_directions: list[float] = []
    humidity_values: list[float] = []
    calm_hours = 0
    meteo_hours = 0
    for row in meteo:
        hour = _local_hour(row.get("time"))
        if hour is None or hour.hour not in hours:
            continue
        meteo_hours += 1
        speed = _number(row.get("wind_speed_10m_ms"))
        direction = _number(row.get("wind_direction_10m"))
        if speed is not None:
            if speed < CALM_WIND_MS:
                calm_hours += 1
            if direction is not None and 0 <= direction <= 360:
                radians = math.radians(direction)
                if speed >= CALM_WIND_MS:
                    wind_vectors.append((math.cos(radians), math.sin(radians), speed))
                else:
                    low_speed_directions.append(direction)
        humidity = _number(row.get("relative_humidity_2m"))
        if humidity is not None:
            humidity_values.append(humidity)
    dominant: dict[str, Any] = {"status": "insufficient_wind"}
    if wind_vectors:
        x = sum(item[0] * item[2] for item in wind_vectors)
        y = sum(item[1] * item[2] for item in wind_vectors)
        speed_sum = sum(item[2] for item in wind_vectors)
        direction_deg = round(math.degrees(math.atan2(y, x)) % 360, 1)
        dominant = {
            "status": "available",
            "direction_from_deg": direction_deg,
            "direction_from_name": compass_name(direction_deg),
            "resultant": round(math.hypot(x, y) / speed_sum, 3),
        }
    elif low_speed_directions:
        # 静风时段无有效风矢量，仅给出低风速来向参考，不作为扩散判断依据。
        mean_direction = round(
            ((sum(math.radians(value) for value in low_speed_directions)
              / len(low_speed_directions)) % (2 * math.pi)) * 180 / math.pi, 1)
        dominant = {
            "status": "low_speed_reference",
            "direction_from_deg": mean_direction,
            "direction_from_name": compass_name(mean_direction),
            "reference_hours": len(low_speed_directions),
        }
    return {
        "city_mean": _mean(city_values),
        "city_hours": len(city_values),
        "wind_speed_mean_ms": _mean([_number(row.get("wind_speed_10m_ms")) for row in meteo
                                     if (hour := _local_hour(row.get("time"))) is not None
                                     and hour.hour in hours and _number(row.get("wind_speed_10m_ms")) is not None]),
        "humidity_mean": _mean(humidity_values),
        "calm_hours": calm_hours,
        "meteo_hours": meteo_hours,
        "dominant_wind": dominant,
    }


def daypart_assessment(city_curve: list[dict[str, Any]], meteo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    city_series = [(_local_hour(item["time"]), item["mean"]) for item in city_curve]
    city_series = [(hour, value) for hour, value in city_series if hour is not None]
    night = _segment_stats(NIGHT_HOURS, city_series, meteo_rows)
    afternoon = _segment_stats(AFTERNOON_HOURS, city_series, meteo_rows)
    ratio = None
    if night["city_mean"] and afternoon["city_mean"]:
        ratio = round(night["city_mean"] / afternoon["city_mean"], 2)
    return {
        "night_label": NIGHT_LABEL,
        "afternoon_label": AFTERNOON_LABEL,
        "night": night,
        "afternoon": afternoon,
        "night_to_afternoon_ratio": ratio,
        "calm_wind_definition": f"风速<{CALM_WIND_MS} m/s",
    }


def pollutant_correlation(rows: list[dict[str, Any]], *, minimum_pairs: int = MIN_CORRELATION_PAIRS) -> dict[str, Any]:
    series_by_station: dict[str, dict[str, dict[datetime, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        hour = _local_hour(row.get("data_time") or row.get("time"))
        station_id = str(row.get("station_id") or "").strip()
        if hour is None or not station_id:
            continue
        for field in CORRELATION_FIELDS:
            value = _number(row.get(field))
            if value is not None:
                series_by_station[station_id][field][hour] = value
    sums: dict[str, list[float]] = defaultdict(list)
    per_station: dict[str, dict[str, float]] = {}
    for station_id, fields in series_by_station.items():
        station_values: dict[str, float] = {}
        for first_index, first in enumerate(CORRELATION_FIELDS):
            for second in CORRELATION_FIELDS[first_index + 1:]:
                pairs = [
                    (fields[first][hour], fields[second][hour])
                    for hour in fields[first].keys() & fields[second].keys()
                ]
                coefficient = pearson(pairs)
                if coefficient is None:
                    continue
                key = f"{first}_{second}"
                station_values[key] = coefficient
                sums[key].append(coefficient)
        if station_values:
            per_station[station_id] = station_values
    medians = {key: _median(values) for key, values in sums.items()}
    return {
        "labels": CORRELATION_LABELS,
        "fields": list(CORRELATION_FIELDS),
        "station_count": len(series_by_station),
        "minimum_pairs": minimum_pairs,
        "medians": medians,
        "per_station": per_station,
    }


def regional_city_comparison(
    regional_rows: list[dict[str, Any]],
    target_curve: list[dict[str, Any]],
    field: str = "pm25",
) -> list[dict[str, Any]]:
    target_series = {(_local_hour(item["time"]), item["mean"]) for item in target_curve}
    target_by_hour = {hour: value for hour, value in target_series if hour is not None}
    by_city: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in regional_rows:
        city = str(row.get("name") or row.get("station_id") or "").strip()
        hour = _local_hour(row.get("data_time") or row.get("time"))
        value = _number(row.get(field))
        if city and hour is not None and value is not None:
            by_city[city].append((hour, value))
    results = []
    for city, samples in sorted(by_city.items()):
        values = [value for _, value in samples]
        peak_hour, peak_value = max(samples, key=lambda item: item[1])
        night = [value for hour, value in samples if hour.hour in NIGHT_HOURS]
        afternoon = [value for hour, value in samples if hour.hour in AFTERNOON_HOURS]
        night_mean = _mean(night)
        afternoon_mean = _mean(afternoon)
        paired = [
            (value, target_by_hour[hour])
            for hour, value in samples if hour in target_by_hour
        ]
        results.append({
            "city": city,
            "daily_mean": _mean(values),
            "peak": round(peak_value, 2),
            "peak_time": peak_hour.isoformat(),
            "night_mean": night_mean,
            "afternoon_mean": afternoon_mean,
            "night_to_afternoon_ratio": (
                round(night_mean / afternoon_mean, 2)
                if night_mean and afternoon_mean else None
            ),
            "correlation_with_target": pearson(paired),
        })
    return results


def township_daily_summary(rows: list[dict[str, Any]], field: str, *, limit: int = 10) -> list[dict[str, Any]]:
    by_station: dict[str, dict[str, Any]] = {}
    for row in rows:
        station_id = str(row.get("station_id") or "").strip()
        value = _number(row.get(field))
        if not station_id or value is None:
            continue
        item = by_station.setdefault(station_id, {
            "station_id": station_id, "station_name": row.get("name") or station_id,
            "district": row.get("district"), "lat": row.get("lat"), "lon": row.get("lon"),
            "values": [],
        })
        item["values"].append(value)
    summary = []
    for item in by_station.values():
        values = item.pop("values")
        if not values:
            continue
        summary.append({**item, "daily_mean": round(sum(values) / len(values), 2),
                        "valid_hours": len(values)})
    return sorted(summary, key=lambda item: item["daily_mean"], reverse=True)[:limit]


def compute_city_day_statistics(
    national_hourly: list[dict[str, Any]],
    township_hourly: list[dict[str, Any]],
    regional_hourly: list[dict[str, Any]],
    meteo_rows: list[dict[str, Any]],
    *,
    pollutant: str = "PM2.5",
) -> dict[str, Any]:
    field = POLLUTANT_FIELD.get(pollutant)
    if field is None:
        return {"status": "unsupported_pollutant", "pollutant": pollutant}
    curve = city_hourly_curve(national_hourly, field)
    township_summary = township_daily_summary(township_hourly, field)
    peak_township = None
    if township_summary:
        top = township_summary[0]
        peak_township = {key: top.get(key) for key in (
            "station_id", "station_name", "district", "lat", "lon", "daily_mean")}
    return {
        "status": "available" if curve else "insufficient_data",
        "pollutant": pollutant,
        "city_hourly": curve,
        "district_hourly": district_hourly_curves(township_hourly, field),
        "daypart": daypart_assessment(curve, meteo_rows),
        "pollutant_correlation": pollutant_correlation(national_hourly),
        "regional": regional_city_comparison(regional_hourly, curve, field),
        "township_daily_top": township_summary,
        "peak_township": peak_township,
        "coverage": {
            "national_stations": len(station_series(national_hourly, field)),
            "township_stations": len(station_series(township_hourly, field)),
            "regional_cities": len({str(row.get("name") or row.get("station_id") or "").strip()
                                    for row in regional_hourly
                                    if _number(row.get(field)) is not None}),
            "meteo_hours": sum(1 for row in meteo_rows if _local_hour(row.get("time")) is not None),
        },
    }
