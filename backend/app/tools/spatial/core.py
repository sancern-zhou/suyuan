from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


WGS84_CRS = "EPSG:4326"


@dataclass(frozen=True)
class AreaResult:
    square_meters: float
    square_kilometers: float
    crs: str


@dataclass(frozen=True)
class DistanceResult:
    meters: float
    kilometers: float
    crs: str


@dataclass(frozen=True)
class BufferedGeometry:
    geometry: BaseGeometry
    area: AreaResult
    crs: str


def geojson_to_shape(geometry: dict[str, Any]) -> BaseGeometry:
    if not isinstance(geometry, dict):
        raise ValueError("GeoJSON geometry must be an object")
    geom = shape(geometry)
    if geom.is_empty:
        raise ValueError("GeoJSON geometry is empty")
    if not geom.is_valid:
        repaired = geom.buffer(0)
        if repaired.is_empty or not repaired.is_valid:
            raise ValueError("GeoJSON geometry is invalid")
        geom = repaired
    return geom


def shape_to_geojson(geometry: BaseGeometry) -> dict[str, Any]:
    return dict(mapping(geometry))


def choose_local_metric_crs(geometry: BaseGeometry) -> str:
    centroid = geometry.centroid
    lon = float(centroid.x)
    lat = float(centroid.y)
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return f"EPSG:{epsg}"


def _project(geometry: BaseGeometry, source_crs: str, target_crs: str) -> BaseGeometry:
    transformer = Transformer.from_crs(CRS.from_user_input(source_crs), CRS.from_user_input(target_crs), always_xy=True)
    return transform(transformer.transform, geometry)


def _project_pair(left: BaseGeometry, right: BaseGeometry, source_crs: str = WGS84_CRS) -> tuple[BaseGeometry, BaseGeometry, str]:
    combined = left.union(right)
    target_crs = choose_local_metric_crs(combined)
    return _project(left, source_crs, target_crs), _project(right, source_crs, target_crs), target_crs


def shape_area(geometry: BaseGeometry, source_crs: str = WGS84_CRS) -> AreaResult:
    target_crs = choose_local_metric_crs(geometry)
    projected = _project(geometry, source_crs, target_crs)
    area_m2 = float(projected.area)
    return AreaResult(square_meters=area_m2, square_kilometers=area_m2 / 1_000_000.0, crs=target_crs)


def distance_meters(left: BaseGeometry, right: BaseGeometry, source_crs: str = WGS84_CRS) -> DistanceResult:
    projected_left, projected_right, target_crs = _project_pair(left, right, source_crs=source_crs)
    distance_m = float(projected_left.distance(projected_right))
    return DistanceResult(meters=distance_m, kilometers=distance_m / 1000.0, crs=target_crs)


def buffer_geometry_meters(geometry: BaseGeometry, distance_m: float, source_crs: str = WGS84_CRS) -> BufferedGeometry:
    if distance_m <= 0:
        raise ValueError("Buffer distance must be positive")
    target_crs = choose_local_metric_crs(geometry)
    projected = _project(geometry, source_crs, target_crs)
    buffered_projected = projected.buffer(distance_m)
    buffered_wgs84 = _project(buffered_projected, target_crs, source_crs)
    area = AreaResult(
        square_meters=float(buffered_projected.area),
        square_kilometers=float(buffered_projected.area) / 1_000_000.0,
        crs=target_crs,
    )
    return BufferedGeometry(geometry=buffered_wgs84, area=area, crs=target_crs)


def transform_shape_to_metric(geometry: BaseGeometry, source_crs: str = WGS84_CRS) -> tuple[BaseGeometry, str]:
    target_crs = choose_local_metric_crs(geometry)
    return _project(geometry, source_crs, target_crs), target_crs


def transform_shape(geometry: BaseGeometry, source_crs: str, target_crs: str) -> BaseGeometry:
    return _project(geometry, source_crs, target_crs)
