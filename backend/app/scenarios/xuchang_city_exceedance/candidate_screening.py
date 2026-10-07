"""Rank inventory enterprises as field-check candidates via an explainable score.

The score is annual inventory emissions attenuated with distance
(``tonnes / (1 + distance_km / 10)``).  It orders field checks; it is not a
modelled contribution or a responsibility ranking.  The observed upwind
sector is carried as an annotation instead of a hard filter so the list
survives calm or variable winds.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.data_registry import data_registry
from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import XUCHANG_INVENTORY_DATA_ID

DECAY_SCALE_KM = 10.0
UPWIND_HALF_ANGLE_DEG = 45.0
ANNUAL_EMISSION_FIELD = {
    "PM2.5": "emission_pm25", "PM10": "emission_pm10",
    "O3": "emission_vocs", "NOX": "emission_nox",
}


def _distance_and_bearing(lat: float, lon: float, source_lat: float, source_lon: float) -> tuple[float, float]:
    lat1, lat2 = math.radians(lat), math.radians(source_lat)
    delta_lat, delta_lon = lat2 - lat1, math.radians(source_lon - lon)
    part = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    distance = 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(part)))
    bearing = math.degrees(math.atan2(math.sin(delta_lon) * math.cos(lat2),
                                      math.cos(lat1) * math.sin(lat2) -
                                      math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon))) % 360
    return distance, bearing


def _dominant_wind(rows: list[dict[str, Any]], hours: set[str]) -> dict[str, Any]:
    vectors = []
    for row in rows:
        hour = str(row.get("time") or "")[:13]
        if hour not in hours:
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
    high_value_point: dict[str, Any] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Rank the registered inventory by emission-with-distance-decay score."""
    wind = _dominant_wind(meteorology_rows, {str(hour)[:13] for hour in trigger_hours})
    if pollutant == "AQI":
        return {"status": "not_run", "reason": "unknown_primary_pollutant",
                "wind": wind, "enterprises": []}
    annual_field = ANNUAL_EMISSION_FIELD.get(pollutant)
    if annual_field is None:
        return {"status": "not_run", "reason": "unsupported_pollutant",
                "wind": wind, "enterprises": []}
    if records is None:
        try:
            records = data_registry.load_dataset(XUCHANG_INVENTORY_DATA_ID)
        except (KeyError, OSError, ValueError) as exc:
            return {"status": "not_run", "reason": f"inventory_unavailable:{type(exc).__name__}",
                    "wind": wind, "enterprises": []}
    if not isinstance(records, list):
        return {"status": "not_run", "reason": "invalid_inventory_asset", "wind": wind, "enterprises": []}
    candidates = []
    skipped_without_emissions = 0
    for item in records:
        if not isinstance(item, dict):
            continue
        try:
            source_lat, source_lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        emissions = item.get("inventory_emissions") or {}
        try:
            annual_value = float(emissions[annual_field])
        except (KeyError, TypeError, ValueError):
            annual_value = 0.0
        if annual_value <= 0:
            skipped_without_emissions += 1
            continue
        distance, bearing = _distance_and_bearing(receptor_lat, receptor_lon, source_lat, source_lon)
        separation = abs((bearing - wind.get("direction_from_deg", bearing) + 180) % 360 - 180)
        in_upwind_sector = (
            wind["status"] == "available"
            and separation <= UPWIND_HALF_ANGLE_DEG
        )
        high_value_distance = None
        if high_value_point:
            try:
                high_value_distance, _ = _distance_and_bearing(
                    float(high_value_point["lat"]), float(high_value_point["lon"]),
                    source_lat, source_lon,
                )
            except (KeyError, TypeError, ValueError):
                high_value_distance = None
        score = annual_value / (1.0 + distance / DECAY_SCALE_KM)
        candidates.append({
            "enterprise_name": item.get("enterprise_name"),
            "industry_category": item.get("industry_category"),
            "district": item.get("district") or None,
            "screening_score": round(score, 1),
            "annual_inventory_tonnes": round(annual_value, 2),
            "distance_km": round(distance, 2),
            "bearing_deg": round(bearing, 1),
            "in_upwind_sector": in_upwind_sector,
            "distance_to_high_value_km": (
                round(high_value_distance, 2) if high_value_distance is not None else None
            ),
            "inventory_period": item.get("inventory_period"),
            "coordinate_quality": item.get("coordinate_quality"),
        })
    # The decay score only orders field checks; it is not a source contribution.
    candidates.sort(key=lambda item: (-item["screening_score"], item["enterprise_name"] or ""))
    return {
        "status": "screened" if candidates else "no_eligible_candidates",
        "wind": wind,
        "inventory_record_count": len(records),
        "ranked_candidate_count": len(candidates),
        "skipped_without_emissions": skipped_without_emissions,
        "ranking_basis": (
            f"清单年排放量/(1+距离/{DECAY_SCALE_KM:.0f}km)距离衰减筛查得分，仅排序现场核查顺序"
        ),
        "upwind_sector_deg": UPWIND_HALF_ANGLE_DEG,
        "enterprises": candidates[:top_n],
        "interpretation_limit": (
            "筛查得分只是核查顺序参考，不代表同期排放、贡献率或企业责任；"
            "风向扇区为标注信息，不构成筛选门槛"
        ),
    }
