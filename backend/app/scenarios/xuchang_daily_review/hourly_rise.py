"""Deterministic hourly rise selection for yesterday's station review."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any

from .episodes import TZ_SHANGHAI, normalize_hour
from app.scenarios.xuchang_station_deviation.service import canonical_station_identity

RULE_VERSION = "xuchang_daily_hourly_rise/v1"
ABSOLUTE_RISE = {"PM2.5": 10.0, "PM10": 15.0, "NO2": 8.0, "SO2": 6.0, "CO": 0.3}
SERIES_FIELDS = {"PM2.5": "pm25", "PM10": "pm10", "NO2": "no2", "SO2": "so2", "CO": "co"}


def _value(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) and value >= 0 else None


def detect_hourly_rises(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any]:
    """Require 2 or 3 consecutive, strictly increasing hourly steps."""
    by_key: dict[tuple[str, str], dict[datetime, float | None]] = defaultdict(dict)
    names: dict[str, str] = {}
    conflicted: set[tuple[str, str, datetime]] = set()
    for row in rows:
        station_id = str(row.get("station_id") or "")
        hour = normalize_hour(row.get("data_time"))
        if not station_id or hour is None:
            continue
        names.setdefault(station_id, str(row.get("name") or station_id))
        for pollutant, field in SERIES_FIELDS.items():
            key = station_id, pollutant
            value = _value(row.get(field))
            if row.get(f"{field}_mark"):
                value = None
            duplicate_key = station_id, pollutant, hour
            if duplicate_key in conflicted:
                continue
            if hour in by_key[key] and by_key[key][hour] != value:
                by_key[key][hour] = None
                conflicted.add(duplicate_key)
            else:
                by_key[key].setdefault(hour, value)

    events: list[dict[str, Any]] = []
    checked_windows = valid_windows = qualified_windows = 0
    for (station_id, pollutant), series in sorted(by_key.items()):
        candidates = []
        for end in sorted(hour for hour in series if hour.date() == target_date):
            for duration in (2, 3):
                hours = [end - timedelta(hours=offset) for offset in range(duration, -1, -1)]
                checked_windows += 1
                values = [series.get(hour) for hour in hours]
                if any(value is None for value in values):
                    continue
                if values[0] <= 0:
                    continue
                valid_windows += 1
                if any(right <= left for left, right in zip(values, values[1:])):
                    continue
                delta = values[-1] - values[0]
                if values[-1] + 1e-9 < values[0] * 1.5 or delta + 1e-9 < ABSOLUTE_RISE[pollutant]:
                    continue
                qualified_windows += 1
                candidates.append({"start": hours[0], "end": end})
        candidates.sort(key=lambda item: (item["start"], item["end"]))
        groups: list[list[dict[str, datetime]]] = []
        for candidate in candidates:
            if groups and candidate["start"] <= max(item["end"] for item in groups[-1]):
                groups[-1].append(candidate)
            else:
                groups.append([candidate])
        for group in groups:
            start = min(item["start"] for item in group)
            end = max(item["end"] for item in group)
            hours = [start + timedelta(hours=offset) for offset in range(int((end - start).total_seconds() // 3600) + 1)]
            values = [series[hour] for hour in hours]
            delta = values[-1] - values[0]
            windows = [(item["start"].isoformat(), item["end"].isoformat()) for item in group]
            observations = [{"time": hour.isoformat(), "concentration": value} for hour, value in zip(hours, values)]
            evidence = {"rule_version": RULE_VERSION, "station_id": station_id,
                        "pollutant": pollutant, "observations": observations, "qualified_windows": windows}
            version = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            process_id = f"hourly-rise-{start:%Y%m%d%H}-{station_id}-{pollutant.lower().replace('.', '')}"
            events.append({
                "episode_id": process_id, "episode_status": "confirmed", "station_id": station_id,
                "station_name": names[station_id], "target_pollutant": pollutant,
                "measurement_granularity": "hour", "alert_type": "daily_hourly_rise",
                "episode_start": hours[1].isoformat(), "episode_end": end.isoformat(),
                "rise_reference_time": start.isoformat(),
                "alert_hours": [hour.isoformat() for hour in hours[1:]],
                "hourly_observations": observations, "start_concentration": values[0],
                "end_concentration": values[-1], "peak_time": end.isoformat(), "peak_value": values[-1],
                "rise_absolute": round(delta, 3), "rise_percent": round(delta / values[0] * 100, 1),
                "minimum_absolute_rise": ABSOLUTE_RISE[pollutant],
                "duration_hours": int((end - start).total_seconds() // 3600),
                "qualified_windows": windows, "evidence_version": version, "rule_version": RULE_VERSION,
                "parent_alert_event_ids": [], "source_episode_ids": [], "minute_clues": [],
                "source_evidence_status": "not_applicable", "source_features": [],
            })
    events.sort(key=lambda item: (item["episode_start"], item["station_id"], item["target_pollutant"]))
    valid_target_hours = {f"{station_id}:{pollutant}": sum(
        hour.date() == target_date and value is not None for hour, value in series.items()
    ) for (station_id, pollutant), series in sorted(by_key.items())}
    return {"rule_version": RULE_VERSION, "target_date": target_date.isoformat(),
            "checked_windows": checked_windows, "valid_windows": valid_windows,
            "qualified_windows": qualified_windows,
            "duplicate_conflicts": len(conflicted), "valid_target_hours": valid_target_hours,
            "quality_policy": "空值、负值、非有限值、冲突重复小时及提供了污染物质控标记的值不参与；小时源查询本身不含独立质控字段",
            "event_count": len(events), "events": events}


def attach_minute_clues(events: list[dict[str, Any]], episode_anchors: list[dict[str, Any]]) -> None:
    """Attach same-station/pollutant five-minute episode facts within the rise."""
    for event in events:
        start = datetime.fromisoformat(event["rise_reference_time"])
        end = datetime.fromisoformat(event["episode_end"]) + timedelta(hours=1)
        for anchor in episode_anchors:
            if (canonical_station_identity(anchor.get("station_id"))[0] != event["station_id"]
                or anchor.get("target_pollutant") != event["target_pollutant"]
                or anchor.get("measurement_granularity") not in {"5min", "minute"}):
                continue
            matched_alerts = []
            boundary_matches = []
            for item in anchor.get("source_alerts") or []:
                raw = item.get("occurred_at")
                if not raw:
                    continue
                try:
                    timestamp = datetime.fromisoformat(str(raw))
                except ValueError:
                    continue
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
                if start <= timestamp < end:
                    matched_alerts.append((timestamp.isoformat(), item))
            for raw in (anchor.get("source_started_at"), anchor.get("source_last_seen_at")):
                if not raw:
                    continue
                try:
                    timestamp = datetime.fromisoformat(str(raw))
                except ValueError:
                    continue
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
                if start <= timestamp < end:
                    boundary_matches.append(timestamp.isoformat())
            if not matched_alerts and not boundary_matches:
                continue
            matched_ids = sorted({str(item.get("event_id")) for _, item in matched_alerts if item.get("event_id")})
            matched_features = [item["source_features"] for _, item in matched_alerts if isinstance(item.get("source_features"), dict)]
            event["source_episode_ids"].append(anchor["episode_id"])
            event["parent_alert_event_ids"].extend(matched_ids)
            event["source_features"].extend(matched_features)
            event["minute_clues"].append({
                "episode_id": anchor["episode_id"], "alert_type": anchor.get("alert_type"),
                "matched_times": sorted({time for time, _ in matched_alerts} | set(boundary_matches)),
                "event_ids": matched_ids,
                "association_method": "matched_alert_time" if matched_alerts else "episode_boundary_time",
                "evidence_status": anchor.get("source_evidence_status"),
            })
        event["source_episode_ids"] = sorted(set(event["source_episode_ids"]))
        event["parent_alert_event_ids"] = sorted(set(event["parent_alert_event_ids"]))
