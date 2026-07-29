from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG
from app.utils.font_utils import apply_font_to_figure, chinese_font_prop

EARTH_RADIUS_KM = 6371.0088
MAX_SUMMARY_HOTSPOTS = 20
FIRE_MAP_LABELS = {
    "title": "NASA FIRMS火点分布图",
    "center_label": "运城",
    "hotspot_label": "卫星火点",
    "frp_label": "火点辐射功率 FRP（MW）",
    "longitude": "经度",
    "latitude": "纬度",
    "yellow_river": "黄河",
    "empty": "告警前6小时内未检索到FIRMS火点",
    "footer": "本地图底图渲染，数据来自NASA FIRMS CSV；卫星热异常仅作线索，不等同于污染源确认。",
}
LOCAL_MAP_CITIES = [
    {"name": "运城", "lat": 35.0228, "lon": 111.0075, "rank": 1},
    {"name": "临汾", "lat": 36.0880, "lon": 111.5190, "rank": 2},
    {"name": "晋城", "lat": 35.4910, "lon": 112.8520, "rank": 2},
    {"name": "三门峡", "lat": 34.7732, "lon": 111.2004, "rank": 2},
    {"name": "渭南", "lat": 34.4994, "lon": 109.5102, "rank": 2},
    {"name": "洛阳", "lat": 34.6197, "lon": 112.4540, "rank": 2},
    {"name": "西安", "lat": 34.3416, "lon": 108.9398, "rank": 3},
    {"name": "侯马", "lat": 35.6191, "lon": 111.3720, "rank": 3},
    {"name": "河津", "lat": 35.5964, "lon": 110.7108, "rank": 3},
    {"name": "灵宝", "lat": 34.5168, "lon": 110.8942, "rank": 3},
]

LOCAL_MAP_BOUNDARIES = [
    [(109.10, 36.75), (109.75, 36.25), (110.35, 35.88), (111.05, 35.64), (111.70, 35.42), (112.45, 35.05)],
    [(109.25, 34.80), (109.95, 35.05), (110.55, 35.18), (111.10, 35.02), (111.72, 34.74), (112.55, 34.55)],
    [(110.25, 33.70), (110.65, 34.25), (111.10, 34.72), (111.48, 35.10), (111.90, 35.58), (112.35, 36.08)],
]

YELLOW_RIVER_REFERENCE = [
    (108.95, 35.56),
    (109.45, 35.56),
    (109.93, 35.50),
    (110.25, 35.35),
    (110.55, 35.10),
    (110.78, 34.86),
    (111.05, 34.70),
    (111.33, 34.68),
    (111.72, 34.77),
    (112.05, 34.92),
    (112.52, 35.05),
]


def build_fire_hotspot_summary(
    fire_payload: dict[str, Any],
    *,
    alert_time: datetime,
    center_lat: float = YUNCHENG_TRIAL_CONFIG.lat,
    center_lon: float = YUNCHENG_TRIAL_CONFIG.lon,
    max_hotspots: int = MAX_SUMMARY_HOTSPOTS,
) -> dict[str, Any]:
    hotspots = fire_payload.get("hotspots") if isinstance(fire_payload.get("hotspots"), list) else []
    enriched = [
        _enrich_hotspot(h, alert_time=alert_time, center_lat=center_lat, center_lon=center_lon)
        for h in hotspots
        if _has_coordinate(h)
    ]
    enriched.sort(key=lambda h: (h.get("hours_before_alert", 9999), -float(h.get("frp") or 0)))

    return {
        "source": "NASA FIRMS",
        "center": {
            "name": YUNCHENG_TRIAL_CONFIG.city,
            "lat": center_lat,
            "lon": center_lon,
        },
        "time_window": {
            "end": alert_time.strftime("%Y-%m-%d %H:%M:%S"),
            "lookback_hours": 6,
        },
        "count": len(enriched),
        "count_by_window": {
            "within_1h": sum(1 for h in enriched if _within(h, 1)),
            "within_3h": sum(1 for h in enriched if _within(h, 3)),
            "within_6h": sum(1 for h in enriched if _within(h, 6)),
        },
        "direction_counts": _direction_counts(enriched),
        "nearest_hotspot": min(enriched, key=lambda h: h["distance_km"], default=None),
        "highest_frp_hotspot": max(enriched, key=lambda h: float(h.get("frp") or 0), default=None),
        "top_hotspots": _top_hotspots(enriched, max_hotspots),
        "business_note": _business_note(enriched),
        "usage_boundary": "卫星火点只作为周边燃烧或热异常线索，不能单独确认具体污染源或责任主体。",
    }


