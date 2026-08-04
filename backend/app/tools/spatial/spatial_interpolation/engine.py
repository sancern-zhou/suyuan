from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata


try:  # pragma: no cover - environment dependent
    from pykrige.ok import OrdinaryKriging

    HAS_PYKRIGE = True
except Exception:  # pragma: no cover - environment dependent
    OrdinaryKriging = None
    HAS_PYKRIGE = False


SUPPORTED_METHODS = {"kriging", "idw", "linear", "cubic", "nearest"}
SURFACE_COLORS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]


def _failed(error_code: str, summary: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "summary": summary,
        "data": {"outputs": []},
        "visuals": [],
        "metadata": {
            "tool_name": "spatial_interpolation",
            "generator": "spatial_interpolation",
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


def _load_points(spec: dict[str, Any], context) -> tuple[list[dict[str, float]], dict[str, Any] | None]:
    file_path = str(spec.get("file_path") or "")
    lon_field = str(spec.get("lon") or spec.get("longitude") or "longitude")
    lat_field = str(spec.get("lat") or spec.get("latitude") or "latitude")
    value_field = str(spec.get("value") or spec.get("value_field") or "")
    if not file_path or not value_field:
        return [], _failed("SPATIAL_SPEC_INVALID_INPUT", "file_path and value field are required")

    try:
        dataset = context.get_raw_data(file_path)
    except KeyError:
        return [], _failed("SPATIAL_INPUT_NOT_FOUND", f"file_path not found: {file_path}", file_path=file_path)

    if not isinstance(dataset, list):
        return [], _failed("SPATIAL_INPUT_INVALID", "interpolation input dataset must be a list", file_path=file_path)

    points: list[dict[str, float]] = []
    seen: dict[tuple[float, float], list[float]] = {}
    for record in dataset:
        if not isinstance(record, dict):
            continue
        lon = _to_float(record.get(lon_field))
        lat = _to_float(record.get(lat_field))
        value = _to_float(record.get(value_field))
        if lon is None or lat is None or value is None:
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        seen.setdefault((lon, lat), []).append(value)

    for (lon, lat), values in seen.items():
        points.append({"longitude": lon, "latitude": lat, "value": sum(values) / len(values)})

    if len(points) < 3:
        return [], _failed(
            "SPATIAL_INSUFFICIENT_POINTS",
            "At least 3 valid concentration points are required for interpolation",
            valid_point_count=len(points),
        )
    return points, None


def _bounds(points: list[dict[str, float]], padding_ratio: float = 0.08) -> tuple[float, float, float, float]:
    lons = np.array([point["longitude"] for point in points], dtype=float)
    lats = np.array([point["latitude"] for point in points], dtype=float)
    lon_min, lon_max = float(lons.min()), float(lons.max())
    lat_min, lat_max = float(lats.min()), float(lats.max())
    lon_pad = max((lon_max - lon_min) * padding_ratio, 0.005)
    lat_pad = max((lat_max - lat_min) * padding_ratio, 0.005)
    return lon_min - lon_pad, lat_min - lat_pad, lon_max + lon_pad, lat_max + lat_pad


def _grid_for_points(points: list[dict[str, float]], grid_size: int) -> tuple[np.ndarray, np.ndarray]:
    lon_min, lat_min, lon_max, lat_max = _bounds(points)
    xs = np.linspace(lon_min, lon_max, grid_size)
    ys = np.linspace(lat_min, lat_max, grid_size)
    return np.meshgrid(xs, ys)


def _idw(points: list[dict[str, float]], xi: np.ndarray, yi: np.ndarray, power: float = 2.0) -> np.ndarray:
    lons = np.array([point["longitude"] for point in points], dtype=float)
    lats = np.array([point["latitude"] for point in points], dtype=float)
    values = np.array([point["value"] for point in points], dtype=float)
    zi = np.zeros_like(xi, dtype=float)
    for row in range(xi.shape[0]):
        for col in range(xi.shape[1]):
            distances = np.hypot(xi[row, col] - lons, yi[row, col] - lats)
            exact = np.where(distances < 1e-12)[0]
            if len(exact):
                zi[row, col] = values[int(exact[0])]
                continue
            weights = 1.0 / np.power(distances, power)
            zi[row, col] = float(np.sum(weights * values) / np.sum(weights))
    return zi


def _griddata_interpolate(points: list[dict[str, float]], xi: np.ndarray, yi: np.ndarray, method: str) -> np.ndarray:
    source_points = np.array([[point["longitude"], point["latitude"]] for point in points], dtype=float)
    values = np.array([point["value"] for point in points], dtype=float)
    zi = griddata(source_points, values, (xi, yi), method=method)
    if np.isnan(zi).any():
        nearest = griddata(source_points, values, (xi, yi), method="nearest")
        zi = np.where(np.isnan(zi), nearest, zi)
    return zi


def _kriging(points: list[dict[str, float]], xi: np.ndarray, yi: np.ndarray) -> np.ndarray:
    if OrdinaryKriging is None:
        raise RuntimeError("PyKrige is not available")
    lons = np.array([point["longitude"] for point in points], dtype=float)
    lats = np.array([point["latitude"] for point in points], dtype=float)
    values = np.array([point["value"] for point in points], dtype=float)
    ok = OrdinaryKriging(lons, lats, values, variogram_model="linear", verbose=False, enable_plotting=False)
    grid_x = xi[0, :]
    grid_y = yi[:, 0]
    z, _ = ok.execute("grid", grid_x, grid_y)
    return np.asarray(z, dtype=float)


def _grid_records(xi: np.ndarray, yi: np.ndarray, zi: np.ndarray) -> list[dict[str, float]]:
    records: list[dict[str, float]] = []
    for row in range(xi.shape[0]):
        for col in range(xi.shape[1]):
            records.append(
                {
                    "longitude": round(float(xi[row, col]), 8),
                    "latitude": round(float(yi[row, col]), 8),
                    "value": round(float(zi[row, col]), 6),
                }
            )
    return records


def _surface_color(value: float, value_min: float, value_max: float) -> str:
    if value_max <= value_min:
        return SURFACE_COLORS[len(SURFACE_COLORS) // 2]
    ratio = (value - value_min) / (value_max - value_min)
    index = min(len(SURFACE_COLORS) - 1, max(0, int(ratio * len(SURFACE_COLORS))))
    return SURFACE_COLORS[index]


def _surface_records(xi: np.ndarray, yi: np.ndarray, zi: np.ndarray) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    value_min = float(np.nanmin(zi))
    value_max = float(np.nanmax(zi))
    for row in range(xi.shape[0] - 1):
        for col in range(xi.shape[1] - 1):
            value = float(np.mean([
                zi[row, col],
                zi[row, col + 1],
                zi[row + 1, col + 1],
                zi[row + 1, col],
            ]))
            coordinates = [[
                [round(float(xi[row, col]), 8), round(float(yi[row, col]), 8)],
                [round(float(xi[row, col + 1]), 8), round(float(yi[row, col + 1]), 8)],
                [round(float(xi[row + 1, col + 1]), 8), round(float(yi[row + 1, col + 1]), 8)],
                [round(float(xi[row + 1, col]), 8), round(float(yi[row + 1, col]), 8)],
                [round(float(xi[row, col]), 8), round(float(yi[row, col]), 8)],
            ]]
            records.append(
                {
                    "value": round(value, 6),
                    "fill_color": _surface_color(value, value_min, value_max),
                    "fill_opacity": 0.58,
                    "stroke_color": "rgba(255,255,255,0)",
                    "stroke_opacity": 0,
                    "geometry": {"type": "Polygon", "coordinates": coordinates},
                }
            )
    return records


def _contour_records(xi: np.ndarray, yi: np.ndarray, zi: np.ndarray, contour_levels: int) -> list[dict[str, Any]]:
    fig, ax = plt.subplots()
    contour = ax.contour(xi, yi, zi, levels=contour_levels)
    records: list[dict[str, Any]] = []
    for level, segments in zip(contour.levels, contour.allsegs):
        for segment in segments:
            if len(segment) < 2:
                continue
            coordinates = [[round(float(x), 8), round(float(y), 8)] for x, y in segment.tolist()]
            records.append(
                {
                    "level": round(float(level), 6),
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )
    plt.close(fig)
    return records


def _register_dataset(asset_schema: str, records: list[dict[str, Any]], metadata: dict[str, Any], context) -> dict[str, Any]:
    file_path = context.save_data(records, schema=asset_schema, metadata=metadata)
    return {"file_path": file_path, "record_count": len(records), "asset_schema": asset_schema}


def execute_interpolation(spec: dict[str, Any], context) -> dict[str, Any]:
    if not isinstance(spec, dict):
        return _failed("SPATIAL_SPEC_INVALID", "spatial_interpolation requires a JSON object spec")

    method_requested = str(spec.get("method") or "idw").lower()
    if method_requested not in SUPPORTED_METHODS:
        return _failed(
            "SPATIAL_INTERPOLATION_METHOD_UNSUPPORTED",
            f"Unsupported interpolation method {method_requested}",
            supported_methods=sorted(SUPPORTED_METHODS),
        )

    points, error = _load_points(spec, context)
    if error:
        return error

    warnings: list[dict[str, Any]] = []
    method_applied = method_requested
    if method_requested == "kriging" and not HAS_PYKRIGE:
        if not bool(spec.get("allow_fallback")):
            return _failed(
                "SPATIAL_DEPENDENCY_MISSING",
                "PyKrige is required for kriging interpolation. Set allow_fallback=true to use IDW.",
                dependency="PyKrige",
            )
        method_applied = "idw"
        warnings.append(
            {
                "code": "SPATIAL_INTERPOLATION_FALLBACK",
                "message": "PyKrige is not available; IDW interpolation was used instead of kriging.",
            }
        )

    if method_applied == "kriging" and len(points) < 8:
        return _failed(
            "SPATIAL_INSUFFICIENT_POINTS",
            "At least 8 valid points are required for kriging interpolation",
            valid_point_count=len(points),
        )

    grid_size = max(8, min(200, int(_to_float(spec.get("grid_size")) or 50)))
    contour_levels = max(3, min(30, int(_to_float(spec.get("contour_levels")) or 10)))
    xi, yi = _grid_for_points(points, grid_size)

    if method_applied == "idw":
        zi = _idw(points, xi, yi, power=float(_to_float(spec.get("power")) or 2.0))
    elif method_applied == "kriging":
        zi = _kriging(points, xi, yi)
    else:
        if method_applied in {"linear", "cubic"} and len(points) < 4:
            return _failed(
                "SPATIAL_INSUFFICIENT_POINTS",
                f"At least 4 valid points are required for {method_applied} interpolation",
                valid_point_count=len(points),
            )
        zi = _griddata_interpolate(points, xi, yi, method_applied)

    grid_records = _grid_records(xi, yi, zi)
    surface_records = _surface_records(xi, yi, zi)
    contour_records = _contour_records(xi, yi, zi, contour_levels)
    pollutant = str(spec.get("pollutant") or spec.get("pollutant_name") or spec.get("value") or "concentration")
    unit = str(spec.get("unit") or "")

    common_metadata = {
        "source": "spatial_interpolation",
        "source_file_path": spec.get("file_path"),
        "method_requested": method_requested,
        "method_applied": method_applied,
        "pollutant": pollutant,
        "unit": unit,
        "sample_count": len(points),
        "grid_size": grid_size,
        "contour_levels": contour_levels,
        "value_range": {"min": float(np.nanmin(zi)), "max": float(np.nanmax(zi))},
        "warnings": warnings,
    }

    grid_output = _register_dataset(
        "interpolation_grid_asset",
        grid_records,
        {
            **common_metadata,
            "name": f"{pollutant} interpolation grid",
            "asset_type": "interpolation_grid_asset",
            "map_capabilities": {"geometry": "point", "lon_field": "longitude", "lat_field": "latitude"},
        }, context,
    )
    surface_output = _register_dataset(
        "interpolation_surface_asset",
        surface_records,
        {
            **common_metadata,
            "name": f"{pollutant} interpolation surface",
            "asset_type": "interpolation_surface_asset",
            "map_capabilities": {"geometry": "polygon", "style_fields": ["fill_color", "fill_opacity"]},
            "legend": {
                "field": "value",
                "colors": SURFACE_COLORS,
                "value_range": common_metadata["value_range"],
            },
        }, context,
    )
    contour_output = _register_dataset(
        "contour_line_asset",
        contour_records,
        {
            **common_metadata,
            "name": f"{pollutant} contour lines",
            "asset_type": "contour_line_asset",
            "map_capabilities": {"geometry": "linestring"},
        }, context,
    )

    return {
        "status": "success",
        "success": True,
        "summary": f"空间插值完成，方法 {method_applied}，生成网格和等值线资产。",
        "data": {
            "outputs": [
                {"id": "grid", **grid_output},
                {"id": "surface", **surface_output},
                {"id": "contours", **contour_output},
            ],
            "value_range": common_metadata["value_range"],
        },
        "visuals": [],
        "metadata": {
            "tool_name": "spatial_interpolation",
            "generator": "spatial_interpolation",
            "schema_version": "spatial_interpolation.v1",
            **common_metadata,
        },
    }
