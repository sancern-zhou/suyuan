"""Deterministic report figures for the Xuchang city-day exceedance report.

Charts render once inside the transport-analysis job and are attached to the
evidence package as ``visualizations`` artifacts; the report layer only ever
references them, it never redraws from raw rows.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Shanghai")

UNIT = "μg/m³"
FIELD_BY_POLLUTANT = {"PM2.5": "pm25", "PM10": "pm10", "O3": "o3", "NOX": "no2"}
INDUSTRY_COLORS = (
    "#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b",
    "#eecc16", "#b279a2", "#ff9da6", "#9d755d", "#bab0ac",
)
# 中文字体普遍缺少 Unicode 上标字形（如 ³），保存前统一改写为 mathtext，
# 避免 Y 轴单位出现黑色方块（tofu）。
_LABEL_NORMALIZATIONS = (
    ("μg/m³", "μg/m$^3$"),
    ("ug/m³", "ug/m$^3$"),
    ("/m³", "/m$^3$"),
)


def _normalize_label(value: Any) -> str:
    text = str(value)
    for source, target in _LABEL_NORMALIZATIONS:
        if source in text:
            text = text.replace(source, target)
    return text


def _field(pollutant: str) -> str:
    return FIELD_BY_POLLUTANT.get(pollutant, "pm25")


def _stamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(TZ) if parsed.tzinfo else parsed.replace(tzinfo=TZ)


def _hour_key(value: Any) -> str:
    """Normalize an hour stamp to a tz-naive Beijing local ISO key.

    统计层时间带 +08:00，抓取层时间可能无时区，两者同为北京墙上时间；
    直接做字符串匹配会因时区后缀错位导致曲线丢失。
    """
    stamp = _stamp(value)
    if stamp is None:
        return str(value)
    return stamp.replace(tzinfo=None).isoformat()


def _hour_label(value: str) -> str:
    stamp = _stamp(value)
    return stamp.strftime("%H时") if stamp else ""


def _valid_concentration(value: Any) -> float | None:
    """Reject non-numeric and missing-data sentinel values (negative fills)."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _save_figure(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    fig.clf()


def _artifact(path: Path, role: str, title: str) -> dict[str, str]:
    return {"role": role, "path": str(path), "title": title, "chart_type": "image"}


def national_station_curves(national_hourly: list[dict[str, Any]], path: Path, pollutant: str) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    by_station: dict[str, dict[str, float]] = defaultdict(dict)
    field = _field(pollutant)
    for row in national_hourly:
        value = _valid_concentration(row.get(field))
        if value is None:
            continue
        hour = row.get("data_time") or row.get("time")
        if hour is None:
            continue
        by_station[str(row.get("name") or row.get("station_id"))][_hour_key(hour)] = value
    if not by_station:
        return None
    all_hours = sorted({hour for samples in by_station.values() for hour in samples})
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    for index, (station, samples) in enumerate(sorted(by_station.items())):
        # 全站共用同一小时横轴，缺测小时留空断线，避免各站索引自对齐错位。
        values = [samples.get(hour) for hour in all_hours]
        ax.plot(range(len(all_hours)), values, linewidth=1.1, alpha=0.75,
                color=INDUSTRY_COLORS[index % len(INDUSTRY_COLORS)], label=station)
    mean_values = []
    for hour in all_hours:
        valid = [samples[hour] for samples in by_station.values() if hour in samples]
        mean_values.append(sum(valid) / len(valid) if valid else None)
    ax.plot(range(len(all_hours)), mean_values,
            linewidth=2.6, color="#1f2937", label="全市均值")
    ax.set_xticks(range(len(all_hours)))
    ax.set_xticklabels([_hour_label(hour) for hour in all_hours], fontsize=8, rotation=45)
    ax.set_ylabel(f"{pollutant} ({UNIT})")
    ax.set_title(f"国控站 {pollutant} 小时变化")
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "national_station_hourly_curves", "国控站小时变化")


