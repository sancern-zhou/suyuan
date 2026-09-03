"""Standard five-element weather forecast time-series chart."""

from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from app.tools.visualization.create_report_chart.renderer import _line_width
from app.tools.visualization.create_report_chart.validation import ChartDataError
from app.utils.font_utils import apply_font_to_figure, configure_chinese_font


def render_weather_timeseries(*, title: str, data: dict[str, Any], options: dict[str, Any], output_context: str, style_profile: str):
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise ChartDataError("weather_timeseries 需要 records。")
    fields = {
        "time": options.get("time_field", data.get("time_field", "forecast_time")),
        "speed": options.get("wind_speed_field", data.get("wind_speed_field", "wind_speed")),
        "direction": options.get("wind_direction_degrees_field", data.get("wind_direction_degrees_field", "wind_direction_degrees")),
        "temperature": options.get("temperature_field", data.get("temperature_field", "temperature")),
        "precipitation": options.get("precipitation_probability_field", data.get("precipitation_probability_field", "precipitation_probability")),
        "humidity": options.get("humidity_field", data.get("humidity_field", "humidity")),
    }
    rows = []
    for record in records:
        if not isinstance(record, dict) or fields["time"] not in record:
            continue
        try:
            timestamp = _parse_time(record[fields["time"]])
            values = [float(record.get(fields[key])) if record.get(fields[key]) is not None else np.nan for key in ("speed", "direction", "temperature", "precipitation", "humidity")]
        except (TypeError, ValueError):
            continue
        rows.append((timestamp, *values))
    if not rows:
        raise ChartDataError("weather_timeseries 没有可绘制的有效记录。")
    rows.sort(key=lambda row: row[0])
    days = {row[0].date() for row in rows}
    if len(days) != 1:
        raise ChartDataError(
            "weather_timeseries 一次只能绘制一个自然日；请按日期拆分 records 后分别调用。"
        )
    ts = [row[0] for row in rows]
    speed, direction, temperature, precipitation, humidity = [np.array([row[i] for row in rows], dtype=float) for i in range(1, 6)]
    width = _line_width(options, default=1.2)
    configure_chinese_font()
    fig, ax = plt.subplots(1, 1, figsize=(8.2, 5.8 if output_context == "word" else 5.4), dpi=180)
    wind_ax = ax.twinx()
    colors = {"speed": "#356AE6", "temperature": "#D97706", "precipitation": "#8A5AB5", "humidity": "#159A9C"}
    valid_dir = np.isfinite(direction)
    ax.plot(ts, temperature, color=colors["temperature"], linewidth=width, marker="o", markersize=2.5, label="温度 (℃)")
    ax.plot(ts, humidity, color=colors["humidity"], linewidth=width, marker="o", markersize=2.5, label="湿度 (%)")
    ax.plot(ts, precipitation, color=colors["precipitation"], linewidth=width, marker="s", markersize=2.5, label="降水概率 (%)")
    for index in range(0, len(ts), max(1, len(ts) // 6)):
        if np.isfinite(temperature[index]):
            ax.annotate(f"{temperature[index]:g}", (ts[index], temperature[index]), xytext=(0, 6), textcoords="offset points", fontsize=7, color=colors["temperature"], ha="center")
    wind_ax.plot(ts, speed, color=colors["speed"], linewidth=width, marker="^", markersize=2.8, label="风速 (m/s)")
    ax.set_ylabel("温度 / 湿度 / 降水概率", fontsize=9)
    wind_ax.set_ylabel("风速 (m/s)", fontsize=9, color=colors["speed"])
    wind_ax.tick_params(axis="y", labelcolor=colors["speed"])
    ax.set_ylim(0, max(100, float(np.nanmax(np.r_[humidity, precipitation])) * 1.15 if np.isfinite(np.r_[humidity, precipitation]).any() else 100))
    wind_ax.set_ylim(0, max(1, float(np.nanmax(speed)) * 1.25 if np.isfinite(speed).any() else 1))
    top = ax.get_ylim()[1] * 0.86
    # Meteorological direction is the direction the wind comes *from*.
    # Draw a true-degree arrow pointing toward where it goes; do not quantize
    # to cardinal glyphs, which loses information and is font-dependent.
    for value, timestamp in zip(direction[valid_dir], np.asarray(ts, dtype=object)[valid_dir], strict=True):
        angle = np.deg2rad(float(value) % 360.0 + 180.0)
        dx = 10.0 * np.sin(angle)
        dy = 10.0 * np.cos(angle)
        ax.annotate(
            "",
            xy=(timestamp, top),
            xycoords="data",
            xytext=(-dx, -dy),
            textcoords="offset points",
            arrowprops={
                "arrowstyle": "-|>",
                "color": "#B7791F",
                "lw": max(0.8, width),
                "mutation_scale": 10,
            },
            annotation_clip=False,
        )
    areas = options.get("areas") or data.get("areas") or options.get("risk_periods") or data.get("risk_periods") or []
    for period in areas:
        try:
            start = _parse_time(period.get("start")); end = _parse_time(period.get("end"))
        except (TypeError, ValueError):
            continue
        level = str(period.get("level", "medium")).lower()
        color = period.get("color") or {"high": "#FFC7CE", "medium": "#FCE4D6", "low": "#FFEB9C"}.get(level, "#FCE4D6")
        alpha = float(period.get("alpha", 0.35))
        for target in (ax, wind_ax): target.axvspan(start, end, color=color, alpha=alpha, zorder=0)
        ax.text(start, ax.get_ylim()[1] * 0.76, str(period.get("name") or period.get("label") or period.get("factor") or "标识区域"), fontsize=8, color=str(period.get("text_color") or "#9C0006"), va="top")
    ax.grid(axis="y", color="#DADCE0", linewidth=0.55, alpha=0.7)
    ax.tick_params(axis="both", labelsize=8)
    wind_ax.tick_params(axis="x", labelsize=8)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月%d日\n%H:%M"))
    ax.set_xlabel("时间", fontsize=9)
    handles, legend_labels = [], []
    for target in (ax, wind_ax):
        h, l = target.get_legend_handles_labels(); handles.extend(h); legend_labels.extend(l)
    ax.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, 1.08), fontsize=8, frameon=False, ncol=4)
    fig.suptitle(str(title), fontsize=14, fontweight="bold", y=0.995)
    fig.subplots_adjust(left=0.12, right=0.88, top=0.78, bottom=0.16)
    apply_font_to_figure(fig)
    output = BytesIO(); fig.savefig(output, format="png", dpi=180, bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(output.getvalue()).decode("ascii"), {"valid_point_count": len(ts), "line_width": width, "date": ts[0].date().isoformat(), "start_time": ts[0].isoformat(sep=" "), "end_time": ts[-1].isoformat(sep=" "), "area_count": len(areas)}, []


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime): return value
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
