"""Deterministic hourly GIS frames for the daily review HTML report."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.scenarios.xuchang_daily_review.episodes import normalize_hour
from app.scenarios.xuchang_daily_review.regional_response import POLLUTANT_SERIES_KEY, _haversine_km
from app.scenarios.xuchang_daily_review.report_events import _value, _direction


def build_map_frames(
    analyses: list[dict[str, Any]],
    regular_rows: list[dict[str, Any]],
    township_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep raw hourly map values separate from Agent-readable summaries."""
    rows_by_hour: dict[str, list[dict[str, Any]]] = {}
    for row in [*regular_rows, *township_rows]:
        timestamp = row.get("data_time")
        if isinstance(timestamp, datetime):
            hour = timestamp.replace(minute=0, second=0, microsecond=0).isoformat()[:19]
        elif isinstance(timestamp, str):
            hour = timestamp[:13] + ":00:00"
        else:
            continue
        rows_by_hour.setdefault(hour, []).append(row)

    episodes = []
    for analysis in analyses:
        anchor = analysis.get("alert_anchor") or {}
        pollutant = str(anchor.get("target_pollutant") or "")
        field = POLLUTANT_SERIES_KEY.get(pollutant)
        windows = (analysis.get("window_policy") or {}).get("windows") or {}
        hours = sorted({hour[:19] for group in ("before", "during", "after") for hour in windows.get(group) or []})
        frames = []
        for hour in hours:
            records_by_id = {}
            for row in rows_by_hour.get(hour, []):
                if not field or row.get("lat") is None or row.get("lon") is None:
                    continue
                try:
                    concentration = float(row[field])
                    latitude = float(row["lat"])
                    longitude = float(row["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if concentration < 0:
                    continue
                station_id = str(row.get("station_id") or "")
                if not station_id:
                    continue
                records_by_id[station_id] = {
                    "station_id": station_id,
                    "station_name": row.get("name") or station_id,
                    "station_type": row.get("station_type") or "regular",
                    "district": row.get("district"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "concentration": concentration,
                }
            frames.append({"time": hour, "records": list(records_by_id.values())})
        target = analysis.get("target_response") or {}
        episodes.append({
            "episode_id": analysis.get("episode_id"),
            "station_id": anchor.get("station_id"),
            "station_name": anchor.get("station_name"),
            "pollutant": pollutant,
            "episode_start": anchor.get("episode_start"),
            "episode_end": anchor.get("episode_end"),
            "peak_time": anchor.get("peak_time"),
            "target": {"station_id": anchor.get("station_id"), "latitude": target.get("lat"), "longitude": target.get("lon")},
            "frames": frames,
        })
    return {"episode_count": len(episodes), "episodes": episodes}


def build_hourly_map_weather(weather_rows: list[dict[str, Any]], target_date: str) -> dict[str, Any]:
    """Align NMC hourly wind observations to Shanghai local map hours."""
    weather_by_hour = {}
    for row in weather_rows:
        hour = normalize_hour(row.get("time"))
        if hour is None or hour.date().isoformat() != target_date:
            continue
        speed = _value(row.get("wind_speed_10m"))
        direction = _value(row.get("wind_direction_10m"))
        if direction is not None and direction > 360:
            direction = None
        weather_by_hour[hour.isoformat()] = {
            "station_name": "许昌气象站", "source": row.get("data_source") or "NMC",
            "wind_speed_ms": speed, "wind_direction_deg": direction,
            "wind_direction_name": _direction(direction) if direction is not None else None,
            "calm": speed is not None and speed < 0.5,
        }
    return weather_by_hour


def build_pollutant_map_frames(
    events: list[dict[str, Any]], regular_rows: list[dict[str, Any]],
    township_rows: list[dict[str, Any]], target_date: str,
    weather_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One full-day timeline per alerted pollutant, regardless of target station."""
    pollutants = sorted({str(event["pollutant"]) for event in events})
    target_ids = {str(event["station_id"]) for event in events}
    target_coordinates = []
    for row in regular_rows:
        if str(row.get("station_id")) in target_ids:
            try:
                coordinate = (float(row["lat"]), float(row["lon"]))
            except (TypeError, ValueError, KeyError):
                continue
            if coordinate not in target_coordinates:
                target_coordinates.append(coordinate)
    rows_by_hour: dict[str, list[dict[str, Any]]] = {}
    for row in [*regular_rows, *township_rows]:
        hour = normalize_hour(row.get("data_time"))
        if hour is not None and hour.date().isoformat() == target_date:
            rows_by_hour.setdefault(hour.isoformat(), []).append(row)
    weather_by_hour = build_hourly_map_weather(weather_rows or [], target_date)
    maps = []
    for pollutant in pollutants:
        field = POLLUTANT_SERIES_KEY.get(pollutant)
        pollutant_events = [event for event in events if event["pollutant"] == pollutant]
        frames = []
        all_values: list[float] = []
        day_start = datetime.fromisoformat(target_date)
        for offset in range(24):
            hour = (day_start + timedelta(hours=offset)).isoformat()
            records: dict[str, dict[str, Any]] = {}
            for row in rows_by_hour.get(hour, []):
                try:
                    value = float(row[field]) if field else float("nan")
                    lat, lon = float(row["lat"]), float(row["lon"])
                except (TypeError, ValueError, KeyError):
                    continue
                if not (0 <= value < float("inf")):
                    continue
                if row.get("station_type") == "township" and value == 0:
                    continue
                if target_coordinates and all(_haversine_km(lat, lon, target_lat, target_lon) > 20
                                              for target_lat, target_lon in target_coordinates):
                    continue
                station_id = str(row.get("station_id") or "")
                if station_id:
                    all_values.append(value)
                    records[station_id] = {
                        "station_id": station_id, "station_name": row.get("name") or station_id,
                        "station_type": row.get("station_type") or "regular",
                        "latitude": lat, "longitude": lon, "concentration": value,
                        "is_alert_station": station_id in target_ids,
                    }
            active = [event["event_id"] for event in pollutant_events
                      if any(interval["start_time"] <= hour <= interval["end_time"]
                             for interval in (event.get("alert_intervals") or [{
                                 "start_time": event["start_time"], "end_time": event["end_time"],
                             }]))]
            frames.append({"time": hour, "records": list(records.values()), "active_event_ids": active,
                           "weather": weather_by_hour.get(hour)})
        all_values.sort()
        low = all_values[int((len(all_values) - 1) * 0.1)] if all_values else 0
        high = all_values[int((len(all_values) - 1) * 0.9)] if all_values else 1
        maps.append({"pollutant": pollutant, "measurement_pollutant": "NO2" if pollutant == "NOX" else pollutant,
                     "event_ids": [event["event_id"] for event in pollutant_events],
                     "frames": frames, "scale_min": low, "scale_max": high})
    return {"pollutant_count": len(maps), "maps": maps,
            "description": "每种告警污染物一张地图；按昨日逐小时显示所有有坐标、有有效值的站点，标记当前小时处于告警过程的国控站。"}
