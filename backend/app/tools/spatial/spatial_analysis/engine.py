from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.services.data_registry import data_registry
from app.tools.spatial.core import (
    buffer_geometry_meters,
    distance_meters,
    geojson_to_shape,
    shape_area,
    shape_to_geojson,
)


SUPPORTED_OPS = {
    "aggregate",
    "area",
    "buffer",
    "clip",
    "contains",
    "distance",
    "filter",
    "intersect",
    "intersects",
    "nearest",
    "top_n",
    "upwind_sector",
    "within",
}
METERS_PER_DEGREE_LAT = 111_320.0
LON_FIELD_ALIASES = ("longitude", "lon", "lng", "经度", "x")
LAT_FIELD_ALIASES = ("latitude", "lat", "纬度", "y")


@dataclass
class FeatureSet:
    features: list[dict[str, Any]]
    geometry_type: str | None = None


def _failed(error_code: str, summary: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "summary": summary,
        "data": {"outputs": []},
        "metadata": {
            "tool_name": "spatial_analysis",
            "generator": "spatial_analysis",
            "error_code": error_code,
            **metadata,
        },
    }


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_m_between(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lat_mid = math.radians((lat1 + lat2) / 2.0)
    dx = (lon2 - lon1) * METERS_PER_DEGREE_LAT * max(math.cos(lat_mid), 0.01)
    dy = (lat2 - lat1) * METERS_PER_DEGREE_LAT
    return math.hypot(dx, dy)


def _point_coordinates(feature: dict[str, Any]) -> tuple[float, float] | None:
    coordinates = feature.get("geometry", {}).get("coordinates") or []
    if len(coordinates) < 2:
        return None
    lon = _to_float(coordinates[0])
    lat = _to_float(coordinates[1])
    if lon is None or lat is None:
        return None
    return lon, lat


def _bearing_degrees(from_lon: float, from_lat: float, to_lon: float, to_lat: float) -> float:
    lat_mid = math.radians((from_lat + to_lat) / 2.0)
    dx = (to_lon - from_lon) * max(math.cos(lat_mid), 0.01)
    dy = to_lat - from_lat
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def _angle_delta_degrees(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _point_feature(lon: float, lat: float, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": dict(properties),
    }


def _load_inline_feature(input_spec: dict[str, Any]) -> FeatureSet | None:
    geometry = input_spec.get("geometry")
    if not isinstance(geometry, dict):
        return None
    properties = input_spec.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    return FeatureSet(
        features=[{"type": "Feature", "geometry": geometry, "properties": dict(properties)}],
        geometry_type=str(geometry.get("type") or ""),
    )


def _feature_geometry_type(feature: dict[str, Any]) -> str | None:
    geometry = feature.get("geometry")
    if isinstance(geometry, dict):
        geometry_type = geometry.get("type")
        return str(geometry_type) if geometry_type else None
    return None


def _load_data_asset(input_spec: dict[str, Any]) -> FeatureSet | None:
    data_id = input_spec.get("data_id")
    geometry_spec = input_spec.get("geometry")
    if not data_id:
        return None

    entry = data_registry.get_metadata(str(data_id))
    dataset = data_registry.load_dataset(str(data_id))

    if isinstance(dataset, list):
        geometry_features: list[dict[str, Any]] = []
        for record in dataset:
            if not isinstance(record, dict) or not isinstance(record.get("geometry"), dict):
                continue
            properties = {str(key): value for key, value in record.items() if key != "geometry"}
            geometry_features.append(
                {"type": "Feature", "geometry": record["geometry"], "properties": properties}
            )
        if geometry_features:
            return FeatureSet(
                features=geometry_features,
                geometry_type=_feature_geometry_type(geometry_features[0]),
            )

    lon_field, lat_field = _resolve_lon_lat_fields(input_spec, entry.metadata if entry else {}, dataset)
    if not lon_field or not lat_field:
        return None

    if not isinstance(dataset, list):
        return FeatureSet(features=[], geometry_type="Point")

    features: list[dict[str, Any]] = []
    for record in dataset:
        if not isinstance(record, dict):
            continue
        lon = _to_float(record.get(str(lon_field)))
        lat = _to_float(record.get(str(lat_field)))
        if lon is None or lat is None:
            continue
        properties = {str(key): value for key, value in record.items()}
        features.append(_point_feature(lon, lat, properties))
    return FeatureSet(features=features, geometry_type="Point")


def _resolve_lon_lat_fields(
    input_spec: dict[str, Any],
    metadata: dict[str, Any],
    dataset: Any,
) -> tuple[str | None, str | None]:
    geometry_spec = input_spec.get("geometry")
    if isinstance(geometry_spec, dict):
        lon_field = geometry_spec.get("lon") or geometry_spec.get("longitude") or geometry_spec.get("x")
        lat_field = geometry_spec.get("lat") or geometry_spec.get("latitude") or geometry_spec.get("y")
        if lon_field and lat_field:
            return str(lon_field), str(lat_field)

    lon_field = metadata.get("longitude_field")
    lat_field = metadata.get("latitude_field")
    if lon_field and lat_field:
        return str(lon_field), str(lat_field)

    map_capabilities = metadata.get("map_capabilities")
    if isinstance(map_capabilities, dict):
        lon_field = map_capabilities.get("lon_field") or map_capabilities.get("longitude_field")
        lat_field = map_capabilities.get("lat_field") or map_capabilities.get("latitude_field")
        if lon_field and lat_field:
            return str(lon_field), str(lat_field)

    if isinstance(dataset, list):
        keys: set[str] = set()
        for record in dataset[:20]:
            if isinstance(record, dict):
                keys.update(str(key) for key in record)
        lon_field = next((field for field in LON_FIELD_ALIASES if field in keys), None)
        lat_field = next((field for field in LAT_FIELD_ALIASES if field in keys), None)
        if lon_field and lat_field:
            return lon_field, lat_field

    return None, None


def _normalize_inputs(inputs_spec: Any) -> dict[str, Any] | None:
    if isinstance(inputs_spec, dict):
        return inputs_spec

    if isinstance(inputs_spec, list):
        normalized: dict[str, Any] = {}
        for index, input_spec in enumerate(inputs_spec):
            if not isinstance(input_spec, dict):
                return None
            input_id = input_spec.get("id") or input_spec.get("name")
            if not input_id:
                return None
            normalized[str(input_id)] = {key: value for key, value in input_spec.items() if key not in {"id", "name"}}
        return normalized

    return None


def _load_inputs(inputs_spec: dict[str, Any]) -> tuple[dict[str, FeatureSet], dict[str, Any] | None]:
    inputs: dict[str, FeatureSet] = {}
    for input_id, input_spec in inputs_spec.items():
        if not isinstance(input_spec, dict):
            return {}, _failed("SPATIAL_SPEC_INVALID_INPUT", f"Invalid input spec for {input_id}", input_id=input_id)

        input_type = input_spec.get("type")
        try:
            if input_type == "inline-feature":
                feature_set = _load_inline_feature(input_spec)
            elif input_type == "data-asset":
                feature_set = _load_data_asset(input_spec)
            else:
                return {}, _failed(
                    "SPATIAL_SPEC_UNSUPPORTED_INPUT",
                    f"Unsupported spatial input type {input_type}",
                    input_id=input_id,
                    input_type=input_type,
                )
        except KeyError as exc:
            return {}, _failed(
                "SPATIAL_SPEC_INPUT_ASSET_NOT_FOUND",
                f"Input data asset not found for {input_id}",
                input_id=input_id,
                missing_data_id=str(exc),
            )

        if feature_set is None:
            return {}, _failed("SPATIAL_SPEC_INVALID_INPUT", f"Invalid input spec for {input_id}", input_id=input_id)
        inputs[str(input_id)] = feature_set
    return inputs, None


def _make_point_buffer(feature: dict[str, Any], distance_m: float, segments: int = 48) -> dict[str, Any]:
    geometry = geojson_to_shape(feature.get("geometry") or {})
    buffered = buffer_geometry_meters(geometry, distance_m)
    properties = dict(feature.get("properties") or {})
    extra_properties = {
        "buffer_distance_m": distance_m,
        "area_m2": round(buffered.area.square_meters, 3),
        "area_km2": round(buffered.area.square_kilometers, 6),
        "area_crs": buffered.area.crs,
    }
    if geometry.geom_type == "Point":
        extra_properties["buffer_center"] = [float(geometry.x), float(geometry.y)]
    properties.update(extra_properties)
    return {
        "type": "Feature",
        "geometry": shape_to_geojson(buffered.geometry),
        "properties": properties,
    }


def _op_buffer(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    input_id = step.get("input")
    source = refs.get(str(input_id))
    if source is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown buffer input {input_id}", step_id=step.get("id"))

    distance = _to_float(step.get("distance"))
    unit = step.get("unit", "m")
    if distance is None or distance <= 0 or unit not in {"m", "meter", "meters"}:
        return None, _failed("SPATIAL_SPEC_INVALID_DISTANCE", "Buffer distance must be a positive meter value", step_id=step.get("id"))

    polygons = [
        _make_point_buffer(feature, distance)
        for feature in source.features
        if feature.get("geometry", {}).get("type") == "Point"
    ]
    return FeatureSet(features=polygons, geometry_type="Polygon"), None


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[0], point[1]
        xj, yj = ring[j][0], ring[j][1]
        crosses = (yi > lat) != (yj > lat)
        if crosses:
            x_intersection = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lon < x_intersection:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(point: dict[str, Any], polygon: dict[str, Any]) -> bool:
    coordinates = point.get("geometry", {}).get("coordinates") or []
    rings = polygon.get("geometry", {}).get("coordinates") or []
    if len(coordinates) < 2 or not rings:
        return False
    return _point_in_ring(float(coordinates[0]), float(coordinates[1]), rings[0])


def _feature_shape(feature: dict[str, Any]):
    return geojson_to_shape(feature.get("geometry") or {})


def _op_intersect(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    left = refs.get(str(step.get("left")))
    right = refs.get(str(step.get("right")))
    if left is None or right is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", "Unknown intersect input", step_id=step.get("id"))

    output_features: list[dict[str, Any]] = []
    for left_feature in left.features:
        left_shape = _feature_shape(left_feature)
        for right_feature in right.features:
            right_shape = _feature_shape(right_feature)
            if not left_shape.intersects(right_shape):
                continue
            if left_shape.geom_type == "Point":
                output_features.append(left_feature)
                break
            intersection = left_shape.intersection(right_shape)
            if intersection.is_empty:
                continue
            properties = dict(left_feature.get("properties") or {})
            if intersection.geom_type in {"Polygon", "MultiPolygon"}:
                area = shape_area(intersection)
                properties.update(
                    {
                        "area_m2": round(area.square_meters, 3),
                        "area_km2": round(area.square_kilometers, 6),
                        "area_crs": area.crs,
                    }
                )
            output_features.append(
                {
                    "type": "Feature",
                    "geometry": shape_to_geojson(intersection),
                    "properties": properties,
                }
            )

    geometry_type = _feature_geometry_type(output_features[0]) if output_features else left.geometry_type
    return FeatureSet(features=output_features, geometry_type=geometry_type), None


def _compare_value(actual: Any, expected: Any, op: str) -> bool:
    if op in {"eq", "="}:
        return actual == expected
    if op in {"neq", "!="}:
        return actual != expected
    if op in {"contains", "like"}:
        return str(expected) in str(actual)
    if op == "in":
        return isinstance(expected, list) and actual in expected

    actual_num = _to_float(actual)
    expected_num = _to_float(expected)
    if actual_num is None or expected_num is None:
        return False
    if op in {"gt", ">"}:
        return actual_num > expected_num
    if op in {"gte", ">="}:
        return actual_num >= expected_num
    if op in {"lt", "<"}:
        return actual_num < expected_num
    if op in {"lte", "<="}:
        return actual_num <= expected_num
    return False


def _matches_where(properties: dict[str, Any], where: dict[str, Any]) -> bool:
    for field, condition in where.items():
        actual = properties.get(str(field))
        if isinstance(condition, dict):
            for op, expected in condition.items():
                if not _compare_value(actual, expected, str(op)):
                    return False
        elif actual != condition:
            return False
    return True


def _op_filter(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    source = refs.get(str(step.get("input")))
    if source is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown filter input {step.get('input')}", step_id=step.get("id"))

    where = step.get("where")
    if not isinstance(where, dict):
        return None, _failed("SPATIAL_SPEC_INVALID_FILTER", "filter requires a where object", step_id=step.get("id"))

    matched = [
        feature
        for feature in source.features
        if _matches_where(feature.get("properties") or {}, where)
    ]
    return FeatureSet(features=matched, geometry_type=source.geometry_type), None


def _op_distance(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    left = refs.get(str(step.get("left") or step.get("input")))
    right = refs.get(str(step.get("right") or step.get("to")))
    if left is None or right is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", "Unknown distance input", step_id=step.get("id"))
    if not right.features:
        return None, _failed("SPATIAL_SPEC_UNSUPPORTED_DISTANCE", "distance requires non-empty right input", step_id=step.get("id"))

    output_features: list[dict[str, Any]] = []
    for feature in left.features:
        source_shape = _feature_shape(feature)
        nearest_distance: float | None = None
        nearest_index: int | None = None
        nearest_crs: str | None = None
        for index, target in enumerate(right.features):
            target_shape = _feature_shape(target)
            distance = distance_meters(source_shape, target_shape)
            distance_m = distance.meters
            if nearest_distance is None or distance_m < nearest_distance:
                nearest_distance = distance_m
                nearest_index = index
                nearest_crs = distance.crs
        if nearest_distance is None:
            continue
        enriched = {
            **feature,
            "properties": {
                **(feature.get("properties") or {}),
                "distance_m": round(nearest_distance, 3),
                "distance_km": round(nearest_distance / 1000.0, 6),
                "nearest_target_index": nearest_index,
                "distance_crs": nearest_crs,
            },
        }
        output_features.append(enriched)
    return FeatureSet(features=output_features, geometry_type=left.geometry_type), None


def _op_area(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    source = refs.get(str(step.get("input")))
    if source is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown area input {step.get('input')}", step_id=step.get("id"))

    records: list[dict[str, Any]] = []
    for index, feature in enumerate(source.features):
        geometry = _feature_shape(feature)
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        area = shape_area(geometry)
        records.append(
            {
                "type": "Record",
                "properties": {
                    **(feature.get("properties") or {}),
                    "feature_index": index,
                    "area_m2": round(area.square_meters, 3),
                    "area_km2": round(area.square_kilometers, 6),
                    "area_crs": area.crs,
                },
            }
        )
    return FeatureSet(features=records, geometry_type=None), None


def _op_clip(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    source = refs.get(str(step.get("input")))
    mask = refs.get(str(step.get("mask") or step.get("clip") or step.get("right")))
    if source is None or mask is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", "Unknown clip input or mask", step_id=step.get("id"))

    output_features: list[dict[str, Any]] = []
    mask_shapes = [_feature_shape(feature) for feature in mask.features]
    for feature in source.features:
        geometry = _feature_shape(feature)
        clipped = None
        for mask_shape in mask_shapes:
            current = geometry.intersection(mask_shape)
            if current.is_empty:
                continue
            clipped = current if clipped is None else clipped.union(current)
        if clipped is None or clipped.is_empty:
            continue
        properties = dict(feature.get("properties") or {})
        if clipped.geom_type in {"Polygon", "MultiPolygon"}:
            area = shape_area(clipped)
            properties.update(
                {
                    "area_m2": round(area.square_meters, 3),
                    "area_km2": round(area.square_kilometers, 6),
                    "area_crs": area.crs,
                }
            )
        output_features.append(
            {
                "type": "Feature",
                "geometry": shape_to_geojson(clipped),
                "properties": properties,
            }
        )
    geometry_type = _feature_geometry_type(output_features[0]) if output_features else source.geometry_type
    return FeatureSet(features=output_features, geometry_type=geometry_type), None


def _op_predicate(step: dict[str, Any], refs: dict[str, FeatureSet], predicate: str) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    left = refs.get(str(step.get("left") or step.get("input")))
    right = refs.get(str(step.get("right") or step.get("target") or step.get("mask")))
    if left is None or right is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown {predicate} input", step_id=step.get("id"))

    selected: list[dict[str, Any]] = []
    for feature in left.features:
        geometry = _feature_shape(feature)
        for target in right.features:
            target_geometry = _feature_shape(target)
            if getattr(geometry, predicate)(target_geometry):
                selected.append(feature)
                break
    return FeatureSet(features=selected, geometry_type=left.geometry_type), None


def _op_nearest(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    result, error = _op_distance(step, refs)
    if error or result is None:
        return result, error
    limit = int(_to_float(step.get("limit"),) or 10)
    max_distance = _to_float(step.get("max_distance") or step.get("distance"))

    features = sorted(
        result.features,
        key=lambda feature: _to_float((feature.get("properties") or {}).get("distance_m")) or float("inf"),
    )
    if max_distance is not None:
        features = [
            feature
            for feature in features
            if (_to_float((feature.get("properties") or {}).get("distance_m")) or float("inf")) <= max_distance
        ]
    return FeatureSet(features=features[: max(1, limit)], geometry_type=result.geometry_type), None


def _op_top_n(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    source = refs.get(str(step.get("input")))
    if source is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown top_n input {step.get('input')}", step_id=step.get("id"))
    field = step.get("field")
    if not field:
        return None, _failed("SPATIAL_SPEC_INVALID_TOP_N", "top_n requires field", step_id=step.get("id"))
    limit = int(_to_float(step.get("limit")) or 10)
    reverse = str(step.get("order") or "desc").lower() != "asc"
    features = sorted(
        source.features,
        key=lambda feature: _to_float((feature.get("properties") or {}).get(str(field))) or 0.0,
        reverse=reverse,
    )
    return FeatureSet(features=features[: max(1, limit)], geometry_type=source.geometry_type), None


def _op_upwind_sector(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    sources = refs.get(str(step.get("sources") or step.get("left") or step.get("input")))
    receptor = refs.get(str(step.get("receptor") or step.get("right") or step.get("to")))
    if sources is None or receptor is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", "Unknown upwind_sector input", step_id=step.get("id"))
    if sources.geometry_type != "Point" or receptor.geometry_type != "Point" or not receptor.features:
        return None, _failed("SPATIAL_SPEC_UNSUPPORTED_UPWIND", "upwind_sector requires point source and receptor inputs", step_id=step.get("id"))

    wind_from = _to_float(step.get("wind_from_degrees"))
    angle = _to_float(step.get("angle_degrees"),) or 60.0
    max_distance = _to_float(step.get("distance") or step.get("max_distance"))
    if wind_from is None:
        return None, _failed("SPATIAL_SPEC_INVALID_UPWIND", "upwind_sector requires wind_from_degrees", step_id=step.get("id"))
    receptor_coords = _point_coordinates(receptor.features[0])
    if receptor_coords is None:
        return None, _failed("SPATIAL_SPEC_INVALID_UPWIND", "receptor must have coordinates", step_id=step.get("id"))

    selected: list[dict[str, Any]] = []
    for feature in sources.features:
        coords = _point_coordinates(feature)
        if coords is None:
            continue
        bearing = _bearing_degrees(receptor_coords[0], receptor_coords[1], coords[0], coords[1])
        distance_m = _distance_m_between(receptor_coords[0], receptor_coords[1], coords[0], coords[1])
        if max_distance is not None and distance_m > max_distance:
            continue
        if _angle_delta_degrees(bearing, wind_from) <= angle / 2.0:
            selected.append(
                {
                    **feature,
                    "properties": {
                        **(feature.get("properties") or {}),
                        "distance_m": round(distance_m, 3),
                        "bearing_from_receptor_degrees": round(bearing, 3),
                        "upwind_direction_degrees": float(wind_from),
                    },
                }
            )
    selected.sort(key=lambda feature: _to_float((feature.get("properties") or {}).get("distance_m")) or float("inf"))
    return FeatureSet(features=selected, geometry_type=sources.geometry_type), None


def _op_aggregate(step: dict[str, Any], refs: dict[str, FeatureSet]) -> tuple[FeatureSet | None, dict[str, Any] | None]:
    source = refs.get(str(step.get("input")))
    if source is None:
        return None, _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown aggregate input {step.get('input')}", step_id=step.get("id"))

    group_by = [str(field) for field in step.get("group_by") or []]
    metrics = [metric for metric in (step.get("metrics") or [{"func": "count", "as": "count"}]) if isinstance(metric, dict)]
    if not metrics:
        return None, _failed("SPATIAL_SPEC_INVALID_AGGREGATE", "aggregate requires metrics", step_id=step.get("id"))
    unsupported = [
        metric.get("func")
        for metric in metrics
        if metric.get("func") not in {"count", "sum", "avg", "max", "min"}
    ]
    if unsupported:
        return None, _failed("SPATIAL_SPEC_UNSUPPORTED_METRIC", f"Unsupported aggregate metrics: {unsupported}", step_id=step.get("id"))

    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for feature in source.features:
        properties = feature.get("properties") or {}
        key = tuple(properties.get(field) for field in group_by)
        buckets.setdefault(key, []).append(properties)

    records: list[dict[str, Any]] = []
    for key, bucket_records in buckets.items():
        record = {field: key[index] for index, field in enumerate(group_by)}
        for metric in metrics:
            func = str(metric.get("func"))
            output_name = str(metric.get("as") or metric.get("field") or func)
            if func == "count":
                record[output_name] = len(bucket_records)
                continue
            field = str(metric.get("field") or "")
            values = [
                value
                for value in (_to_float(item.get(field)) for item in bucket_records)
                if value is not None
            ]
            if func == "sum":
                record[output_name] = sum(values)
            elif func == "avg":
                record[output_name] = sum(values) / len(values) if values else None
            elif func == "max":
                record[output_name] = max(values) if values else None
            elif func == "min":
                record[output_name] = min(values) if values else None
        records.append(record)
    return FeatureSet(features=[{"type": "Record", "properties": record} for record in records], geometry_type=None), None


def _feature_to_record(feature: dict[str, Any], asset_schema: str) -> dict[str, Any]:
    properties = dict(feature.get("properties") or {})
    geometry = feature.get("geometry")
    if asset_schema == "spatial_point_asset" and isinstance(geometry, dict) and geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) >= 2:
            properties.setdefault("longitude", coordinates[0])
            properties.setdefault("latitude", coordinates[1])
        return properties
    if geometry:
        properties["geometry"] = geometry
    return properties


def _register_output(
    output_spec: dict[str, Any],
    feature_set: FeatureSet,
    *,
    intent: str | None,
) -> dict[str, Any]:
    output_id = str(output_spec["id"])
    asset_schema = str(output_spec.get("asset_schema") or "spatial_result_asset")
    records = [_feature_to_record(feature, asset_schema) for feature in feature_set.features]
    entry = data_registry.register_dataset(
        asset_schema,
        "v1",
        records,
        data_id=f"{asset_schema}:v1:{uuid4().hex}",
        metadata={
            "name": output_spec.get("name") or output_id,
            "source": "spatial_analysis",
            "intent": intent,
            "asset_type": asset_schema,
            "geometry": feature_set.geometry_type,
            "output_id": output_id,
            "map_capabilities": (
                {"geometry": "point", "lon_field": "longitude", "lat_field": "latitude"}
                if asset_schema == "spatial_point_asset"
                else {"geometry": (feature_set.geometry_type or "table").lower()}
            ),
        },
    )
    return {
        "id": output_id,
        "data_id": entry.data_id,
        "asset_schema": asset_schema,
        "record_count": len(records),
        "geometry": feature_set.geometry_type,
        "as": output_spec.get("as"),
    }


def _infer_asset_schema(feature_set: FeatureSet, output_spec: dict[str, Any]) -> str:
    if output_spec.get("asset_schema"):
        return str(output_spec["asset_schema"])
    geometry_type = (feature_set.geometry_type or "").lower()
    if geometry_type == "point":
        return "spatial_point_asset"
    if geometry_type in {"polygon", "multipolygon"}:
        return "spatial_polygon_asset"
    if not geometry_type:
        return "analysis_table_asset"
    return "spatial_result_asset"


def _normalize_output_ref(output_id: str, output_spec: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(output_spec)
    normalized.setdefault("id", output_id)
    if "from_step" not in normalized:
        normalized["from_step"] = normalized.get("from") or output_id
    if normalized.get("type") in {"layer", "point-layer", "polygon-layer"}:
        normalized.setdefault("as", "map-layer")
    elif normalized.get("type") and not normalized.get("as"):
        normalized["as"] = normalized.get("type")
    return normalized


def _normalize_outputs(outputs: Any) -> list[dict[str, Any]] | None:
    if isinstance(outputs, list):
        normalized = []
        for output in outputs:
            if not isinstance(output, dict):
                return None
            output_id = output.get("id") or output.get("name") or output.get("from_step") or output.get("from")
            if not output_id:
                return None
            normalized.append(_normalize_output_ref(str(output_id), output))
        return normalized

    if isinstance(outputs, dict):
        normalized = []
        for output_id, output_spec in outputs.items():
            if not isinstance(output_spec, dict):
                return None
            normalized.append(_normalize_output_ref(str(output_id), output_spec))
        return normalized

    return None


def _normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(step)
    if "id" not in normalized and normalized.get("name"):
        normalized["id"] = normalized["name"]

    params = normalized.get("params")
    if isinstance(params, dict):
        for key in ("distance", "unit", "units"):
            if key in params and key not in normalized:
                normalized[key] = params[key]
        if "unit" not in normalized and "units" in normalized:
            normalized["unit"] = normalized["units"]

    return normalized


def execute_spatial_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return _failed("SPATIAL_SPEC_INVALID", "spatial_analysis requires a JSON object spec")

    inputs_spec = _normalize_inputs(spec.get("inputs"))
    raw_steps = spec.get("steps")
    outputs = _normalize_outputs(spec.get("outputs"))
    if not isinstance(inputs_spec, dict) or not isinstance(raw_steps, list) or outputs is None:
        return _failed("SPATIAL_SPEC_INVALID", "spec must contain inputs, steps, and outputs")

    refs, error = _load_inputs(inputs_spec)
    if error:
        return error

    for raw_step in raw_steps:
        step = _normalize_step(raw_step) if isinstance(raw_step, dict) else raw_step
        if not isinstance(step, dict):
            return _failed("SPATIAL_SPEC_INVALID_STEP", "Each step must be an object")
        step_id = step.get("id")
        op = step.get("op")
        if not step_id:
            return _failed("SPATIAL_SPEC_INVALID_STEP", "Each step must have an id")
        if op not in SUPPORTED_OPS:
            return _failed(
                "SPATIAL_SPEC_UNSUPPORTED_OP",
                f"Unsupported spatial op {op}",
                step_id=step_id,
                supported_ops=sorted(SUPPORTED_OPS),
            )
        if op == "buffer":
            result, error = _op_buffer(step, refs)
        elif op == "area":
            result, error = _op_area(step, refs)
        elif op == "clip":
            result, error = _op_clip(step, refs)
        elif op == "intersect":
            result, error = _op_intersect(step, refs)
        elif op in {"within", "contains", "intersects"}:
            result, error = _op_predicate(step, refs, op)
        elif op == "filter":
            result, error = _op_filter(step, refs)
        elif op == "distance":
            result, error = _op_distance(step, refs)
        elif op == "nearest":
            result, error = _op_nearest(step, refs)
        elif op == "top_n":
            result, error = _op_top_n(step, refs)
        elif op == "upwind_sector":
            result, error = _op_upwind_sector(step, refs)
        else:
            result, error = _op_aggregate(step, refs)
        if error:
            return error
        refs[str(step_id)] = result or FeatureSet(features=[])

    registered_outputs: list[dict[str, Any]] = []
    for output in outputs:
        if not isinstance(output, dict) or not output.get("id"):
            return _failed("SPATIAL_SPEC_INVALID_OUTPUT", "Each output must reference a step id")
        output_id = str(output["id"])
        source_id = str(output.get("from_step") or output_id)
        feature_set = refs.get(source_id)
        if feature_set is None:
            return _failed("SPATIAL_SPEC_REF_NOT_FOUND", f"Unknown output id {source_id}", output_id=source_id)
        output = {**output, "asset_schema": _infer_asset_schema(feature_set, output)}
        registered_outputs.append(_register_output(output, feature_set, intent=spec.get("intent")))

    return {
        "status": "success",
        "success": True,
        "summary": f"空间分析完成，生成 {len(registered_outputs)} 个结果资产。",
        "data": {
            "version": spec.get("version") or "spatial-spec.v1",
            "intent": spec.get("intent"),
            "outputs": registered_outputs,
            "supported_ops": sorted(SUPPORTED_OPS),
        },
        "metadata": {
            "tool_name": "spatial_analysis",
            "generator": "spatial_analysis",
            "schema_version": "spatial_analysis.v1",
            "output_count": len(registered_outputs),
            "supported_ops": sorted(SUPPORTED_OPS),
        },
    }
