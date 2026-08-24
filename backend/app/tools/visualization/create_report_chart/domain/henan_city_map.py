"""Static Henan city pollution/AQI map renderer for report images."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

HENAN_CITY_CENTERS = {
    "郑州": (113.62, 34.75), "开封": (114.34, 34.80), "洛阳": (112.45, 34.62),
    "平顶山": (113.30, 33.74), "安阳": (114.39, 36.10), "鹤壁": (114.30, 35.75),
    "新乡": (113.90, 35.30), "焦作": (113.24, 35.22), "濮阳": (115.03, 35.76),
    "许昌": (113.85, 34.04), "漯河": (114.02, 33.58), "三门峡": (111.20, 34.78),
    "南阳": (112.53, 32.99), "商丘": (115.65, 34.44), "信阳": (114.09, 32.15),
    "周口": (114.70, 33.63), "驻马店": (114.02, 32.98), "济源": (112.59, 35.09),
}
DEFAULT_BOUNDARY_ASSET = Path(__file__).resolve().parents[1] / "assets" / "henan_city_boundaries.geojson"
COLORS = ["#10b981", "#f2e600", "#f59e0b", "#ef4444", "#7c3aed", "#991b1b"]
LEVELS = (50, 100, 150, 200, 300)
# HJ 633-2026 concentration breakpoints at IAQI 50/100/150/200/300.
# CO is mg/m3; the other pollutants are ug/m3. AQI itself uses LEVELS above.
NEW_STANDARD_CONCENTRATION_BREAKS = {
    "PM2_5": (35, 60, 115, 150, 250),
    "PM10": (50, 120, 250, 350, 420),
    "SO2": (50, 150, 475, 800, 1600),
    "NO2": (40, 80, 180, 280, 565),
    "CO": (2, 4, 14, 24, 36),
    "O3_8h": (100, 160, 215, 265, 800),
}
LEVEL_LABELS = ("优", "良", "轻度", "中度", "重度", "严重")


def _city_key(value: Any) -> str:
    return str(value or "").strip().replace("市", "")


def _records(data: dict[str, Any]) -> list[dict[str, Any]]:
    records = data.get("records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    values = data.get("values") or data.get("aqi")
    cities = data.get("cities") or data.get("labels")
    if isinstance(values, list) and isinstance(cities, list):
        return [
            {"city": city, "value": value}
            for city, value in zip(cities, values, strict=False)
        ]
    return []


def _value(record: dict[str, Any], metric: str) -> float | None:
    candidates = [metric, metric.replace(".", "_"), metric.lower(), metric.upper(), "value", "浓度", "AQI", "aqi"]
    for key in candidates:
        try:
            value = record.get(key)
            if value is not None and str(value).strip() != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _color_index(value: float, breaks: list[float]) -> int:
    for index, threshold in enumerate(breaks):
        if value <= threshold:
            return index
    return len(breaks)


def _metric_key(metric: str) -> str:
    normalized = str(metric or "AQI").strip().upper().replace(".", "_")
    aliases = {
        "PM2_5": "PM2_5",
        "PM25": "PM2_5",
        "PM10": "PM10",
        "O3": "O3_8h",
        "O3_8H": "O3_8h",
        "O3_8H_24H": "O3_8h",
        "臭氧": "O3_8h",
        "二氧化硫": "SO2",
        "二氧化氮": "NO2",
        "一氧化碳": "CO",
    }
    return aliases.get(normalized, normalized)


def render_henan_city_map(
    title: str, data: dict[str, Any], options: dict[str, Any], output_context: str
) -> tuple[str, dict[str, Any], list[str]]:
    configure_chinese_font()
    metric = str(data.get("metric") or options.get("metric") or "AQI")
    records = _records(data)
    values: dict[str, float] = {}
    for record in records:
        city = _city_key(record.get("city") or record.get("city_name") or record.get("name"))
        value = _value(record, metric)
        if city and value is not None:
            values[city] = value
    if not values:
        raise ValueError("henan_city_map 需要 records 或 cities+values，并包含可解析的城市数值。")

    metric_key = _metric_key(metric)
    raw_breaks = options.get("breaks") or data.get("breaks")
    if not raw_breaks and metric_key != "AQI" and metric_key not in NEW_STANDARD_CONCENTRATION_BREAKS:
        raise ValueError(f"不支持的污染物指标：{metric}，请提供 options.breaks。")
    try:
        if raw_breaks:
            breaks = [float(x) for x in raw_breaks]
            classification_basis = "custom"
        elif metric_key == "AQI":
            breaks = list(LEVELS)
            classification_basis = "AQI"
        elif metric_key in NEW_STANDARD_CONCENTRATION_BREAKS:
            breaks = list(NEW_STANDARD_CONCENTRATION_BREAKS[metric_key])
            classification_basis = "HJ 633-2026 concentration breakpoints"
    except (TypeError, ValueError):
        raise ValueError("breaks 必须是数字数组。") from None
    if sorted(breaks) != breaks or len(breaks) != 5:
        raise ValueError("breaks 必须包含 5 个递增阈值。")

    fig, ax = plt.subplots(figsize=(8.2, 5.2) if output_context == "word" else (9.5, 5.8))
    ax.set_facecolor("#f8fafc")
    geojson = data.get("geojson") or options.get("geojson")
    asset_source = "inline_geojson"
    if geojson is None:
        if not DEFAULT_BOUNDARY_ASSET.exists():
            raise ValueError(f"河南省城市边界资产不存在：{DEFAULT_BOUNDARY_ASSET}")
        geojson = json.loads(DEFAULT_BOUNDARY_ASSET.read_text(encoding="utf-8"))
        asset_source = str(DEFAULT_BOUNDARY_ASSET)
    rendered_polygons = 0
    rendered_coordinates: list[tuple[float, float]] = []
    if isinstance(geojson, dict):
        for feature in geojson.get("features", []):
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            city = _city_key(props.get("city") or props.get("name") or props.get("市名"))
            value = values.get(city)
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates")
            if value is None or not coordinates:
                continue
            if geometry.get("type") == "MultiPolygon":
                rings = [polygon[0] for polygon in coordinates if polygon]
            else:
                rings = [coordinates[0]] if coordinates and coordinates[0] else []
            for ring in rings:
                if ring and isinstance(ring[0], (list, tuple)):
                    rendered_coordinates.extend(
                        (float(point[0]), float(point[1]))
                        for point in ring
                        if len(point) >= 2
                    )
                    ax.add_patch(
                        MplPolygon(
                            ring,
                            closed=True,
                            facecolor=COLORS[_color_index(value, breaks)],
                            edgecolor="#475569",
                            linewidth=0.65,
                        )
                    )
                    rendered_polygons += 1

    if rendered_polygons == 0:
        plt.close(fig)
        raise ValueError("河南省 GeoJSON 中没有与输入城市匹配的可渲染行政区要素。")

    for city, value in values.items():
        lonlat = HENAN_CITY_CENTERS.get(city)
        if lonlat:
            ax.text(
                lonlat[0], lonlat[1], f"{city}\n{value:g}", ha="center", va="center",
                fontsize=7.2, color="#111827", zorder=5,
            )
    ax.set_title(str(normalize_matplotlib_label_text(title)), fontsize=15, pad=10)
    min_lon = min(point[0] for point in rendered_coordinates)
    max_lon = max(point[0] for point in rendered_coordinates)
    min_lat = min(point[1] for point in rendered_coordinates)
    max_lat = max(point[1] for point in rendered_coordinates)
    lon_padding = max(0.12, (max_lon - min_lon) * 0.035)
    lat_padding = max(0.12, (max_lat - min_lat) * 0.035)
    ax.set_xlim(min_lon - lon_padding, max_lon + lon_padding)
    ax.set_ylim(min_lat - lat_padding, max_lat + lat_padding)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    handles = [
        plt.Line2D(
            [0], [0], marker="s", linestyle="", markerfacecolor=color,
            markeredgecolor="#64748b", markersize=9, label=label,
        )
        for color, label in zip(COLORS, LEVEL_LABELS, strict=True)
    ]
    legend_title = "AQI 分级" if metric_key == "AQI" else f"{metric} 浓度分级"
    legend_title = str(normalize_matplotlib_label_text(legend_title))
    ax.legend(handles=handles, loc="lower left", ncol=3, frameon=False, fontsize=8, title=legend_title)
    apply_font_to_figure(fig)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    metadata = {
        "metric": metric,
        "metric_key": metric_key,
        "city_count": len(values),
        "rendered_polygon_count": rendered_polygons,
        "boundary_asset": asset_source,
        "breaks": breaks,
        "classification_basis": classification_basis,
        "level_labels": list(LEVEL_LABELS),
        "scope": "henan_province",
    }
    return base64.b64encode(buffer.getvalue()).decode("ascii"), metadata, []