def urban_district_comparison(city_hourly: list[dict[str, Any]], district_hourly: list[dict[str, Any]],
                              path: Path, pollutant: str) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    if not city_hourly or not district_hourly:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    base = [item["time"] for item in city_hourly]
    order = {hour: index for index, hour in enumerate(base)}
    ax.plot([order[item["time"]] for item in city_hourly], [item["mean"] for item in city_hourly],
            linewidth=2.6, color="#1f2937", label="城区(国控均值)")
    for curve in district_hourly:
        points = [(order[p["time"]], p["mean"]) for p in curve["points"] if p["time"] in order]
        if not points:
            continue
        ax.plot([p[0] for p in points], [p[1] for p in points],
                linewidth=1.1, alpha=0.8, label=curve["district"])
    ax.set_xticks(list(order.values()))
    ax.set_xticklabels([_hour_label(hour) for hour in order], fontsize=8, rotation=45)
    ax.set_ylabel(f"{pollutant} ({UNIT})")
    ax.set_title("城区与各区县乡镇站小时均值对比")
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "urban_district_hourly_comparison", "城区与区县对比")


def meteorology_panel(city_hourly: list[dict[str, Any]], meteo_rows: list[dict[str, Any]],
                      path: Path, pollutant: str) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    if not meteo_rows:
        return None
    hours = [str(row.get("time")) for row in meteo_rows]
    hours.sort()
    order = {hour: index for index, hour in enumerate(hours)}
    by_hour: dict[str, dict[str, Any]] = {str(row.get("time")): row for row in meteo_rows}
    fig, (ax_top, ax_bottom) = plt.subplots(2, 1, figsize=(8.6, 5.6), sharex=True,
                                            gridspec_kw={"height_ratios": (3, 2)})
    if city_hourly:
        points = [(order[item["time"]], item["mean"]) for item in city_hourly if item["time"] in order]
        ax_top.plot([p[0] for p in points], [p[1] for p in points], color="#c2410c",
                    linewidth=2.2, label=f"{pollutant}全市均值")
        ax_top.set_ylabel(f"{pollutant} ({UNIT})")
    humidity = [(order[h], by_hour[h].get("relative_humidity_2m")) for h in hours]
    humidity = [(x, y) for x, y in humidity if y is not None]
    if humidity:
        ax_top.plot([p[0] for p in humidity], [p[1] for p in humidity], color="#2563eb",
                    linewidth=1.6, linestyle="--", label="相对湿度(%)")
    ax_top.legend(fontsize=8, ncol=2)
    ax_top.grid(alpha=0.25)
    speed = [(order[h], by_hour[h].get("wind_speed_10m_ms")) for h in hours]
    speed = [(x, y) for x, y in speed if y is not None]
    direction = [(order[h], by_hour[h].get("wind_direction_10m")) for h in hours]
    direction = [(x, y) for x, y in direction if y is not None]
    if speed:
        ax_bottom.bar([p[0] for p in speed], [p[1] for p in speed], color="#94a3b8",
                      width=0.6, label="风速(m/s)")
    if direction:
        ax_bottom.scatter([p[0] for p in direction], [p[1] for p in direction],
                          color="#0f766e", s=14, marker="o", label="风向(°)")
        ax_bottom.axhline(180, color="#cbd5f5", linewidth=0.6)
    ax_bottom.set_ylabel("风速(m/s) / 风向(°)")
    ax_bottom.legend(fontsize=8, ncol=2)
    ax_bottom.grid(alpha=0.25)
    ax_bottom.set_xticks(list(order.values()))
    ax_bottom.set_xticklabels([_hour_label(hour) for hour in order], fontsize=8, rotation=45)
    fig.suptitle(f"{pollutant}与气象条件小时变化（许昌站）", y=1.0)
    fig.tight_layout()
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "meteorology_hourly_panel", "污染与气象小时变化")


