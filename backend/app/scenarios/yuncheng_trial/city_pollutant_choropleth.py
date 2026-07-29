from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.utils.font_utils import apply_font_to_figure, chinese_font_prop


BOUNDARY_DIR = Path(__file__).resolve().parent / "city_boundaries"
BOUNDARY_FILES = {
    "运城市": "140800_yuncheng.geojson",
    "临汾市": "141000_linfen.geojson",
    "渭南市": "610500_weinan.geojson",
    "三门峡市": "411200_sanmenxia.geojson",
    "洛阳市": "410300_luoyang.geojson",
    "晋城市": "140500_jincheng.geojson",
}

FALLBACK_CITY_POLYGONS: dict[str, list[tuple[float, float]]] = {
    "渭南市": [(109.2, 34.25), (110.35, 34.25), (110.52, 35.0), (110.08, 35.45), (109.2, 35.22)],
    "三门峡市": [(110.42, 34.42), (111.48, 34.42), (111.58, 35.05), (111.08, 35.28), (110.48, 34.98)],
    "运城市": [(110.08, 34.92), (111.08, 34.82), (111.47, 35.16), (111.35, 35.75), (110.65, 35.85), (110.14, 35.45)],
    "洛阳市": [(111.48, 34.25), (112.9, 34.25), (113.02, 35.1), (111.62, 35.17)],
    "晋城市": [(111.62, 35.12), (112.98, 35.02), (113.03, 35.86), (111.84, 36.03), (111.42, 35.66)],
    "临汾市": [(110.52, 35.72), (111.78, 35.72), (111.95, 36.48), (110.75, 36.48), (110.42, 36.05)],
}

CITY_LABEL_POSITIONS: dict[str, tuple[float, float]] = {
    "渭南市": (109.82, 34.85),
    "三门峡市": (111.0, 34.78),
    "运城市": (110.78, 35.35),
    "洛阳市": (112.22, 34.68),
    "晋城市": (112.18, 35.56),
    "临汾市": (111.14, 36.1),
}

LEVEL_COLORS = {
    "优": "#00e400",
    "良": "#ffff00",
    "轻度污染": "#ff7e00",
    "中度污染": "#ff0000",
    "重度污染": "#99004c",
    "严重污染": "#7e0023",
    "无数据": "#d5d8dc",
}

POLLUTANT_THRESHOLDS: dict[str, list[tuple[float, str]]] = {
    "AQI": [(50, "优"), (100, "良"), (150, "轻度污染"), (200, "中度污染"), (300, "重度污染")],
    "PM2.5": [(35, "优"), (75, "良"), (115, "轻度污染"), (150, "中度污染"), (250, "重度污染")],
    "PM10": [(50, "优"), (150, "良"), (250, "轻度污染"), (350, "中度污染"), (420, "重度污染")],
    "O3": [(160, "优"), (200, "良"), (300, "轻度污染"), (400, "中度污染"), (800, "重度污染")],
    "NO2": [(100, "优"), (200, "良"), (700, "轻度污染"), (1200, "中度污染"), (2340, "重度污染")],
    "SO2": [(150, "优"), (500, "良"), (650, "轻度污染"), (800, "中度污染"), (1600, "重度污染")],
    "CO": [(5, "优"), (10, "良"), (35, "轻度污染"), (60, "中度污染"), (90, "重度污染")],
}


