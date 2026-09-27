"""Screen inventory enterprises as field-check candidates, without attribution."""

from __future__ import annotations

import math
from typing import Any

from app.services.data_registry import data_registry
from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import XUCHANG_INVENTORY_DATA_ID


def _distance_and_bearing(lat: float, lon: float, source_lat: float, source_lon: float) -> tuple[float, float]:
    lat1, lat2 = math.radians(lat), math.radians(source_lat)
    delta_lat, delta_lon = lat2 - lat1, math.radians(source_lon - lon)
    part = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    distance = 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(part)))
    bearing = math.degrees(math.atan2(math.sin(delta_lon) * math.cos(lat2),
                                     math.cos(lat1) * math.sin(lat2) -
                                     math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon))) % 360
    return distance, bearing


def _dominant_wind(rows: list[dict[str, Any]], trigger_hours: set[str]) -> dict[str, Any]:
    vectors = []
    for row in rows:
        hour = str(row.get("time") or "")[:13]
        if hour not in trigger_hours:
            continue
        try:
            direction, speed = float(row["wind_direction_10m"]), float(row["wind_speed_10m_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        if speed < 0.5 or not 0 <= direction <= 360:
            continue
        vectors.append((math.cos(math.radians(direction)), math.sin(math.radians(direction)), speed))
    if len(vectors) < 2:
        return {"status": "insufficient_wind", "valid_hours": len(vectors)}
    x = sum(v[0] * v[2] for v in vectors)
    y = sum(v[1] * v[2] for v in vectors)
    resultant = math.hypot(x, y) / sum(v[2] for v in vectors)
    if resultant < 0.5:
        return {"status": "variable_wind", "valid_hours": len(vectors),
                "resultant": round(resultant, 3)}
    return {"status": "available", "valid_hours": len(vectors),
            "direction_from_deg": round(math.degrees(math.atan2(y, x)) % 360, 1),
            "resultant": round(resultant, 3)}


def screen_inventory_candidates(
    *, receptor_lat: float, receptor_lon: float, pollutant: str,
    meteorology_rows: list[dict[str, Any]], trigger_hours: list[str],
    records: list[dict[str, Any]] | None = None,
    radius_km: float = 5.0, half_angle_deg: float = 45.0,
) -> dict[str, Any]:
    """Restrict a registered inventory by observed upwind sector and distance."""
    wind = _dominant_wind(meteorology_rows, {str(hour)[:13] for hour in trigger_hours})
    if pollutant == "AQI":
        return {"status": "not_run", "reason": "unknown_primary_pollutant",
                "wind": wind, "enterprises": []}
    if wind["status"] != "available":
        return {"status": "not_run", "reason": wind["status"], "wind": wind, "enterprises": []}
    if records is None:
        try:
            records = data_registry.load_dataset(XUCHANG_INVENTORY_DATA_ID)
        except (KeyError, OSError, ValueError) as exc:
            return {"status": "not_run", "reason": f"inventory_unavailable:{type(exc).__name__}",
                    "wind": wind, "enterprises": []}
    if not isinstance(records, list):
        return {"status": "not_run", "reason": "invalid_inventory_asset", "wind": wind, "enterprises": []}
    candidates = []
    for item in records:
        if not isinstance(item, dict):
            continue
        try:
            source_lat, source_lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        distance, bearing = _distance_and_bearing(receptor_lat, receptor_lon, source_lat, source_lon)
        separation = abs((bearing - wind["direction_from_deg"] + 180) % 360 - 180)
        if distance > radius_km or separation > half_angle_deg:
            continue
        emissions = item.get("inventory_emissions") or {}
        annual_field = {"PM2.5": "emission_pm25", "PM10": "emission_pm10", "O3": "emission_vocs"}.get(pollutant)
        annual_value = emissions.get(annual_field) if annual_field else None
        candidates.append({
            "enterprise_name": item.get("enterprise_name"),
            "industry_category": item.get("industry_category"),
            "distance_km": round(distance, 2), "bearing_deg": round(bearing, 1),
            "annual_inventory_tonnes": annual_value, "inventory_period": item.get("inventory_period"),
            "coordinate_quality": item.get("coordinate_quality"),
            "screening_reason": "位于观测风来向扇区内且距离不超过5公里；仅供现场核查",
        })
    # Distance orders field checks; it is not a modeled source contribution.
    candidates.sort(key=lambda item: (item["distance_km"], item["enterprise_name"] or ""))
    return {"status": "screened", "wind": wind, "inventory_record_count": len(records),
            "candidate_count": len(candidates), "radius_km": radius_km,
            "half_angle_deg": half_angle_deg, "ranking_basis": "distance_for_field_check_only",
            "enterprises": candidates[:10],
            "interpretation_limit": "年度清单与风向只能筛出待核查对象，不代表同期排放或责任"}
