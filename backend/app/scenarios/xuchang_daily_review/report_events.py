"""Deterministic facts for chapter two of the Xuchang daily review."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import atan2, cos, degrees, radians, sin
import re
from typing import Any

from app.scenarios.xuchang_daily_review.episodes import normalize_hour
from app.scenarios.xuchang_daily_review.regional_response import (
    POLLUTANT_SERIES_KEY,
    _bearing_deg,
    _haversine_km,
)

WIND_CONE_HALF_WIDTH_DEG = 67.5
MIN_DIRECTIONAL_WIND_SPEED = 0.5
MAX_NEIGHBOR_DISTANCE_KM = 20
MAX_UPWIND_STATIONS = 10
MAX_UNALERTED_GAP_HOURS = 1
COMPASS_8 = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


def _value(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value < float("inf") else None


def _direction(degrees_from_north: float) -> str:
    return COMPASS_8[int((degrees_from_north + 22.5) // 45) % 8]


def _wind_for_hours(weather_rows: list[dict[str, Any]], hours: set[datetime]) -> dict[str, Any]:
    east = north = weight = 0.0
    count = 0
    for row in weather_rows:
        hour = normalize_hour(row.get("time"))
        direction = _value(row.get("wind_direction_10m"))
        speed = _value(row.get("wind_speed_10m"))
        if hour not in hours or direction is None or speed is None or speed < MIN_DIRECTIONAL_WIND_SPEED:
            continue
        angle = radians(direction % 360)
        east += sin(angle) * speed
        north += cos(angle) * speed
        weight += speed
        count += 1
    if not count or (east * east + north * north) ** 0.5 / weight < 0.15:
        return {"status": "insufficient_data", "direction_deg": None, "direction_name": None, "valid_hours": count}
    direction = round(degrees(atan2(east, north)) % 360, 1)
    return {"status": "ok", "direction_deg": direction, "direction_name": _direction(direction), "valid_hours": count,
            "definition": "NMC 10米风向为来向；按有效小时风速加权矢量均值，静风(<0.5 m/s)不计"}


def build_report_events(
    analyses: list[dict[str, Any]], regular_rows: list[dict[str, Any]],
    township_rows: list[dict[str, Any]], weather_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge same-station/pollutant alerts across at most one unalerted hour.

    An event is anchored to Scenario-1 alerts. No new alerts are inferred from
    station concentrations. Overlapping, next-hour, and one-hour-interrupted
    episodes join one event; actual alert intervals are retained separately.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for analysis in analyses:
        anchor = analysis.get("alert_anchor") or {}
        start = normalize_hour(anchor.get("episode_start"))
        end = normalize_hour(anchor.get("episode_end"))
        key = (str(anchor.get("station_id") or ""), str(anchor.get("target_pollutant") or "").upper())
        if key[0] and key[1] and start:
            groups[key].append({"start": start, "end": max(start, end or start), "analysis": analysis})

    grouped: list[dict[str, Any]] = []
    for (station_id, pollutant), candidates in groups.items():
        candidates.sort(key=lambda item: (item["start"], item["end"]))
        for candidate in candidates:
            if grouped and grouped[-1]["station_id"] == station_id and grouped[-1]["pollutant"] == pollutant and candidate["start"] <= grouped[-1]["end"] + timedelta(hours=MAX_UNALERTED_GAP_HOURS + 1):
                grouped[-1]["end"] = max(grouped[-1]["end"], candidate["end"])
                grouped[-1]["analyses"].append(candidate["analysis"])
            else:
                grouped.append({"station_id": station_id, "pollutant": pollutant,
                                "start": candidate["start"], "end": candidate["end"], "analyses": [candidate["analysis"]]})
    grouped.sort(key=lambda item: (item["start"], item["station_id"], item["pollutant"]))

    hourly: dict[tuple[str, datetime], dict[str, Any]] = {}
    for row in [*regular_rows, *township_rows]:
        hour = normalize_hour(row.get("data_time"))
        station_id = str(row.get("station_id") or "")
        if hour and station_id:
            hourly[(station_id, hour)] = row

    events = []
    for index, group in enumerate(grouped, 1):
        source_windows = []
        for analysis in group["analyses"]:
            source_anchor = analysis.get("alert_anchor") or {}
            source_start = normalize_hour(source_anchor.get("episode_start"))
            source_end = normalize_hour(source_anchor.get("episode_end"))
            if source_start is not None:
                source_windows.append({"start": source_start, "end": max(source_start, source_end or source_start),
                                       "analysis": analysis})
        alert_hours = {
            item["start"] + timedelta(hours=offset)
            for item in source_windows
            for offset in range(int((item["end"] - item["start"]).total_seconds() // 3600) + 1)
        }
        alert_intervals = []
        for alert_hour in sorted(alert_hours):
            if alert_intervals and alert_hour <= alert_intervals[-1]["end"] + timedelta(hours=1):
                alert_intervals[-1]["end"] = alert_hour
            else:
                alert_intervals.append({"start": alert_hour, "end": alert_hour})
        first = group["analyses"][0]
        anchor = first.get("alert_anchor") or {}
        target = first.get("target_response") or {}
        field = POLLUTANT_SERIES_KEY.get(group["pollutant"])
        hours = [group["start"] + timedelta(hours=i) for i in range(int((group["end"] - group["start"]).total_seconds() // 3600) + 1)]
        target_values = [(hour, _value((hourly.get((group["station_id"], hour)) or {}).get(field))) for hour in hours] if field else []
        target_values = [(hour, value) for hour, value in target_values if value is not None]
        preceding_hour = group["start"] - timedelta(hours=1)
        preceding_value = _value((hourly.get((group["station_id"], preceding_hour)) or {}).get(field)) if field else None
        first_value = preceding_value if preceding_value is not None else (target_values[0][1] if target_values else None)
        reference_time = preceding_hour if preceding_value is not None else (target_values[0][0] if target_values else None)
        last_value = target_values[-1][1] if target_values else None
        peak_hour, peak_value = max(target_values, key=lambda pair: pair[1]) if target_values else (None, None)
        rise = round(peak_value - first_value, 3) if first_value is not None else None
        wind = _wind_for_hours(weather_rows, set(hours))
        target_lat, target_lon = _value(target.get("lat")), _value(target.get("lon"))
        neighbors = []
        for station_id in sorted({str(row.get("station_id")) for row in township_rows if row.get("station_id")}):
            observed = [(hour, hourly.get((station_id, hour))) for hour in hours]
            values_by_hour = [(hour, _value((row or {}).get(field))) for hour, row in observed] if field else []
            # Township source encodes missing pollutant observations as zero.
            values_by_hour = [(hour, value) for hour, value in values_by_hour if value is not None and value > 0]
            row = next((row for _, row in observed if row and row.get("lat") is not None and row.get("lon") is not None), None)
            if not values_by_hour or row is None or target_lat is None or target_lon is None:
                continue
            lat, lon = _value(row.get("lat")), _value(row.get("lon"))
            if lat is None or lon is None:
                continue
            distance = _haversine_km(target_lat, target_lon, lat, lon)
            if distance > MAX_NEIGHBOR_DISTANCE_KM:
                continue
            bearing = _bearing_deg(target_lat, target_lon, lat, lon)
            wind_deg = wind["direction_deg"]
            if wind_deg is None or abs((bearing - wind_deg + 180) % 360 - 180) > WIND_CONE_HALF_WIDTH_DEG:
                continue
            mean = round(sum(value for _, value in values_by_hour) / len(values_by_hour), 3)
            target_by_hour = dict(target_values)
            comparable_pairs = [(value, target_by_hour[hour]) for hour, value in values_by_hour if hour in target_by_hour]
            comparable_mean = round(sum(value for value, _ in comparable_pairs) / len(comparable_pairs), 3) if comparable_pairs else None
            target_mean = round(sum(value for _, value in comparable_pairs) / len(comparable_pairs), 3) if comparable_pairs else None
            neighbors.append({"station_id": station_id, "station_name": row.get("name") or station_id,
                              "district": row.get("district"), "distance_km": round(distance, 2),
                              "bearing_deg": round(bearing, 1), "bearing_name": _direction(bearing),
                              "concentration_mean": mean, "valid_hours": len(values_by_hour),
                              "comparison_concentration_mean": comparable_mean,
                              "target_comparison_mean": target_mean, "comparable_hours": len(comparable_pairs),
                              "vs_target": ("高于" if comparable_mean > target_mean else "低于" if comparable_mean < target_mean else "持平") if target_mean is not None else "无法对比"})
        neighbors.sort(key=lambda item: (item["distance_km"], item["station_id"]))
        candidate_count = len(neighbors)
        neighbors = neighbors[:MAX_UPWIND_STATIONS]
        station_name = re.sub(r"[（(]启用[^）)]*[）)]", "", str(anchor.get("station_name") or group["station_id"])).strip()
        events.append({"event_id": f"review-{index:03d}", "station_id": group["station_id"],
                       "station_name": station_name, "pollutant": group["pollutant"],
                       "measurement_pollutant": "NO2" if group["pollutant"] == "NOX" else group["pollutant"],
                       "start_time": group["start"].isoformat(), "end_time": group["end"].isoformat(),
                       "source_episode_ids": [item.get("episode_id") for item in group["analyses"]],
                       "alert_intervals": [{"start_time": item["start"].isoformat(), "end_time": item["end"].isoformat()} for item in alert_intervals],
                       "alert_hour_count": len(alert_hours), "gap_hour_count": len(hours) - len(alert_hours),
                       "valid_target_hours": len(target_values),
                       "reference_time": reference_time.isoformat() if reference_time else None,
                       "reference_kind": "告警前一小时" if preceding_value is not None else "事件内首个有效小时",
                       "start_concentration": first_value, "end_concentration": last_value,
                       "peak_concentration": peak_value, "peak_time": peak_hour.isoformat() if peak_hour else None,
                       "peak_rise_absolute": rise,
                       "peak_rise_percent": round(100 * rise / first_value, 1) if first_value and rise is not None else None,
                       "target_mean": round(sum(value for _, value in target_values) / len(target_values), 3) if target_values else None,
                       "wind": wind, "upwind_candidate_count": candidate_count,
                       "upwind_township_stations": neighbors,
                       "upwind_selection": f"风向来向±{WIND_CONE_HALF_WIDTH_DEG:g}°，距目标站不超过{MAX_NEIGHBOR_DISTANCE_KM:g}km，按距离取最近{MAX_UPWIND_STATIONS}站；浓度为事件时段有效小时均值，与目标站仅在同小时可比样本上对比"})
        if len(alert_intervals) > 1:
            segments = []
            for interval in alert_intervals:
                sources = [item["analysis"] for item in source_windows
                           if item["start"] <= interval["end"] and item["end"] >= interval["start"]]
                segment = build_report_events(sources, regular_rows, township_rows, weather_rows)["events"][0]
                segment.pop("event_id")
                segments.append(segment)
            events[-1]["segments"] = segments
    return {"event_count": len(events), "events": events,
            "method": "同一国控站同一污染物，场景一告警 episode 重叠、下一小时接续或中间仅隔1个无告警小时即合并；不跨站或污染物合并。保留实际告警时段，过程统计覆盖合并后的时间跨度。升幅=过程内峰值-告警前一小时有效值；该小时缺测则用过程内首个有效小时值。"}