def regional_city_curves(city_hourly: list[dict[str, Any]], regional_hourly: list[dict[str, Any]],
                         path: Path, pollutant: str) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    if not regional_hourly:
        return None
    field = _field(pollutant)
    by_city: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in regional_hourly:
        value = _valid_concentration(row.get(field))
        if value is None:
            continue
        hour = row.get("data_time") or row.get("time")
        if hour is None:
            continue
        by_city[str(row.get("name") or row.get("station_id"))].append((_hour_key(hour), value))
    if not by_city:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    base = [_hour_key(item["time"]) for item in city_hourly]
    order = {hour: index for index, hour in enumerate(base)}
    if base:
        ax.plot(list(order.values()), [item["mean"] for item in city_hourly],
                linewidth=2.6, color="#c2410c", label="许昌市")
    for index, (city, samples) in enumerate(sorted(by_city.items())):
        samples.sort()
        points = [(order[h], v) for h, v in samples if h in order]
        if not points:
            continue
        ax.plot([p[0] for p in points], [p[1] for p in points], linewidth=1.1, alpha=0.8,
                color=INDUSTRY_COLORS[index % len(INDUSTRY_COLORS)], label=city)
    ax.set_xticks(list(order.values()))
    ax.set_xticklabels([_hour_label(hour) for hour in order], fontsize=8, rotation=45)
    ax.set_ylabel(f"{pollutant} ({UNIT})")
    ax.set_title("许昌及周边城市小时变化对比")
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "regional_city_hourly_comparison", "周边城市小时对比")


def regional_daypart_bars(regional: list[dict[str, Any]], path: Path,
                          daypart: dict[str, Any]) -> dict[str, str] | None:
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [item for item in regional
            if item.get("night_mean") is not None or item.get("afternoon_mean") is not None]
    if not rows:
        return None
    night_label = daypart.get("night_label", "夜间")
    afternoon_label = daypart.get("afternoon_label", "午后")
    night = [item.get("night_mean") or 0 for item in rows]
    afternoon = [item.get("afternoon_mean") or 0 for item in rows]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    ax.bar(x - 0.2, night, width=0.4, color="#4c78a8", label=f"夜间均值({night_label})")
    ax.bar(x + 0.2, afternoon, width=0.4, color="#f58518", label=f"午后均值({afternoon_label})")
    for index, item in enumerate(rows):
        if item.get("night_to_afternoon_ratio") is not None:
            ax.text(index, max(item.get("night_mean") or 0, item.get("afternoon_mean") or 0) + 1,
                    f"夜/午 {item['night_to_afternoon_ratio']}", ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([item["city"] for item in rows], fontsize=9)
    ax.set_ylabel(f"均值 ({UNIT})")
    ax.set_title("周边城市夜间与午后均值对比")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "regional_city_daypart_comparison", "周边城市分时段均值")


def correlation_heatmap(correlation: dict[str, Any], path: Path) -> dict[str, str] | None:
    import matplotlib.pyplot as plt
    import numpy as np

    fields = list(correlation.get("fields") or [])
    medians = correlation.get("medians") or {}
    if len(fields) < 2:
        return None
    size = len(fields)
    matrix = np.full((size, size), np.nan)
    for i, first in enumerate(fields):
        for j, second in enumerate(fields):
            if i == j:
                matrix[i, j] = 1.0
                continue
            value = medians.get(f"{first}_{second}", medians.get(f"{second}_{first}"))
            if value is not None:
                matrix[i, j] = value
                matrix[j, i] = value
    labels = [correlation.get("labels", {}).get(field, field) for field in fields]
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    image = ax.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(size))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticks(range(size))
    ax.set_yticklabels(labels, fontsize=9)
    for i in range(size):
        for j in range(size):
            if not np.isnan(matrix[i, j]):
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.85)
    ax.set_title("污染物小时相关性（逐站Pearson中位数）")
    fig.tight_layout()
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "pollutant_correlation_heatmap", "污染物相关性热力图")


def township_spatial_map(township_top: list[dict[str, Any]], national_hourly: list[dict[str, Any]],
                         path: Path, pollutant: str) -> dict[str, str] | None:
    import matplotlib.pyplot as plt

    points = [item for item in township_top
              if item.get("lat") is not None and item.get("lon") is not None]
    if not points:
        return None
    fig, ax = plt.subplots(figsize=(6.8, 6.2))
    lons = [item["lon"] for item in points]
    lats = [item["lat"] for item in points]
    means = [item["daily_mean"] for item in points]
    scatter = ax.scatter(lons, lats, c=means, cmap="YlOrRd", s=90,
                         edgecolors="#7f1d1d", linewidths=0.5)
    for item in points[:5]:
        ax.annotate(str(item.get("station_name")), (item["lon"], item["lat"]),
                    fontsize=7, xytext=(3, 3), textcoords="offset points")
    anchors = [(row.get("lon"), row.get("lat"), row.get("name") or row.get("station_id"))
               for row in national_hourly[:1]]
    for lon, lat, name in anchors:
        if lon is None or lat is None:
            continue
        ax.scatter([lon], [lat], marker="*", s=220, color="#1d4ed8", zorder=3)
        ax.annotate(f"{name}(国控)", (lon, lat), fontsize=8, xytext=(4, 4),
                    textcoords="offset points", color="#1d4ed8")
    fig.colorbar(scatter, ax=ax, shrink=0.85, label=f"日均({UNIT})")
    ax.set_title(f"乡镇站 {pollutant} 日均空间分布（Top{len(points)}）")
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    ax.grid(alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "township_daily_spatial_distribution", "乡镇站空间分布")


