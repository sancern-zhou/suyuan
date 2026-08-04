from __future__ import annotations

import re

from app.schemas.gis_map import MapLayerSpec, MapProgram
from app.fetchers.consultation.city_mapping import CITY_NAME_TO_CODE


def _slug(value: str) -> str:
    aliases = {
        "广州": "guang_zhou",
        "广州市": "guang_zhou",
        "广东": "guang_dong",
        "广东省": "guang_dong",
        "珠三角": "pearl_river_delta",
    }
    stripped = value.strip()
    if stripped in aliases:
        return aliases[stripped]
    city_code = CITY_NAME_TO_CODE.get(stripped)
    if city_code:
        return f"city_{city_code}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", stripped).strip("_").lower()
    if not slug and stripped:
        slug = "_".join(f"u{ord(char):x}" for char in stripped)
    return slug or "view"


def create_point_layer_program(
    *,
    data_id: str,
    layer_id: str,
    name: str,
    longitude_field: str,
    latitude_field: str,
    color_by: str | None = None,
    breaks: list[float] | None = None,
    colors: list[str] | None = None,
    icon: str | None = None,
    icon_by: str | None = None,
    icon_map: dict[str, str] | None = None,
    default_icon: str | None = None,
    fit_bounds: bool = True,
    turn_id: str | None = None,
) -> MapProgram:
    style = {"type": "classified" if breaks else "simple"}
    if color_by:
        style["field"] = color_by
    if breaks:
        style["breaks"] = breaks
    if colors:
        style["colors"] = colors
    if icon:
        style["icon"] = icon
    if icon_by:
        style["icon_by"] = icon_by
    if icon_map:
        style["icon_map"] = icon_map
    if default_icon:
        style["default_icon"] = default_icon

    layer = MapLayerSpec(
        id=layer_id,
        name=name,
        layer_type="point",
        data={"type": "file_path", "path": data_id},
        geometry={
            "type": "point",
            "longitude_field": longitude_field,
            "latitude_field": latitude_field,
        },
        style=style,
        interactions={
            "selectable": True,
            "popup_fields": ["station_name", "city", color_by] if color_by else ["station_name", "city"],
        },
    )

    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_{layer_id}",
        intent=f"Render point layer {name}",
        state={
            "view": {"fit_bounds": fit_bounds},
            "layers": [layer],
        },
        lineage={
            "source_file_paths": [data_id],
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )


def create_polygon_layer_program(
    *,
    data_id: str,
    layer_id: str,
    name: str,
    fill_color: str | None = None,
    fill_opacity: float | None = None,
    stroke_color: str | None = None,
    stroke_weight: float | int | None = None,
    fit_bounds: bool = True,
    turn_id: str | None = None,
) -> MapProgram:
    style = {
        "type": "simple",
        "fill_color": fill_color or "#2f80ed",
        "fill_opacity": 0.18 if fill_opacity is None else fill_opacity,
        "stroke_color": stroke_color or "#1f5fbf",
        "stroke_weight": 2 if stroke_weight is None else stroke_weight,
    }

    layer = MapLayerSpec(
        id=layer_id,
        name=name,
        layer_type="polygon",
        data={"type": "file_path", "path": data_id},
        geometry={"type": "geojson", "geometry_field": "geometry"},
        style=style,
        interactions={
            "selectable": True,
            "popup_fields": ["name", "buffer_distance_m"],
        },
    )

    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_{layer_id}",
        intent=f"Render polygon layer {name}",
        state={
            "view": {"fit_bounds": fit_bounds},
            "layers": [layer],
        },
        lineage={
            "source_file_paths": [data_id],
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )


def create_line_layer_program(
    *,
    data_id: str,
    layer_id: str,
    name: str,
    stroke_color: str | None = None,
    stroke_weight: float | int | None = None,
    stroke_opacity: float | None = None,
    fit_bounds: bool = True,
    turn_id: str | None = None,
) -> MapProgram:
    style = {
        "type": "simple",
        "stroke_color": stroke_color or "#d7191c",
        "stroke_weight": 2 if stroke_weight is None else stroke_weight,
        "stroke_opacity": 0.92 if stroke_opacity is None else stroke_opacity,
    }

    layer = MapLayerSpec(
        id=layer_id,
        name=name,
        layer_type="line",
        data={"type": "file_path", "path": data_id},
        geometry={"type": "geojson", "geometry_field": "geometry"},
        style=style,
        interactions={
            "selectable": True,
            "popup_fields": ["level", "name"],
        },
    )

    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_{layer_id}",
        intent=f"Render line layer {name}",
        state={
            "view": {"fit_bounds": fit_bounds},
            "layers": [layer],
        },
        lineage={
            "source_file_paths": [data_id],
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )


def create_interpolation_layer_program(
    *,
    data_id: str,
    layer_id: str,
    name: str,
    fill_color: str | None = None,
    fill_opacity: float | None = None,
    stroke_color: str | None = None,
    stroke_weight: float | int | None = None,
    stroke_opacity: float | None = None,
    fit_bounds: bool = True,
    turn_id: str | None = None,
) -> MapProgram:
    style = {
        "type": "interpolation_surface",
        "feature_fill_color_field": "fill_color",
        "feature_fill_opacity_field": "fill_opacity",
        "feature_stroke_color_field": "stroke_color",
        "feature_stroke_opacity_field": "stroke_opacity",
        "fill_color": fill_color or "#fdae61",
        "fill_opacity": 0.58 if fill_opacity is None else fill_opacity,
        "stroke_color": stroke_color or "rgba(255,255,255,0)",
        "stroke_weight": 0 if stroke_weight is None else stroke_weight,
        "stroke_opacity": 0 if stroke_opacity is None else stroke_opacity,
    }

    layer = MapLayerSpec(
        id=layer_id,
        name=name,
        layer_type="polygon",
        data={"type": "file_path", "path": data_id, "limit": 5000},
        geometry={"type": "geojson", "geometry_field": "geometry"},
        style=style,
        interactions={
            "selectable": True,
            "popup_fields": ["value", "level", "name"],
        },
    )

    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_{layer_id}",
        intent=f"Render interpolation surface layer {name}",
        state={
            "view": {"fit_bounds": fit_bounds},
            "layers": [layer],
        },
        lineage={
            "source_file_paths": [data_id],
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )


def create_set_view_program(
    *,
    center: list[float],
    zoom: float | int | None = None,
    name: str = "map view",
    turn_id: str | None = None,
) -> MapProgram:
    view = {"center": center}
    if zoom is not None:
        view["zoom"] = zoom

    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_set_view_{_slug(name)}",
        intent=f"Set map view to {name}",
        state={
            "view": view,
            "layers": [],
        },
        lineage={
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )


def create_dashboard_layer_program(
    *,
    layer_id: str,
    name: str,
    visible: bool = True,
    turn_id: str | None = None,
) -> MapProgram:
    return MapProgram(
        renderer="amap-compatible",
        program_id=f"mapprog_dashboard_layer_{_slug(layer_id)}",
        intent=f"Set dashboard layer {name} visibility",
        state={
            "view": {},
            "layers": [],
            "dashboard_layers": [{"id": layer_id, "visible": visible}],
        },
        lineage={
            "dashboard_layer_ids": [layer_id],
            **({"turn_id": turn_id} if turn_id else {}),
        },
    )
