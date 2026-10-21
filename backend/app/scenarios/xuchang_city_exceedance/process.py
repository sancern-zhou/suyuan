"""Detect station pollution processes without treating hourly values as daily limits."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
POLLUTANT_FIELDS = {"PM2.5": "pm25", "PM10": "pm10", "O3": "o3", "AQI": "aqi"}
PRIMARY_ALIASES = {
    "PM2.5": "PM2.5", "PM25": "PM2.5", "细颗粒物": "PM2.5",
    "PM10": "PM10", "可吸入颗粒物": "PM10", "O3": "O3", "臭氧": "O3",
}
AQI_TRIGGER = 101.0
PM25_BUSINESS_TRIGGER = 75.0
DEVIATION_RATIO = 1.5
MIN_PEER_STATIONS = 3
MIN_ABSOLUTE_DELTA = {"PM2.5": 10.0, "PM10": 10.0, "O3": 30.0}


def _hour(value: Any) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(TZ)
    else:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.replace(minute=0, second=0, microsecond=0)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _primary(row: dict[str, Any]) -> str | None:
    text = str(row.get("pollutant") or "").strip().upper().replace("_", "").replace(" ", "")
    for alias, canonical in PRIMARY_ALIASES.items():
        if alias.upper() in text:
            return canonical
    return None


def detect_processes(
    national_rows: list[dict[str, Any]],
    township_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return triggered, contiguous episodes; two clean hours end an episode."""
    normalized: dict[tuple[str, str, datetime], dict[str, Any]] = {}
    for kind, rows in (("national", national_rows), ("township", township_rows)):
        for raw in rows:
            station_id, hour = str(raw.get("station_id") or "").strip(), _hour(raw.get("data_time"))
            if not station_id or hour is None:
                continue
            normalized[(kind, station_id, hour)] = {**raw, "station_type": kind, "_hour": hour}
    by_kind_hour: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized.values():
        by_kind_hour[(row["station_type"], row["_hour"])].append(row)

    hits: dict[tuple[str, str, str], list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for row in normalized.values():
        kind, station_id, hour = row["station_type"], str(row["station_id"]), row["_hour"]
        primary = _primary(row)
        aqi = _number(row.get("aqi")) if kind == "national" else None
        if kind == "national" and aqi is not None and aqi >= AQI_TRIGGER:
            detail = {"rule": "published_hourly_aqi", "value": aqi, "published_primary": primary}
            hits[(kind, station_id, "AQI")].append((hour, detail))
            if primary:
                hits[(kind, station_id, primary)].append((hour, detail))
        pm25 = _number(row.get("pm25"))
        if kind == "national" and pm25 is not None and pm25 >= PM25_BUSINESS_TRIGGER:
            hits[(kind, station_id, "PM2.5")].append((hour, {"rule": "pm25_business_high", "value": pm25}))
        for pollutant in ("PM2.5", "PM10", "O3"):
            field = POLLUTANT_FIELDS[pollutant]
            value = _number(row.get(field))
            if value is None:
                continue
            peers = [
                number for other in by_kind_hour[(kind, hour)]
                if str(other["station_id"]) != station_id
                if (number := _number(other.get(field))) is not None
            ]
            if len(peers) < MIN_PEER_STATIONS:
                continue
            peer_mean = sum(peers) / len(peers)
            if peer_mean > 0 and value > DEVIATION_RATIO * peer_mean and value - peer_mean > MIN_ABSOLUTE_DELTA[pollutant]:
                hits[(kind, station_id, pollutant)].append((hour, {
                    "rule": "station_peer_deviation", "value": value,
                    "peer_mean": round(peer_mean, 3), "peer_count": len(peers),
                }))

    processes: list[dict[str, Any]] = []
    for (kind, station_id, pollutant), hit_rows in sorted(hits.items()):
        by_hour: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
        for hour, detail in hit_rows:
            by_hour[hour].append(detail)
        sequences: list[list[datetime]] = []
        for hour in sorted(by_hour):
            if not sequences or hour - sequences[-1][-1] > timedelta(hours=2):
                sequences.append([])
            sequences[-1].append(hour)
        for hours in sequences:
            aqi_hours = {hour for hour in hours if any(item["rule"] == "published_hourly_aqi" for item in by_hour[hour])}
            pm25_hours = {hour for hour in hours if any(item["rule"] == "pm25_business_high" for item in by_hour[hour])}
            two_hour_trigger = any(
                (hour + timedelta(hours=1) in hour_set)
                for hour_set in (aqi_hours, pm25_hours) for hour in hour_set
            )
            has_deviation = any(item["rule"] == "station_peer_deviation" for hour in hours for item in by_hour[hour])
            if not (two_hour_trigger or has_deviation):
                continue
            first = normalized.get((kind, station_id, hours[0]))
            if first is None or _number(first.get("lat")) is None or _number(first.get("lon")) is None:
                continue
            processes.append({
                "station_id": station_id, "station_name": first.get("name") or station_id,
                "station_type": kind, "lat": float(first["lat"]), "lon": float(first["lon"]),
                "target_pollutant": pollutant, "start_time": hours[0].isoformat(),
                "end_time": hours[-1].isoformat(), "trigger_hours": [hour.isoformat() for hour in hours],
                "triggers": [{"time": hour.isoformat(), **detail} for hour in hours for detail in by_hour[hour]],
                "trigger_status": "confirmed", "data_standard": "HJ 633-2026 published hourly AQI; PM2.5 high value is business-only",
            })
    processes = [item for item in processes if not (
        item["target_pollutant"] == "AQI" and any(
            other["station_id"] == item["station_id"]
            and other["station_type"] == item["station_type"]
            and other["target_pollutant"] != "AQI"
            and other["start_time"] <= item["start_time"]
            and other["end_time"] >= item["end_time"]
            and any(trigger["rule"] == "published_hourly_aqi" for trigger in other["triggers"])
            for other in processes
        )
    )]
    return sorted(processes, key=lambda item: (item["start_time"], item["station_id"], item["target_pollutant"]))