def enterprise_top10_bars(enterprises: list[dict[str, Any]], path: Path) -> dict[str, str] | None:
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [item for item in enterprises if item.get("screening_score") is not None][:10]
    if not rows:
        return None
    industries = sorted({str(item.get("industry_category") or "其他") for item in rows})
    palette = {industry: INDUSTRY_COLORS[index % len(INDUSTRY_COLORS)]
               for index, industry in enumerate(industries)}
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.barh(y, [item["screening_score"] for item in rows],
            color=[palette[str(item.get("industry_category") or "其他")] for item in rows])
    ax.set_yticks(y)
    ax.set_yticklabels([str(item.get("enterprise_name"))[:18] for item in rows], fontsize=8)
    ax.invert_yaxis()
    for index, item in enumerate(rows):
        distance = item.get("distance_to_high_value_km")
        note = f"{item.get('distance_km')}km" if distance is None else f"距高值镇街{distance}km"
        ax.text(item["screening_score"], index, f"  {note}", va="center", fontsize=7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color) for color in palette.values()]
    ax.legend(handles, list(palette), fontsize=7, loc="lower right")
    ax.set_xlabel("筛查得分（清单排放量×距离衰减，非贡献率）")
    ax.set_title("嫌疑企业Top10筛查得分")
    ax.grid(axis="x", alpha=0.25)
    apply_font_to_figure(fig, _normalize_label)
    _save_figure(fig, path)
    return _artifact(path, "enterprise_screening_top10", "嫌疑企业筛查得分")


def generate_city_report_charts(
    *, output_dir: Path, job_id: str, pollutant: str,
    national_hourly: list[dict[str, Any]], city_day_statistics: dict[str, Any],
    meteorology_rows: list[dict[str, Any]],
    regional_hourly: list[dict[str, Any]],
    enterprise_screening: dict[str, Any],
) -> list[dict[str, str]]:
    """Render every template figure; single-chart failures never abort the job."""
    configure_chinese_font()
    charts_dir = output_dir / "charts"
    stats = city_day_statistics or {}
    tasks = (
        ("national", lambda p: national_station_curves(national_hourly, p, pollutant)),
        ("urban_district", lambda p: urban_district_comparison(
            stats.get("city_hourly") or [], stats.get("district_hourly") or [], p, pollutant)),
        ("meteorology", lambda p: meteorology_panel(
            stats.get("city_hourly") or [], meteorology_rows, p, pollutant)),
        ("regional_city", lambda p: regional_city_curves(
            stats.get("city_hourly") or [], regional_hourly, p, pollutant)),
        ("regional_daypart", lambda p: regional_daypart_bars(
            stats.get("regional") or [], p, stats.get("daypart") or {})),
        ("correlation", lambda p: correlation_heatmap(stats.get("pollutant_correlation") or {}, p)),
        ("township_spatial", lambda p: township_spatial_map(
            stats.get("township_daily_top") or [], national_hourly, p, pollutant)),
        ("enterprise_top10", lambda p: enterprise_top10_bars(
            enterprise_screening.get("enterprises") or [], p)),
    )
    artifacts = []
    for name, render in tasks:
        try:
            artifact = render(charts_dir / f"{job_id}-{name}.png")
            if artifact:
                artifacts.append(artifact)
        except Exception:
            logger.exception("xuchang_city_report_chart_failed", chart=name, job_id=job_id)
    return artifacts