def render_city_pollutant_choropleth(
    *,
    target_payload: Any,
    nearby_payload: Any,
    pollutant: str,
    analysis_window: dict[str, Any],
    output_path: Path,
    interval_hours: int = 2,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Polygon

    rows = _extract_rows(target_payload) + _extract_rows(nearby_payload)
    start = _parse_time(str(analysis_window["start"]))
    end = _parse_time(str(analysis_window["end"]))
    values_by_time = _values_by_time_city(rows, pollutant)
    frame_times = _frame_times(start, end, interval_hours, available_times=set(values_by_time))
    city_shapes, label_positions = _load_city_boundaries()
    bounds = _shape_bounds(city_shapes)

    chinese_font = chinese_font_prop()
    _apply_matplotlib_fonts(plt, chinese_font)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = 2
    rows_count = max(1, (len(frame_times) + columns - 1) // columns)
    fig, axes = plt.subplots(rows_count, columns, figsize=(12.4, 4.6 * rows_count), dpi=170)
    axes_list = list(axes.flat) if hasattr(axes, "flat") else [axes]
    fig.patch.set_facecolor("white")

    for ax, frame_time in zip(axes_list, frame_times):
        _draw_frame(
            ax=ax,
            frame_time=frame_time,
            values=values_by_time.get(_format_time(frame_time), {}),
            pollutant=pollutant,
            city_shapes=city_shapes,
            label_positions=label_positions,
            bounds=bounds,
            chinese_font=chinese_font,
            Patch=Patch,
            Polygon=Polygon,
        )

    for ax in axes_list[len(frame_times):]:
        fig.delaxes(ax)

    fig.tight_layout(pad=1.0, h_pad=1.2, w_pad=1.0)
    apply_font_to_figure(fig)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return output_path


def _draw_frame(
    *,
    ax: Any,
    frame_time: datetime,
    values: dict[str, float],
    pollutant: str,
    city_shapes: dict[str, list[list[tuple[float, float]]]],
    label_positions: dict[str, tuple[float, float]],
    bounds: tuple[float, float, float, float],
    chinese_font: Any,
    Patch: Any,
    Polygon: Any,
) -> None:
    ax.set_facecolor("white")
    min_lon, min_lat, max_lon, max_lat = bounds
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)

    for city, rings in city_shapes.items():
        value = values.get(city)
        level = pollutant_level(pollutant, value)
        for ring in rings:
            ax.add_patch(
                Polygon(
                    ring,
                    closed=True,
                    facecolor=LEVEL_COLORS[level],
                    edgecolor="#3d9b3d",
                    linewidth=0.45,
                    alpha=0.9 if value is not None else 0.58,
                    zorder=3,
                )
            )
        label_lon, label_lat = label_positions[city]
        value_text = "-" if value is None else _format_value(value)
        ax.text(
            label_lon,
            label_lat,
            f"{city.replace('市', '')}\n{value_text}",
            ha="center",
            va="center",
            fontsize=7,
            color="#111111",
            fontproperties=chinese_font,
            zorder=5,
        )

    ax.set_title(f"{pollutant}空间分布图", fontsize=13, color="#333333", fontproperties=chinese_font, pad=12)
    ax.text(
        0,
        1.01,
        _format_frame_label(frame_time),
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color="#333333",
        fontweight="bold",
        fontproperties=chinese_font,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_color("#222222")
        spine.set_linewidth(0.7)

    _draw_scale_bar(ax=ax, bounds=bounds, chinese_font=chinese_font)
    _draw_north_arrow(ax=ax, chinese_font=chinese_font, Polygon=Polygon)
    _draw_legend(ax=ax, pollutant=pollutant, chinese_font=chinese_font, Patch=Patch)


def _load_city_boundaries() -> tuple[dict[str, list[list[tuple[float, float]]]], dict[str, tuple[float, float]]]:
    shapes: dict[str, list[list[tuple[float, float]]]] = {}
    labels: dict[str, tuple[float, float]] = {}

    for city, filename in BOUNDARY_FILES.items():
        path = BOUNDARY_DIR / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rings = _geojson_rings(payload)
        center = _geojson_center(payload)
        if rings:
            shapes[city] = rings
            labels[city] = CITY_LABEL_POSITIONS.get(city) or center or _ring_center(rings)

    if len(shapes) == len(BOUNDARY_FILES):
        return shapes, labels

    return {city: [polygon] for city, polygon in FALLBACK_CITY_POLYGONS.items()}, dict(CITY_LABEL_POSITIONS)


def _geojson_rings(payload: dict[str, Any]) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    features = payload.get("features") if isinstance(payload.get("features"), list) else []
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            continue
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geom_type == "Polygon" and isinstance(coordinates, list):
            _append_polygon_rings(rings, coordinates)
        elif geom_type == "MultiPolygon" and isinstance(coordinates, list):
            for polygon in coordinates:
                if isinstance(polygon, list):
                    _append_polygon_rings(rings, polygon)
    return rings


def _append_polygon_rings(rings: list[list[tuple[float, float]]], polygon_coordinates: list[Any]) -> None:
    if not polygon_coordinates:
        return
    exterior = polygon_coordinates[0]
    if not isinstance(exterior, list):
        return
    ring = [
        (float(point[0]), float(point[1]))
        for point in exterior
        if isinstance(point, list) and len(point) >= 2
    ]
    if len(ring) >= 3:
        rings.append(ring)


def _geojson_center(payload: dict[str, Any]) -> tuple[float, float] | None:
    features = payload.get("features") if isinstance(payload.get("features"), list) else []
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        center = properties.get("center") if isinstance(properties, dict) else None
        if isinstance(center, list) and len(center) >= 2:
            return float(center[0]), float(center[1])
    return None


def _ring_center(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    points = [point for ring in rings for point in ring]
    if not points:
        return 0.0, 0.0
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def _shape_bounds(city_shapes: dict[str, list[list[tuple[float, float]]]]) -> tuple[float, float, float, float]:
    points = [point for rings in city_shapes.values() for ring in rings for point in ring]
    if not points:
        return 109.05, 34.15, 113.08, 36.55
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    lon_pad = max((max(lons) - min(lons)) * 0.04, 0.05)
    lat_pad = max((max(lats) - min(lats)) * 0.04, 0.05)
    return min(lons) - lon_pad, min(lats) - lat_pad, max(lons) + lon_pad, max(lats) + lat_pad


def _draw_legend(*, ax: Any, pollutant: str, chinese_font: Any, Patch: Any) -> None:
    handles = [
        Patch(facecolor=color, edgecolor="#e0e0e0", linewidth=0.35, label=label)
        for color, label in zip(_legend_colors(), _legend_labels(pollutant), strict=True)
    ]
    legend = ax.legend(
        handles=handles,
        title=_pollutant_unit(pollutant),
        loc="lower right",
        frameon=True,
        fancybox=False,
        framealpha=0.95,
        borderpad=0.35,
        handlelength=1.2,
        handleheight=0.8,
        labelspacing=0.18,
        prop=chinese_font,
        fontsize=6.2,
        title_fontproperties=chinese_font,
    )
    legend.get_frame().set_edgecolor("#c7c7c7")
    legend.get_frame().set_linewidth(0.6)


def _legend_colors() -> list[str]:
    return [
        LEVEL_COLORS["优"],
        LEVEL_COLORS["良"],
        LEVEL_COLORS["轻度污染"],
        LEVEL_COLORS["中度污染"],
        LEVEL_COLORS["重度污染"],
        LEVEL_COLORS["严重污染"],
        LEVEL_COLORS["无数据"],
    ]


def _legend_labels(pollutant: str) -> list[str]:
    thresholds = [threshold for threshold, _level in POLLUTANT_THRESHOLDS.get(
        _normalize_pollutant(pollutant),
        POLLUTANT_THRESHOLDS["AQI"],
    )]
    labels = [f"0~{_format_threshold(thresholds[0])}"]
    labels.extend(
        f"{_format_threshold(previous)}~{_format_threshold(current)}"
        for previous, current in zip(thresholds, thresholds[1:], strict=False)
    )
    labels.append(f">{_format_threshold(thresholds[-1])}")
    labels.append("无数据")
    return labels


def _pollutant_unit(pollutant: str) -> str:
    normalized = _normalize_pollutant(pollutant)
    if normalized == "AQI":
        return "AQI"
    if normalized == "CO":
        return "mg/m3"
    return "ug/m3"


def _format_threshold(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _draw_scale_bar(*, ax: Any, bounds: tuple[float, float, float, float], chinese_font: Any) -> None:
    min_lon, min_lat, max_lon, max_lat = bounds
    center_lat = (min_lat + max_lat) / 2
    scale_km = _nice_scale_km((max_lon - min_lon) * 111.32 * math.cos(math.radians(center_lat)) * 0.18)
    scale_degrees = _scale_bar_degrees(scale_km, latitude=center_lat)
    x0 = min_lon + (max_lon - min_lon) * 0.035
    y0 = min_lat + (max_lat - min_lat) * 0.035
    tick_height = (max_lat - min_lat) * 0.035

    ax.plot([x0, x0 + scale_degrees], [y0, y0], color="black", linewidth=0.8, zorder=9)
    for offset in (0, scale_degrees / 2, scale_degrees):
        ax.plot([x0 + offset, x0 + offset], [y0, y0 + tick_height], color="black", linewidth=0.8, zorder=9)

    labels = ("0", str(scale_km // 2), f"{scale_km} km")
    for offset, label in zip((0, scale_degrees / 2, scale_degrees), labels, strict=True):
        ax.text(
            x0 + offset,
            y0 + tick_height * 1.25,
            label,
            ha="center",
            va="bottom",
            fontsize=6.8,
            color="black",
            fontproperties=chinese_font,
            zorder=10,
        )


def _nice_scale_km(target_km: float) -> int:
    for candidate in (5, 10, 20, 30, 50, 100):
        if target_km <= candidate:
            return candidate
    return 100


def _scale_bar_degrees(km: int | float, *, latitude: float) -> float:
    lon_km = 111.32 * max(math.cos(math.radians(latitude)), 0.1)
    return float(km) / lon_km


def _draw_north_arrow(*, ax: Any, chinese_font: Any, Polygon: Any) -> None:
    ax.text(
        0.948,
        0.956,
        "N",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=13,
        color="black",
        fontproperties=chinese_font,
        zorder=10,
    )
    arrow = Polygon(
        [(0.948, 0.92), (0.928, 0.855), (0.948, 0.875), (0.968, 0.855)],
        closed=True,
        transform=ax.transAxes,
        facecolor="black",
        edgecolor="black",
        linewidth=0.4,
        zorder=10,
    )
    ax.add_patch(arrow)


def pollutant_level(pollutant: str, value: float | None) -> str:
    if value is None:
        return "无数据"
    for threshold, level in POLLUTANT_THRESHOLDS.get(_normalize_pollutant(pollutant), POLLUTANT_THRESHOLDS["AQI"]):
        if value <= threshold:
            return level
    return "严重污染"


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "rows", "result", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _values_by_time_city(rows: list[dict[str, Any]], pollutant: str) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for row in rows:
        city = _normalize_city(row.get("city") or row.get("city_name") or row.get("Area") or row.get("area"))
        time_text = _normalize_time(row.get("time") or row.get("TimePoint") or row.get("timestamp"))
        value = _pollutant_value(row, pollutant)
        if city and time_text and value is not None:
            values.setdefault(time_text, {})[city] = value
    return values


def _pollutant_value(row: dict[str, Any], pollutant: str) -> float | None:
    measurements = row.get("measurements") if isinstance(row.get("measurements"), dict) else {}
    aliases = _pollutant_aliases(pollutant)
    for alias in aliases:
        value = _to_float(row.get(alias))
        if value is not None:
            return value
        value = _to_float(measurements.get(alias))
        if value is not None:
            return value
    return None


def _pollutant_aliases(pollutant: str) -> tuple[str, ...]:
    normalized = _normalize_pollutant(pollutant)
    aliases = {
        "PM2.5": ("PM2.5", "PM2_5", "pm2_5", "pm25"),
        "PM10": ("PM10", "pm10"),
        "O3": ("O3", "O3_8h", "o3", "o3_8h"),
        "NO2": ("NO2", "no2"),
        "SO2": ("SO2", "so2"),
        "CO": ("CO", "co"),
        "AQI": ("AQI", "aqi"),
    }
    return aliases.get(normalized, (pollutant,))


def _normalize_pollutant(value: str) -> str:
    normalized = str(value or "").strip().upper().replace("PM₂.₅", "PM2.5").replace("_", "")
    if normalized in {"PM25", "PM2.5"}:
        return "PM2.5"
    return normalized


def _normalize_city(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if text.endswith("市") else f"{text}市"


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _normalize_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return _format_time(value)
    text = str(value or "").strip()
    if not text:
        return None
    return _format_time(_parse_time(text))


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_frame_label(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _frame_times(start: datetime, end: datetime, interval_hours: int, available_times: set[str] | None = None) -> list[datetime]:
    frames: list[datetime] = []
    current = start
    step = timedelta(hours=max(1, interval_hours))
    while current <= end:
        if available_times is None or _format_time(current) in available_times:
            frames.append(current)
        current += step
    if available_times is None and frames and frames[-1] != end:
        frames.append(end)
    return frames


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_value(value: float) -> str:
    if abs(value) >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _apply_matplotlib_fonts(plt: Any, font_prop: Any) -> None:
    family = font_prop.get_name() if font_prop is not None else "Droid Sans Fallback"
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [family, "Noto Sans CJK SC", "Droid Sans Fallback", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
