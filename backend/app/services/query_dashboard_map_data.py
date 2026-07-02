from __future__ import annotations

from typing import Any


def _coerce_records(dataset: Any, view: str | None = None) -> list[dict[str, Any]]:
    if isinstance(dataset, list):
        return [record for record in dataset if isinstance(record, dict)]

    if not isinstance(dataset, dict):
        return []

    if view:
        views = dataset.get("views")
        if isinstance(views, dict):
            records = views.get(view)
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]

        records = dataset.get(view)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]

    records = dataset.get("records") or dataset.get("data")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]

    return []


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _geojson_geometry(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if not isinstance(geometry_type, str) or coordinates is None:
        return None
    if geometry_type not in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        return None
    return value


def dataset_to_geojson_features(
    dataset: Any,
    *,
    longitude_field: str,
    latitude_field: str,
    view: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for record in _coerce_records(dataset, view=view):
        existing_geometry = _geojson_geometry(record.get("geometry"))
        if existing_geometry:
            properties = {
                key: value
                for key, value in record.items()
                if key != "geometry"
            }
            features.append({
                "type": "Feature",
                "geometry": existing_geometry,
                "properties": properties,
            })
            if len(features) >= limit:
                break
            continue

        longitude = _to_float(record.get(longitude_field))
        latitude = _to_float(record.get(latitude_field))
        if longitude is None or latitude is None:
            continue

        properties = {
            key: value
            for key, value in record.items()
            if key not in {longitude_field, latitude_field}
        }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [longitude, latitude],
            },
            "properties": properties,
        })
        if len(features) >= limit:
            break

    return features
