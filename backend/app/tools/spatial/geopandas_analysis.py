"""Lazy, auditable GeoPandas helpers for project spatial analysis.

This module complements the existing GeoJSON/Shapely spatial engine. It does
not register a new agent tool and does not load GeoPandas for ordinary tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


class GeoPandasUnavailableError(RuntimeError):
    """Raised when a spatial table operation needs the optional dependency."""


def geopandas_available() -> bool:
    try:
        import geopandas  # noqa: F401
    except ImportError:
        return False
    return True


def points_to_geodataframe(
    records: Iterable[Mapping[str, Any]],
    *,
    longitude: str = "longitude",
    latitude: str = "latitude",
    crs: str = "EPSG:4326",
):
    """Build a point GeoDataFrame after validating coordinates and CRS."""
    gpd = _import_geopandas()
    rows = [dict(record) for record in records]
    if not rows:
        raise ValueError("records must contain at least one row")
    missing = [field for field in (longitude, latitude) if field not in rows[0]]
    if missing:
        raise ValueError(f"missing coordinate fields: {', '.join(missing)}")
    try:
        lon = [float(row[longitude]) for row in rows]
        lat = [float(row[latitude]) for row in rows]
    except (TypeError, ValueError) as exc:
        raise ValueError("coordinate fields must contain numeric values") from exc
    if any(abs(value) > 180 for value in lon) or any(abs(value) > 90 for value in lat):
        raise ValueError("coordinates are outside longitude/latitude bounds")
    return gpd.GeoDataFrame(rows, geometry=gpd.points_from_xy(lon, lat), crs=crs)


def read_geojson(path: str | Path, *, target_crs: str | None = None):
    """Read a GeoJSON-like file and optionally transform to a declared CRS."""
    gpd = _import_geopandas()
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError("input spatial file has no declared CRS")
    if target_crs:
        frame = frame.to_crs(target_crs)
    return frame


def spatial_join(left, right, *, predicate: str = "within", how: str = "left"):
    """Join spatial attributes after requiring matching coordinate systems."""
    _require_matching_crs(left, right)
    return left.sjoin(right, how=how, predicate=predicate)


def nearest_join(left, right, *, how: str = "left", max_distance: float | None = None):
    """Join the nearest feature; distance is meaningful only in a metric CRS."""
    _require_matching_crs(left, right)
    if left.crs is None or not left.crs.is_projected:
        raise ValueError("nearest joins require a projected metric CRS")
    return left.sjoin_nearest(right, how=how, max_distance=max_distance, distance_col="distance")


def write_geojson(frame, path: str | Path) -> str:
    """Write a spatial result and return its normalized path."""
    _import_geopandas()
    if frame.crs is None:
        raise ValueError("output GeoDataFrame must declare a CRS")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(output, driver="GeoJSON")
    return str(output)


def _require_matching_crs(left, right) -> None:
    if left.crs is None or right.crs is None:
        raise ValueError("both spatial inputs must declare a CRS")
    if left.crs != right.crs:
        raise ValueError("spatial inputs must use the same CRS; transform explicitly first")


def _import_geopandas():
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise GeoPandasUnavailableError(
            "geopandas is not installed; add it to the backend_py311 environment "
            "before requesting table-based spatial analysis"
        ) from exc
    return gpd
