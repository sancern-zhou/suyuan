"""Static Xuchang district pollution/AQI map renderer for report images."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from app.tools.visualization.create_business_chart.domain.henan_city_map import (
    COLORS,
    LEVEL_LABELS,
    LEVELS,
    NEW_STANDARD_CONCENTRATION_BREAKS,
    _color_index,
    _metric_key,
    _value,
)
from app.tools.visualization.create_business_chart.text import normalize_matplotlib_label_text
from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

DEFAULT_BOUNDARY_ASSET = Path(__file__).resolve().parents[1] / "assets" / "xuchang_district_boundaries.geojson"

# 6 个官方行政区：与边界资产 properties.name/adcode 一一对应。
OFFICIAL_DISTRICTS = {
    "魏都区": 411002,
    "建安区": 411003,
    "鄢陵县": 411024,
    "襄城县": 411025,
    "禹州市": 411081,
    "长葛市": 411082,
}
# 3 个功能区无官方行政边界（DataV 411000_full 仅含 6 官方区县），
# 按站点目录（tools/xuchang/station_catalog 的 office/township 坐标）
# 以站点标示，不画边界线。
FUNCTIONAL_ZONE_STATIONS = {
    "东城区": (
        ("半截河街道办事处", 113.845149, 34.023483),
        ("邓庄街道办事处", 113.916100, 34.022300),
        ("天宝街道办事处", 113.855260, 34.044667),
        ("祖师街道办事处", 113.907350, 33.966720),
        ("永昌街道办事处", 113.922025, 34.059214),
    ),
    "开发区": (
        ("龙湖街道办事处", 113.798000, 33.998009),
        ("长村张街道办事处", 113.782300, 33.983330),
    ),
    "示范区": (
        ("尚集镇", 113.854800, 34.085700),
    ),
}
SUPPORTED_DISTRICTS = frozenset(OFFICIAL_DISTRICTS) | frozenset(FUNCTIONAL_ZONE_STATIONS)
DISTRICT_ALIASES = {
    "经济技术开发区": "开发区",
    "许昌经济技术开发区": "开发区",
    "城乡一体化示范区": "示范区",
    "许昌市城乡一体化示范区": "示范区",
}
NO_DATA_FACECOLOR = "#f1f5f9"
NO_DATA_EDGECOLOR = "#94a3b8"
BOUNDARY_EDGECOLOR = "#475569"
FOOTNOTE_TEXT = "东城区/开发区/示范区为功能区，无行政边界，按站点目录以站点标示。"


def _suffix_names() -> dict[str, str]:
    return {name[:-1]: name for name in SUPPORTED_DISTRICTS if name.endswith(("市", "县", "区"))}


def _district_key(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "").replace("　", "")
    if not text:
        return ""
    if text.startswith("许昌市"):
        text = text[len("许昌市"):]
    if text in SUPPORTED_DISTRICTS:
        return text
    if text in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[text]
    return _suffix_names().get(text, "")


def _district_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    records = data.get("records")
    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)]
    values = data.get("values") or data.get("aqi")
    names = data.get("districts") or data.get("names") or data.get("cities") or data.get("labels")
    if isinstance(values, list) and isinstance(names, list):
        return [
            {"district": name, "value": value}
            for name, value in zip(names, values, strict=False)
        ]
    return []


def render_xuchang_district_map(
    title: str, data: dict[str, Any], options: dict[str, Any], output_context: str
) -> tuple[str, dict[str, Any], list[str]]:
    configure_chinese_font()
    metric = str(data.get("metric") or options.get("metric") or "AQI")
    records = _district_records(data)
    values: dict[str, float] = {}
    unmatched: list[str] = []
    for record in records:
        raw_name = (
            record.get("district")
            or record.get("district_name")
            or record.get("name")
            or record.get("city")
            or record.get("region")
        )
        district = _district_key(raw_name)
        value = _value(record, metric)
        if not district:
            if raw_name or value is not None:
                unmatched.append(str(raw_name or "").strip())
            continue
        if value is not None:
            values[district] = value
    if not values:
        raise ValueError("xuchang_district_map 需要 records[{district,value}]（或 districts+values），并包含可解析的区县数值。")

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
            raise ValueError(f"许昌区县边界资产不存在：{DEFAULT_BOUNDARY_ASSET}")
        geojson = json.loads(DEFAULT_BOUNDARY_ASSET.read_text(encoding="utf-8"))
        asset_source = str(DEFAULT_BOUNDARY_ASSET)

    rendered_polygons = 0
    rendered_coordinates: list[tuple[float, float]] = []
    centroids: dict[str, tuple[float, float]] = {}
    if isinstance(geojson, dict):
        for feature in geojson.get("features", []):
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            district = _district_key(props.get("name") or props.get("city"))
            adcode = props.get("adcode")
            if not district and adcode is not None:
                district = next(
                    (name for name, code in OFFICIAL_DISTRICTS.items() if str(code) == str(adcode)),
                    "",
                )
            if not district or district not in OFFICIAL_DISTRICTS:
                continue
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates")
            if geometry.get("type") == "MultiPolygon":
                rings = [polygon[0] for polygon in coordinates if polygon]
            elif geometry.get("type") == "Polygon":
                rings = [coordinates[0]] if coordinates and coordinates[0] else []
            else:
                rings = []
            centroid = props.get("centroid")
            if isinstance(centroid, (list, tuple)) and len(centroid) >= 2:
                centroids[district] = (float(centroid[0]), float(centroid[1]))
            value = values.get(district)
            facecolor = COLORS[_color_index(value, breaks)] if value is not None else NO_DATA_FACECOLOR
            edgecolor = BOUNDARY_EDGECOLOR if value is not None else NO_DATA_EDGECOLOR
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
                            facecolor=facecolor,
                            edgecolor=edgecolor,
                            linewidth=0.65,
                            linestyle="-" if value is not None else "--",
                        )
                    )
                    rendered_polygons += 1
            if district not in centroids and rings:
                points = [point for ring in rings for point in ring if isinstance(point, (list, tuple))]
                if points:
                    centroids[district] = (
                        sum(float(point[0]) for point in points) / len(points),
                        sum(float(point[1]) for point in points) / len(points),
                    )

    if rendered_polygons == 0:
        plt.close(fig)
        raise ValueError("许昌区县 GeoJSON 中没有与输入区县匹配的可渲染行政区要素。")

    station_coordinates: list[tuple[float, float]] = []
    station_names: dict[str, list[str]] = {}
    zone_centers: dict[str, tuple[float, float]] = {}
    plotted_stations = 0
    for zone, stations in FUNCTIONAL_ZONE_STATIONS.items():
        value = values.get(zone)
        if value is None:
            continue
        color = COLORS[_color_index(value, breaks)]
        points = [(lon, lat) for _, lon, lat in stations]
        station_coordinates.extend(points)
        station_names[zone] = [name for name, _, _ in stations]
        zone_centers[zone] = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
        for name, lon, lat in stations:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=5.5,
                markerfacecolor=color,
                markeredgecolor="white",
                markeredgewidth=0.8,
                linestyle="",
                zorder=4,
            )
            plotted_stations += 1

    for district, value in values.items():
        if district in FUNCTIONAL_ZONE_STATIONS:
            continue
        lonlat = centroids.get(district)
        if lonlat:
            ax.text(
                lonlat[0], lonlat[1], f"{district}\n{value:g}", ha="center", va="center",
                fontsize=7.2, color="#111827", zorder=5,
            )
    for zone, center in zone_centers.items():
        value = values[zone]
        ax.text(
            center[0], center[1], f"{zone}\n{value:g}", ha="center", va="center",
            fontsize=7.0, color="#111827", zorder=6,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1.2},
        )

    all_points = rendered_coordinates + station_coordinates
    if not all_points:
        plt.close(fig)
        raise ValueError("没有可渲染的区县边界或站点坐标。")
    min_lon = min(point[0] for point in all_points)
    max_lon = max(point[0] for point in all_points)
    min_lat = min(point[1] for point in all_points)
    max_lat = max(point[1] for point in all_points)
    lon_padding = max(0.08, (max_lon - min_lon) * 0.035)
    lat_padding = max(0.08, (max_lat - min_lat) * 0.035)
    ax.set_xlim(min_lon - lon_padding, max_lon + lon_padding)
    ax.set_ylim(min_lat - lat_padding, max_lat + lat_padding)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title(str(normalize_matplotlib_label_text(title)), fontsize=15, pad=10)

    handles = [
        plt.Line2D(
            [0], [0], marker="s", linestyle="", markerfacecolor=color,
            markeredgecolor="#64748b", markersize=9, label=label,
        )
        for color, label in zip(COLORS, LEVEL_LABELS, strict=True)
    ]
    handles.append(
        plt.Line2D(
            [0], [0], marker="o", linestyle="", markerfacecolor="#9ca3af",
            markeredgecolor="white", markersize=7,
            label="功能区站点（按值着色）",
        )
    )
    legend_title = "AQI 分级" if metric_key == "AQI" else f"{metric} 浓度分级"
    legend_title = str(normalize_matplotlib_label_text(legend_title))
    ax.legend(handles=handles, loc="lower left", ncol=2, frameon=False, fontsize=7.5, title=legend_title)
    if options.get("show_footnote", True):
        ax.text(
            0.995, 0.005, FOOTNOTE_TEXT,
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=6.3, color="#64748b",
        )
    apply_font_to_figure(fig)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    metadata = {
        "metric": metric,
        "metric_key": metric_key,
        "official_district_count": len([d for d in values if d in OFFICIAL_DISTRICTS]),
        "functional_zone_count": len([d for d in values if d in FUNCTIONAL_ZONE_STATIONS]),
        "station_count": plotted_stations,
        "rendered_polygon_count": rendered_polygons,
        "boundary_asset": asset_source,
        "breaks": breaks,
        "classification_basis": classification_basis,
        "level_labels": list(LEVEL_LABELS),
        "unmatched_districts": unmatched,
        "functional_zone_stations": station_names,
        "scope": "xuchang_districts",
    }
    warnings: list[str] = []
    if unmatched:
        warnings.append("以下区县名称未匹配到许昌 9 区县口径，已忽略：" + "、".join(unmatched))
    missing_officials = [name for name in OFFICIAL_DISTRICTS if name not in values]
    missing_zones = [name for name in FUNCTIONAL_ZONE_STATIONS if name not in values]
    if missing_officials:
        warnings.append("未提供数值的区县按无数据描边显示：" + "、".join(missing_officials))
    if missing_zones:
        warnings.append("未提供数值的功能区不绘制站点标示：" + "、".join(missing_zones))
    return base64.b64encode(buffer.getvalue()).decode("ascii"), metadata, warnings
