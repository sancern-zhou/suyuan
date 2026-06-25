from __future__ import annotations

from typing import Any


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, current in enumerate(ring):
        xi, yi = current[0], current[1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def points_within_polygon(
    points: list[dict[str, Any]],
    polygon: dict[str, Any],
    *,
    lon_field: str,
    lat_field: str,
) -> list[dict[str, Any]]:
    if polygon.get("type") != "Polygon":
        raise ValueError("Only Polygon geometry is supported in gisctl v0")
    rings = polygon.get("coordinates") or []
    if not rings:
        return []
    outer = rings[0]
    result = []
    for point in points:
        try:
            lon = float(point[lon_field])
            lat = float(point[lat_field])
        except (KeyError, TypeError, ValueError):
            continue
        if _point_in_ring(lon, lat, outer):
            result.append(point)
    return result


def bbox_for_features(features: list[dict[str, Any]], *, lon_field: str, lat_field: str) -> list[float] | None:
    coordinates: list[tuple[float, float]] = []
    for feature in features:
        try:
            coordinates.append((float(feature[lon_field]), float(feature[lat_field])))
        except (KeyError, TypeError, ValueError):
            continue
    if not coordinates:
        return None
    lons = [item[0] for item in coordinates]
    lats = [item[1] for item in coordinates]
    return [min(lons), min(lats), max(lons), max(lats)]
