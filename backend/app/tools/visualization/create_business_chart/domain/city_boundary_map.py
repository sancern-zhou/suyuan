"""Generic China city-level boundary choropleth renderer (chart_type: city_boundary_map).

全国任意城市集合的行政区填色地图：按 adcode/城市名匹配全国边界资产，视野随数据
自适应。与 henan_city_map（河南专用、手写坐标表）方法同源，但不依赖它——本模块
自包含分级/配色常量，可在无河南模块的环境（如 main 分支）独立工作。
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch, Polygon as MplPolygon
from matplotlib.path import Path as MplPath

from app.tools.visualization.create_business_chart.text import normalize_matplotlib_label_text
from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

DEFAULT_BOUNDARY_ASSET = Path(__file__).resolve().parents[1] / "assets" / "china_city_boundaries.geojson"
COLORS = ["#10b981", "#f2e600", "#f59e0b", "#ef4444", "#7c3aed", "#991b1b"]
LEVELS = (50, 100, 150, 200, 300)
# HJ 633-2026 concentration breakpoints at IAQI 50/100/150/200/300.
# CO is mg/m3; the other pollutants are ug/m3. AQI itself uses LEVELS above.
CONCENTRATION_BREAKS = {
    "PM2_5": (35, 60, 115, 150, 250),
    "PM10": (50, 120, 250, 350, 420),
    "SO2": (50, 150, 475, 800, 1600),
    "NO2": (40, 80, 180, 280, 565),
    "CO": (2, 4, 14, 24, 36),
    "O3_8h": (100, 160, 215, 265, 800),
}
LEVEL_LABELS = ("优", "良", "轻度", "中度", "重度", "严重")
GROUP_PRIMARY_EDGE = "#111827"
GROUP_PRIMARY_WIDTH = 1.4
GROUP_SECONDARY_EDGE = "#475569"
GROUP_SECONDARY_WIDTH = 0.65

# 可选 IDW 插值示意模式（render_mode="idw"）：城市点反距离加权插值的默认参数与底线。
IDW_POWER = 2.0
IDW_GRID_STEPS = 520
IDW_MIN_POINTS = 8
IDW_ROW_CHUNK = 64  # 分块插值，控制峰值内存
IDW_DOT_MIN_GAP_DEG = 0.25  # 相邻采样点最小间距（度）：密邻城市省略点，避免与相邻标签挤占混淆
# 插值面裁剪口径：cities=仅目标(数据)城市并集，目标范围外留白（默认，防止外推色被误读为无数据城市有值）；
# land=视野内全部陆地沿海岸线连续铺满（参考主流 AQI 分布图观感，外推语义靠注记声明）。
IDW_CLIP_MODES = ("cities", "land")


def _city_key(value: Any) -> str:
    """城市名归一化：去首尾空白与尾部"市"（行政区数据口径与数据源列名的桥）。"""
    text = str(value or "").strip()
    return text[:-1] if text.endswith("市") and len(text) > 1 else text


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


def _color_index(value: float, breaks: list[float]) -> int:
    for index, threshold in enumerate(breaks):
        if value <= threshold:
            return index
    return len(breaks)


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


def _record_value(record: dict[str, Any], metric: str) -> float | None:
    candidates = [
        metric, metric.replace(".", "_"), metric.lower(), metric.upper(),
        "value", "浓度", "AQI", "aqi",
    ]
    for key in candidates:
        try:
            value = record.get(key)
            if value is not None and str(value).strip() != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _record_adcode(record: dict[str, Any]) -> int | None:
    raw = record.get("adcode")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _numeric_field(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            value = record.get(key)
            if value is not None and str(value).strip() != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _record_seed_value(
    record: dict[str, Any], metric: str, value_mode: str
) -> tuple[float | None, bool]:
    """解析参与渲染的数值；value_mode="mid" 时优先取区间 min~max 中值。

    返回 (数值, 是否取自中值)。区间字段缺失时回退到常规数值解析（计入回退）。
    """
    if value_mode == "mid":
        low = _numeric_field(record, ("min", "min_value", "value_min"))
        high = _numeric_field(record, ("max", "max_value", "value_max"))
        if low is not None and high is not None:
            return (low + high) / 2.0, True
    return _record_value(record, metric), False


def _resolve_breaks(data: dict[str, Any], options: dict[str, Any], metric_key: str) -> tuple[list[float], str]:
    raw_breaks = options.get("breaks") or data.get("breaks")
    try:
        if raw_breaks:
            breaks = [float(x) for x in raw_breaks]
            if sorted(breaks) != breaks or len(breaks) != 5:
                raise ValueError("breaks 必须包含 5 个递增阈值。")
            return breaks, "custom"
        if metric_key == "AQI":
            return list(LEVELS), "AQI"
        if metric_key in CONCENTRATION_BREAKS:
            return list(CONCENTRATION_BREAKS[metric_key]), "HJ 633-2026 concentration breakpoints"
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and "递增" in str(exc):
            raise
        raise ValueError("breaks 必须是数字数组。") from None
    raise ValueError(f"不支持的污染物指标：{metric_key}，请提供 options.breaks（5 个递增阈值）。")


def _boundary_feature_collections(
    data: dict[str, Any], options: dict[str, Any]
) -> tuple[dict[int, dict], dict[str, dict], str, list[dict]]:
    """返回 (adcode索引, 城市名索引, 资产来源描述, 全部要素列表)。"""
    geojson = data.get("geojson") or options.get("geojson")
    if isinstance(geojson, dict):
        source = "inline_geojson"
        features = [
            f for f in geojson.get("features", []) if isinstance(f, dict)
        ]
    else:
        if not DEFAULT_BOUNDARY_ASSET.exists():
            raise ValueError(f"全国城市边界资产不存在：{DEFAULT_BOUNDARY_ASSET}")
        source = str(DEFAULT_BOUNDARY_ASSET)
        features = json.loads(DEFAULT_BOUNDARY_ASSET.read_text(encoding="utf-8")).get("features", [])
    by_adcode: dict[int, dict] = {}
    by_name: dict[str, dict] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        if feature.get("geometry") and feature["geometry"].get("coordinates"):
            try:
                by_adcode[int(props.get("adcode"))] = feature
            except (TypeError, ValueError):
                pass
            name_key = _city_key(props.get("name"))
            if name_key and name_key not in by_name:
                by_name[name_key] = feature
    return by_adcode, by_name, source, features


def _feature_rings(feature: dict) -> list:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    if geometry.get("type") == "Polygon":
        return [coordinates[0]] if coordinates and coordinates[0] else []
    return []


def _group_order(records: list[dict[str, Any]], options: dict[str, Any]) -> list[str]:
    """分组顺序：options.group_order 优先，其余按首次出现顺序排在后面。"""
    seen: list[str] = []
    for record in records:
        group = str(record.get("group") or "").strip()
        if group and group not in seen:
            seen.append(group)
    specified = options.get("group_order")
    if isinstance(specified, list):
        ordered = [str(g) for g in specified if str(g) in seen]
        ordered += [g for g in seen if g not in ordered]
        return ordered
    return seen


def _estimate_label_size(
    text: str, fontsize: float, inch_per_lon: float, inch_per_lat: float
) -> tuple[float, float]:
    """按字符宽度估算标签占用的经纬度尺寸（中文全角 1.0、半角 0.55 字宽）。"""
    lines = text.split("\n")
    width_chars = max(sum(1.0 if ord(ch) > 127 else 0.55 for ch in line) for line in lines)
    width_in = width_chars * fontsize / 72.0
    height_in = len(lines) * fontsize / 72.0 * 1.4
    return width_in / max(inch_per_lon, 1e-9), height_in / max(inch_per_lat, 1e-9)


def _resolve_label_overlaps(
    labels: list[tuple[float, float, str, bool]],
    city_boxes: list[tuple[float, float, float, float]],
    fig_width: float,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    raise_above_anchor: bool = False,
) -> tuple[list[tuple[float, float, str, bool]], int, int]:
    """贪心标签避让：冲突时优先在城市自身 bbox 内做上下位移，位移不出去则保持原位。

    raise_above_anchor=True（IDW 插值模式）时文字整体抬到采样点上方，露出采样圆点。
    返回 (调整后标签, 位移数, 未能避让数)。bbox 约束保证标签不会被推出所属城市。
    """
    if not labels:
        return labels, 0, 0
    axes_width_in = fig_width * 0.82
    lon_span = max(xlim[1] - xlim[0], 1e-9)
    lat_span = max(ylim[1] - ylim[0], 1e-9)
    axes_height_in = axes_width_in * lat_span / lon_span  # 等比投影
    inch_per_lon = axes_width_in / lon_span
    inch_per_lat = axes_height_in / lat_span

    placed: list[tuple[float, float, float, float]] = []
    result: list[tuple[float, float, str, bool]] = []
    displaced = 0
    unplaced = 0

    def _conflicts(box: tuple[float, float, float, float]) -> bool:
        return any(
            not (box[2] <= other[0] or box[0] >= other[2]
                 or box[3] <= other[1] or box[1] >= other[3])
            for other in placed
        )

    for (lon, lat, text, is_primary), (min_lon, max_lon, min_lat, max_lat) in zip(labels, city_boxes):
        fontsize = 7.0 if is_primary else 6.8
        width, height = _estimate_label_size(text, fontsize, inch_per_lon, inch_per_lat)
        box_bottom = lat - height / 2 if not raise_above_anchor else lat
        box = (lon - width / 2, box_bottom, lon + width / 2, box_bottom + height)
        if _conflicts(box):
            moved = False
            # 优先向下（下邻多为视野边缘），再向上，再半步微调。
            for dy in (-height, height, -height * 0.55, height * 0.55):
                candidate = (box[0], box[1] + dy, box[2], box[3] + dy)
                within_city = (
                    candidate[0] >= min_lon - 0.04 and candidate[2] <= max_lon + 0.04
                    and candidate[1] >= min_lat - 0.04 and candidate[3] <= max_lat + 0.04
                )
                if within_city and not _conflicts(candidate):
                    box = candidate
                    displaced += 1
                    moved = True
                    break
            if not moved:
                unplaced += 1
        placed.append(box)
        result.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, text, is_primary))
    return result, displaced, unplaced


def _level_color_anchors(breaks: list[float]) -> list[float]:
    """六级色锚点值：各档中值 + 顶档外推值（AQI → [25, 75, 125, 175, 250, 400]）。

    连续色映射用：等级色作为控制点锚在这些代表值上，档间线性过渡。
    """
    values = [breaks[0] / 2.0]
    for index in range(1, len(breaks)):
        values.append((breaks[index - 1] + breaks[index]) / 2.0)
    values.append(breaks[-1] + (breaks[-1] - breaks[-2]) / 2.0)
    return values


def _continuous_level_colors(zi: "np.ndarray", anchors: list[float]) -> "np.ndarray":
    """插值场 → 连续 RGB：六级 HJ 633 色作锚点、档间线性插值（np.interp 端外截断）。"""
    anchor_arr = np.asarray(anchors, dtype=float)
    rgb = np.empty(zi.shape + (3,), dtype=float)
    for channel in range(3):
        control = np.array([to_rgb(color)[channel] for color in COLORS], dtype=float)
        rgb[..., channel] = np.interp(zi, anchor_arr, control)
    return rgb


def _paint_idw_surface(
    ax: plt.Axes,
    collected: list[dict[str, Any]],
    breaks: list[float],
    extent: tuple[float, float, float, float],
    all_features: list[dict[str, Any]] | None = None,
    clip_mode: str = "land",
) -> tuple[int, int]:
    """IDW 插值示意面：城市点反距离加权插值 → 六级色锚点连续色带 → 陆地/城市并集裁剪。

    clip_mode="land"（默认）时插值面铺满视野内全部陆地、沿海岸线精确裁剪（参考主流
    AQI 分布图观感）；"cities" 时仅数据城市多边形并集内着色。城市之间均为连续过渡。
    数据面颜色仅为示意，不得当作模式网格或实测场引用（图内带角标）。
    密邻城市（间距 < IDW_DOT_MIN_GAP_DEG）省略采样点。
    返回 (参与裁剪的边界环数, 省略的采样点数)。
    """
    min_lon, max_lon, min_lat, max_lat = extent
    lon_span = max(max_lon - min_lon, 1e-9)
    lat_span = max(max_lat - min_lat, 1e-9)
    grid_nx = IDW_GRID_STEPS
    grid_ny = max(24, int(grid_nx * lat_span / lon_span))
    grid_x, grid_y = np.meshgrid(
        np.linspace(min_lon, max_lon, grid_nx),
        np.linspace(min_lat, max_lat, grid_ny),
    )
    sample_lon = np.array([entry["anchor"][0] for entry in collected], dtype=float)
    sample_lat = np.array([entry["anchor"][1] for entry in collected], dtype=float)
    sample_val = np.array([entry["value"] for entry in collected], dtype=float)
    sample_val32 = sample_val.astype(np.float32)

    zi = np.empty(grid_x.shape, dtype=np.float32)
    inside = np.zeros(grid_x.shape, dtype=bool)
    grid_flat = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    if clip_mode == "land" and all_features:
        # 陆地裁剪：视野内全部城市边界（含无数据城市），插值面沿海岸线连续铺满。
        clip_rings: list = []
        for feature in all_features:
            for ring in _feature_rings(feature):
                pts = np.asarray(ring, dtype=float)
                if pts.ndim != 2 or len(pts) < 4:
                    continue
                if (pts[:, 0].max() < min_lon or pts[:, 0].min() > max_lon
                        or pts[:, 1].max() < min_lat or pts[:, 1].min() > max_lat):
                    continue
                clip_rings.append(ring)
    else:
        clip_rings = [
            ring for entry in collected for ring in entry["rings"]
            if ring and isinstance(ring[0], (list, tuple))
        ]
    for start in range(0, grid_ny, IDW_ROW_CHUNK):
        stop = min(start + IDW_ROW_CHUNK, grid_ny)
        dx = grid_x[start:stop][..., None] - sample_lon
        dy = grid_y[start:stop][..., None] - sample_lat
        d2 = (dx * dx + dy * dy).astype(np.float32)
        exact = d2 < np.float32(1e-12)
        weights = np.float32(1.0) / np.maximum(d2, np.float32(1e-12)) ** np.float32(IDW_POWER / 2.0)
        block = (weights * sample_val32).sum(axis=-1) / weights.sum(axis=-1)
        exact_hit = exact.any(axis=-1)
        if exact_hit.any():
            block[exact_hit] = sample_val32[exact.argmax(axis=-1)[exact_hit]]
        zi[start:stop] = block
        chunk_points = grid_flat[start * grid_nx:stop * grid_nx]
        chunk_inside = np.zeros(chunk_points.shape[0], dtype=bool)
        for ring in clip_rings:
            chunk_inside |= MplPath(np.asarray(ring, dtype=float)).contains_points(chunk_points)
        inside[start:stop] = chunk_inside.reshape(stop - start, grid_nx)

    rgba = np.zeros((*grid_x.shape, 4), dtype=np.float32)
    rgba[..., :3] = _continuous_level_colors(zi.astype(float), _level_color_anchors(breaks))
    rgba[..., 3] = inside
    ax.imshow(
        rgba, extent=(min_lon, max_lon, min_lat, max_lat),
        origin="lower", interpolation="bilinear", aspect="auto", zorder=1,
    )

    for entry in collected:
        edge = GROUP_PRIMARY_EDGE if entry["is_primary"] else GROUP_SECONDARY_EDGE
        linewidth = 0.9 if entry["is_primary"] else 0.4
        for ring in entry["rings"]:
            if ring and isinstance(ring[0], (list, tuple)):
                ax.add_patch(
                    MplPolygon(
                        ring, closed=True, facecolor="none", edgecolor=edge,
                        linewidth=linewidth, zorder=2,
                    )
                )
    visible_idx = []
    skipped_dots = 0
    for index, entry in enumerate(collected):
        lon, lat = entry["anchor"]
        if all(
            ((other["anchor"][0] - lon) ** 2 + (other["anchor"][1] - lat) ** 2) ** 0.5
            >= IDW_DOT_MIN_GAP_DEG
            for other_index, other in enumerate(collected)
            if other_index != index
        ):
            visible_idx.append(index)
        else:
            skipped_dots += 1
    if visible_idx:
        ax.plot(
            [collected[i]["anchor"][0] for i in visible_idx],
            [collected[i]["anchor"][1] for i in visible_idx],
            linestyle="", marker="o", markersize=4.5,
            markerfacecolor="#1e293b", markeredgecolor="white", markeredgewidth=1.1,
            alpha=0.9, zorder=8,  # 最高层：采样点在任何标签位移/描边组合下都必须可辨
        )
    return sum(len(entry["rings"]) for entry in collected), skipped_dots


def render_city_boundary_map(
    title: str, data: dict[str, Any], options: dict[str, Any], output_context: str
) -> tuple[str, dict[str, Any], list[str]]:
    configure_chinese_font()
    metric = str(data.get("metric") or options.get("metric") or "AQI")
    metric_key = _metric_key(metric)
    breaks, classification_basis = _resolve_breaks(data, options, metric_key)
    render_mode = str(options.get("render_mode") or "choropleth").strip().lower()
    if render_mode not in ("choropleth", "idw"):
        raise ValueError("render_mode 仅支持 choropleth（默认行政区填色）或 idw（城市点插值示意）。")
    value_mode = str(options.get("value_mode") or "value").strip().lower()
    if value_mode not in ("value", "mid"):
        raise ValueError("value_mode 仅支持 value（默认）或 mid（取区间 min~max 中值）。")
    idw_clip = str(options.get("idw_clip") or "cities").strip().lower()
    if render_mode == "idw" and idw_clip not in IDW_CLIP_MODES:
        raise ValueError("idw_clip 仅支持 cities（目标城市并集，默认，范围外留白）或 land（视野内陆地）。")

    records = _records(data)
    if not records:
        raise ValueError("city_boundary_map 需要 records[{city|adcode, value}] 或 cities+values。")

    by_adcode, by_name, boundary_asset, all_features = _boundary_feature_collections(data, options)
    warnings: list[str] = []
    matched: list[dict[str, Any]] = []
    unmatched: list[str] = []
    mid_used = 0
    for record in records:
        feature = None
        adcode = _record_adcode(record)
        if adcode is not None:
            feature = by_adcode.get(adcode)
        if feature is None:
            name_key = _city_key(
                record.get("city") or record.get("city_name") or record.get("name")
            )
            feature = by_name.get(name_key)
        value, used_mid = _record_seed_value(record, metric, value_mode)
        if used_mid:
            mid_used += 1
        if feature is None or value is None:
            label = str(record.get("city") or record.get("name") or adcode or "unknown")
            unmatched.append(label)
            continue
        matched.append(
            {
                "feature": feature,
                "adcode": adcode if adcode is not None else int(
                    (feature.get("properties") or {}).get("adcode") or 0
                ),
                "name": _city_key(
                    record.get("city") or record.get("city_name") or record.get("name")
                )
                or _city_key((feature.get("properties") or {}).get("name")),
                "value": value,
                "group": str(record.get("group") or "").strip(),
            }
        )
    if unmatched:
        warnings.append(f"{len(unmatched)} 条记录未匹配到边界要素，已跳过：{'、'.join(unmatched[:20])}")
    if not matched:
        raise ValueError("city_boundary_map：输入记录没有可渲染的行政区要素（检查 adcode/城市名与数值）。")
    if render_mode == "idw" and len(matched) < IDW_MIN_POINTS:
        raise ValueError(
            f"IDW 插值至少需要 {IDW_MIN_POINTS} 个有效城市点（当前 {len(matched)}）；"
            "城市过少时插值无意义，请使用默认填色模式或补充数据。"
        )
    if value_mode == "mid" and mid_used < len(matched):
        warnings.append(
            f"{len(matched) - mid_used} 条记录缺少 min/max 区间字段，已回退为单值参与渲染。"
        )

    groups = _group_order(records, options)
    primary_group = groups[0] if groups else None
    star_adcode = options.get("star_adcode")
    try:
        star_adcode = int(star_adcode) if star_adcode is not None else None
    except (TypeError, ValueError):
        star_adcode = None

    fig_width = 9.0 if output_context == "word" else 10.5
    fig, ax = plt.subplots(figsize=(fig_width, 8.0))
    ax.set_facecolor("#f8fafc")

    # —— 采集环、锚点与标签（两种模式共用）——
    collected: list[dict[str, Any]] = []
    coords: list[tuple[float, float]] = []
    labels: list[tuple[float, float, str, bool]] = []
    city_boxes: list[tuple[float, float, float, float]] = []
    for item in matched:
        is_primary = bool(item["group"]) and item["group"] == primary_group
        rings = _feature_rings(item["feature"])
        ring_points = [
            (float(point[0]), float(point[1]))
            for ring in rings if ring and isinstance(ring[0], (list, tuple))
            for point in ring if len(point) >= 2
        ]
        if not ring_points:
            continue
        props = item["feature"].get("properties") or {}
        lonlat = props.get("centroid") or props.get("center")
        if lonlat:
            anchor = (float(lonlat[0]), float(lonlat[1]))
        else:
            anchor = (
                sum(p[0] for p in ring_points) / len(ring_points),
                sum(p[1] for p in ring_points) / len(ring_points),
            )
        coords.extend(ring_points)
        city_boxes.append((
            min(p[0] for p in ring_points), max(p[0] for p in ring_points),
            min(p[1] for p in ring_points), max(p[1] for p in ring_points),
        ))
        name = item["name"]
        if star_adcode is not None and item["adcode"] == star_adcode:
            name = f"★{name}"
        labels.append((anchor[0], anchor[1], f"{name}\n{item['value']:g}", is_primary))
        collected.append({
            "rings": rings, "anchor": anchor,
            "value": item["value"], "is_primary": is_primary,
        })

    if not coords:
        plt.close(fig)
        raise ValueError("city_boundary_map：边界要素中没有可渲染的多边形。")

    min_lon = min(point[0] for point in coords)
    max_lon = max(point[0] for point in coords)
    min_lat = min(point[1] for point in coords)
    max_lat = max(point[1] for point in coords)

    if render_mode == "idw":
        rendered_polygons, skipped_dots = _paint_idw_surface(
            ax, collected, breaks, (min_lon, max_lon, min_lat, max_lat),
            all_features=all_features, clip_mode=idw_clip,
        )
        if skipped_dots:
            warnings.append(
                f"{skipped_dots} 个城市因与相邻城市过近（<{IDW_DOT_MIN_GAP_DEG}°）省略了采样点标记，插值仍参与。"
            )
    else:
        rendered_polygons = 0
        for entry in collected:
            color = COLORS[_color_index(entry["value"], breaks)]
            edge = GROUP_PRIMARY_EDGE if entry["is_primary"] else GROUP_SECONDARY_EDGE
            linewidth = GROUP_PRIMARY_WIDTH if entry["is_primary"] else GROUP_SECONDARY_WIDTH
            for ring in entry["rings"]:
                if ring and isinstance(ring[0], (list, tuple)):
                    ax.add_patch(
                        MplPolygon(
                            ring, closed=True, facecolor=color, edgecolor=edge,
                            linewidth=linewidth, zorder=4 if entry["is_primary"] else 3,
                        )
                    )
                    rendered_polygons += 1

    ax.set_title(str(normalize_matplotlib_label_text(title)), fontsize=15, pad=10)
    lon_padding = max(0.12, (max_lon - min_lon) * 0.035)
    lat_padding = max(0.12, (max_lat - min_lat) * 0.035)
    ax.set_xlim(min_lon - lon_padding, max_lon + lon_padding)
    ax.set_ylim(min_lat - lat_padding, max_lat + lat_padding)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    aspect = (max_lat - min_lat) / max(max_lon - min_lon, 1e-6)
    fig_height = min(16.0, max(5.0, fig_width * aspect))
    fig.set_size_inches(fig_width, fig_height)

    labels, displaced, unplaced = _resolve_label_overlaps(
        labels, city_boxes, fig_width,
        ax.get_xlim(), ax.get_ylim(),
        raise_above_anchor=(render_mode == "idw"),
    )
    if displaced:
        warnings.append(f"{displaced} 个城市标签因相邻密集做了位移避让。")
    if unplaced:
        warnings.append(f"{unplaced} 个城市标签区域过密，未能完全避让，建议减少城市数量或拆分渲染。")

    for lon, lat, text, is_primary in labels:
        ax.text(
            lon, lat, text, ha="center", va="center",
            fontsize=7.0 if is_primary else 6.8,
            fontweight="bold" if is_primary else "normal",
            color="#111827", zorder=6, linespacing=1.15,
            path_effects=[path_effects.withStroke(linewidth=2.2, foreground="white")],
        )

    aqi_handles = [
        plt.Line2D(
            [0], [0], marker="s", linestyle="", markerfacecolor=color,
            markeredgecolor="#64748b", markersize=9, label=label,
        )
        for color, label in zip(COLORS, LEVEL_LABELS, strict=True)
    ]
    legend_title = "AQI 分级" if metric_key == "AQI" else f"{metric} 浓度分级"
    if len(groups) > 1:
        # 先建分组图例并固定为 artist，再让 AQI 图例作为坐标轴图例——
        # 后一次 ax.legend() 会顶掉前一次，两组图例需分开持有。
        ring_handles = [
            Patch(facecolor="#cbd5e1", edgecolor=GROUP_PRIMARY_EDGE, linewidth=GROUP_PRIMARY_WIDTH, label=f"{primary_group}"),
            Patch(facecolor="#cbd5e1", edgecolor=GROUP_SECONDARY_EDGE, linewidth=GROUP_SECONDARY_WIDTH, label="其他分组"),
        ]
        group_legend = ax.legend(
            handles=ring_handles, loc="lower right", frameon=False, fontsize=7.5, title="分组"
        )
        ax.add_artist(group_legend)
    ax.legend(
        handles=aqi_handles, loc="lower left", ncol=3, frameon=False,
        fontsize=8, title=str(normalize_matplotlib_label_text(legend_title)),
    )
    if render_mode == "idw":
        clip_note = (
            "插值示意面覆盖视野内陆地（含无数据城市，为外推结果）"
            if idw_clip == "land" else "仅数据城市范围内着色"
        )
        # 注记放图幅下方外部：左下角有六档图例、右下可能有分组图例，图内底边必碰撞。
        ax.text(
            0.5, -0.012,
            f"基于城市点 IDW 插值示意（power={IDW_POWER:g}），非模式网格数据；{clip_note}",
            transform=ax.transAxes, ha="center", va="top", fontsize=6.5,
            color="#64748b", zorder=7,
        )

    apply_font_to_figure(fig)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    metadata = {
        "metric": metric,
        "metric_key": metric_key,
        "city_count": len(matched),
        "unmatched_record_count": len(unmatched),
        "rendered_polygon_count": rendered_polygons,
        "boundary_asset": boundary_asset,
        "breaks": breaks,
        "classification_basis": classification_basis,
        "level_labels": list(LEVEL_LABELS),
        "groups": groups,
        "render_mode": render_mode,
        "value_mode": value_mode,
        "seed_mid_used": mid_used,
        "scope": "china_city_level",
    }
    if render_mode == "idw":
        metadata["idw"] = {
            "power": IDW_POWER,
            "grid_steps": IDW_GRID_STEPS,
            "min_points": IDW_MIN_POINTS,
            "skipped_dots": skipped_dots,
            "clip": idw_clip,
        }
    return base64.b64encode(buffer.getvalue()).decode("ascii"), metadata, warnings