def render_fire_hotspot_map(
    summary: dict[str, Any],
    output_path: Path,
    *,
    bbox: dict[str, float],
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.patches import Rectangle

    chinese_font = _configure_chinese_font(plt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hotspots = summary.get("top_hotspots") if isinstance(summary.get("top_hotspots"), list) else []
    center = summary["center"]

    min_lon = bbox["min_lon"]
    max_lon = bbox["max_lon"]
    min_lat = bbox["min_lat"]
    max_lat = bbox["max_lat"]
    lon_pad = max((max_lon - min_lon) * 0.08, 0.1)
    lat_pad = max((max_lat - min_lat) * 0.08, 0.1)
    view_min_lon = min_lon - lon_pad
    view_max_lon = max_lon + lon_pad
    view_min_lat = min_lat - lat_pad
    view_max_lat = max_lat + lat_pad

    fig, ax = plt.subplots(figsize=(9.6, 7.2), dpi=180)
    fig.patch.set_facecolor("#f7f8f2")
    ax.set_facecolor("#eef1ea")
    ax.set_xlim(view_min_lon, view_max_lon)
    ax.set_ylim(view_min_lat, view_max_lat)
    _draw_local_basemap(ax, view_min_lon, view_max_lon, view_min_lat, view_max_lat, fontproperties=chinese_font)

    ax.add_patch(
        Rectangle(
            (min_lon, min_lat),
            max_lon - min_lon,
            max_lat - min_lat,
            fill=False,
            edgecolor="#5f6c75",
            linewidth=1.15,
            linestyle="--",
            alpha=0.95,
            zorder=3,
        )
    )

    ax.scatter(
        [center["lon"]],
        [center["lat"]],
        marker="*",
        s=220,
        color="#2673a6",
        edgecolor="white",
        linewidth=0.9,
        zorder=7,
        label=FIRE_MAP_LABELS["center_label"],
    )
    ax.text(
        center["lon"] + 0.06,
        center["lat"] + 0.05,
        FIRE_MAP_LABELS["center_label"],
        color="#23313a",
        fontsize=9,
        zorder=8,
        fontproperties=chinese_font,
    )

    if hotspots:
        frps = [float(h.get("frp") or 0) for h in hotspots]
        sizes = [max(24, min(180, 28 + math.sqrt(max(frp, 0)) * 18)) for frp in frps]
        sc = ax.scatter(
            [h["lon"] for h in hotspots],
            [h["lat"] for h in hotspots],
            s=sizes,
            c=frps,
            cmap="YlOrRd",
            norm=Normalize(vmin=min(frps), vmax=max(frps) or 1),
            edgecolor="#6b1f0d",
            linewidth=0.45,
            alpha=0.90,
            zorder=6,
            label=FIRE_MAP_LABELS["hotspot_label"],
        )
        cbar = fig.colorbar(sc, ax=ax, fraction=0.036, pad=0.03)
        cbar.set_label(FIRE_MAP_LABELS["frp_label"], color="#2d3439", fontproperties=chinese_font)
        cbar.ax.yaxis.set_tick_params(color="#2d3439")
        plt.setp(cbar.ax.get_yticklabels(), color="#2d3439")
    else:
        ax.text(
            0.5,
            0.52,
            FIRE_MAP_LABELS["empty"],
            transform=ax.transAxes,
            ha="center",
            va="center",
            color="#3b444b",
            fontsize=13,
            alpha=0.9,
            fontproperties=chinese_font,
        )

    title = FIRE_MAP_LABELS["title"]
    subtitle = f"运城 | {summary['time_window']['end']} | 告警前6小时 | 火点数={summary['count']}"
    ax.set_title(f"{title}\n{subtitle}", color="#20272d", fontsize=13, pad=16, fontproperties=chinese_font)
    ax.set_xlabel(FIRE_MAP_LABELS["longitude"], color="#2d3439", fontproperties=chinese_font)
    ax.set_ylabel(FIRE_MAP_LABELS["latitude"], color="#2d3439", fontproperties=chinese_font)
    ax.tick_params(colors="#2d3439")
    for spine in ax.spines.values():
        spine.set_color("#aeb7af")
    legend = ax.legend(
        loc="lower left",
        facecolor="#f7f8f2",
        edgecolor="#aeb7af",
        framealpha=0.90,
        prop=chinese_font,
    )
    for text in legend.get_texts():
        text.set_color("#2d3439")
    ax.text(
        0.99,
        0.01,
        FIRE_MAP_LABELS["footer"],
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#56636b",
        fontsize=7.5,
        fontproperties=chinese_font,
    )
    apply_font_to_figure(fig)
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def _has_coordinate(hotspot: Any) -> bool:
    return isinstance(hotspot, dict) and hotspot.get("lat") is not None and hotspot.get("lon") is not None


def _enrich_hotspot(hotspot: dict[str, Any], *, alert_time: datetime, center_lat: float, center_lon: float) -> dict[str, Any]:
    lat = float(hotspot["lat"])
    lon = float(hotspot["lon"])
    distance = haversine_km(center_lat, center_lon, lat, lon)
    bearing = bearing_degrees(center_lat, center_lon, lat, lon)
    acquisition_time = str(hotspot.get("acquisition_time") or hotspot.get("acq_datetime") or "")
    hours_before = _hours_before_alert(acquisition_time, alert_time)
    return {
        "lat": lat,
        "lon": lon,
        "distance_km": round(distance, 1),
        "direction": direction_label(bearing),
        "bearing_degrees": round(bearing, 1),
        "hours_before_alert": round(hours_before, 2) if hours_before is not None else None,
        "frp": hotspot.get("frp"),
        "confidence": hotspot.get("confidence"),
        "brightness": hotspot.get("brightness"),
        "acquisition_time": acquisition_time,
        "satellite": hotspot.get("satellite"),
        "day_night": hotspot.get("day_night") or hotspot.get("daynight"),
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def direction_label(bearing: float) -> str:
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int((bearing + 22.5) // 45) % 8]


def _hours_before_alert(acquisition_time: str, alert_time: datetime) -> float | None:
    if not acquisition_time:
        return None
    try:
        parsed = datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
    except ValueError:
        return None
    return (alert_time - parsed).total_seconds() / 3600


def _within(hotspot: dict[str, Any], hours: int) -> bool:
    value = hotspot.get("hours_before_alert")
    return isinstance(value, (int, float)) and 0 <= value <= hours


def _direction_counts(hotspots: list[dict[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]}
    for hotspot in hotspots:
        direction = str(hotspot.get("direction") or "")
        if direction in counts:
            counts[direction] += 1
    return {k: v for k, v in counts.items() if v}


def _top_hotspots(hotspots: list[dict[str, Any]], max_hotspots: int) -> list[dict[str, Any]]:
    ranked = sorted(
        hotspots,
        key=lambda h: (
            h.get("hours_before_alert") if isinstance(h.get("hours_before_alert"), (int, float)) else 9999,
            h["distance_km"],
            -float(h.get("frp") or 0),
        ),
    )
    return ranked[:max_hotspots]


def _business_note(hotspots: list[dict[str, Any]]) -> str:
    if not hotspots:
        return "告警前6小时检索范围内未见NASA FIRMS卫星火点线索。"
    nearest = min(hotspots, key=lambda h: h["distance_km"])
    return (
        f"告警前6小时检索范围内发现{len(hotspots)}个NASA FIRMS火点线索；"
        f"最近火点位于运城{nearest['direction']}方向约{nearest['distance_km']}km，"
        "需结合风场、轨迹和本地巡查核实。"
    )


def _draw_local_basemap(
    ax: Any,
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
    *,
    fontproperties: Any,
) -> None:
    from matplotlib.patches import Polygon

    land_poly = [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
    ]
    ax.add_patch(Polygon(land_poly, closed=True, facecolor="#eef1ea", edgecolor="none", zorder=0))
    _draw_relief(ax, min_lon, max_lon, min_lat, max_lat)
    _draw_line(ax, YELLOW_RIVER_REFERENCE, color="#77a9c9", linewidth=2.0, alpha=0.82, zorder=2)
    ax.text(
        110.64,
        34.86,
        FIRE_MAP_LABELS["yellow_river"],
        color="#5a8eaf",
        fontsize=7.5,
        rotation=-25,
        zorder=3,
        fontproperties=fontproperties,
    )
    for boundary in LOCAL_MAP_BOUNDARIES:
        _draw_line(ax, boundary, color="#aeb7af", linewidth=0.9, alpha=0.75, zorder=2)

    ax.grid(color="#cfd6cf", linestyle="-", linewidth=0.55, alpha=0.75, zorder=1)
    for lon in _frange(math.ceil(min_lon), math.floor(max_lon), 1):
        ax.axvline(lon, color="#c4ccc3", linewidth=0.65, zorder=1)
    for lat in _frange(math.ceil(min_lat), math.floor(max_lat), 1):
        ax.axhline(lat, color="#c4ccc3", linewidth=0.65, zorder=1)

    for city in LOCAL_MAP_CITIES:
        if city["name"] == FIRE_MAP_LABELS["center_label"]:
            continue
        lon = city["lon"]
        lat = city["lat"]
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        marker_size = 26 if city["rank"] <= 2 else 15
        ax.scatter([lon], [lat], s=marker_size, color="#6d7478", edgecolor="white", linewidth=0.35, zorder=4)
        x_offset = -0.32 if lon > max_lon - 0.28 else 0.04
        y_offset = -0.08 if lat > max_lat - 0.18 else 0.035
        ax.text(
            lon + x_offset,
            lat + y_offset,
            city["name"],
            color="#4c555b",
            fontsize=7.4,
            zorder=4,
            fontproperties=fontproperties,
        )


def _draw_relief(ax: Any, min_lon: float, max_lon: float, min_lat: float, max_lat: float) -> None:
    import numpy as np
    from matplotlib.colors import ListedColormap

    x = np.linspace(min_lon, max_lon, 180)
    y = np.linspace(min_lat, max_lat, 150)
    xx, yy = np.meshgrid(x, y)
    relief = (
        0.48 * np.sin((xx - 108.8) * 3.4)
        + 0.36 * np.cos((yy - 33.5) * 4.8)
        + 0.18 * np.sin((xx + yy) * 4.0)
    )
    cmap = ListedColormap(["#e4e9df", "#edf1e7", "#f3f4ea", "#e8eddf"])
    ax.contourf(x, y, relief, levels=8, cmap=cmap, alpha=0.56, zorder=0)


def _draw_line(
    ax: Any,
    points: list[tuple[float, float]],
    *,
    color: str,
    linewidth: float,
    alpha: float,
    zorder: int,
) -> None:
    if not points:
        return
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=color, linewidth=linewidth, alpha=alpha, zorder=zorder)


def _configure_chinese_font(plt: Any) -> Any:
    prop = chinese_font_prop()
    family = prop.get_name() if prop is not None else "Droid Sans Fallback"
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [family, "Noto Sans CJK SC", "Droid Sans Fallback", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return prop


def _frange(start: int, stop: int, step: int) -> list[int]:
    return list(range(start, stop + 1, step))
