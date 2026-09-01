from __future__ import annotations

import base64
import math
from collections.abc import Sequence
from datetime import date, datetime
from io import BytesIO
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.tools.visualization.create_report_chart.validation import ChartDataError
from app.utils.font_utils import apply_font_to_figure, configure_chinese_font


def render_wind_timeseries(
    *,
    title: str,
    data: dict[str, Any],
    options: dict[str, Any],
    output_context: str,
    style_profile: str,
) -> tuple[str, dict[str, Any], list[str]]:
    prepared, warnings = _prepare_data(data, options)
    from app.tools.visualization.create_report_chart.renderer import _line_width
    line_width = _line_width(options, default=1.0)
    timestamps = prepared["timestamps"]
    east_u = np.asarray(prepared["east_u"], dtype=float)
    north_v = np.asarray(prepared["north_v"], dtype=float)
    wind_speeds = np.hypot(east_u, north_v)
    concentrations = np.asarray(prepared["concentrations"], dtype=float)
    humidity = np.asarray(prepared.get("humidity", [float("nan")] * len(timestamps)), dtype=float)
    precipitation = np.asarray(prepared.get("precipitation", [float("nan")] * len(timestamps)), dtype=float)

    order = np.argsort(np.asarray(timestamps, dtype="datetime64[us]"))
    timestamps = [timestamps[index] for index in order]
    east_u = east_u[order]
    north_v = north_v[order]
    wind_speeds = wind_speeds[order]
    concentrations = concentrations[order]
    humidity = humidity[order]
    precipitation = precipitation[order]

    pollutant_name = str(
        normalize_matplotlib_label_text(
            data.get("pollutant_name") or options.get("pollutant_name") or "PM2.5"
        )
    )
    pollutant_unit = str(
        normalize_matplotlib_label_text(data.get("unit") or options.get("unit") or "μg/m³")
    )
    wind_speed_unit = str(
        normalize_matplotlib_label_text(
            data.get("wind_speed_unit") or options.get("wind_speed_unit") or "m/s"
        )
    )
    max_vectors = _bounded_int(options.get("max_vectors", data.get("max_vectors", 80)), 80, 12, 160)
    vector_indices = _evenly_spaced_indices(len(timestamps), max_vectors)
    if len(vector_indices) < len(timestamps):
        warnings.append("wind_vectors_thinned")

    configure_chinese_font()
    height = 7.4 if output_context == "word" else 7.0
    if style_profile == "compact":
        height = 6.5
    include_humidity = bool(options.get("include_humidity", data.get("include_humidity", False))) and np.isfinite(humidity).any()
    include_precipitation = bool(options.get("include_precipitation", data.get("include_precipitation", False))) and np.isfinite(precipitation).any()
    panel_count = 3 + int(include_humidity) + int(include_precipitation)
    fig, axes = plt.subplots(
        panel_count,
        1,
        figsize=(8.2, height),
        dpi=180,
        sharex=True,
        gridspec_kw={"height_ratios": [0.9] * panel_count, "hspace": 0.12},
    )
    axes = list(np.atleast_1d(axes))
    vector_ax, speed_ax, pollutant_ax = axes[:3]
    try:
        vector_x = [timestamps[index] for index in vector_indices]
        vector_u = east_u[vector_indices]
        vector_v = north_v[vector_indices]
        peak_speed = max(float(np.nanmax(wind_speeds)), 1.0)
        vector_ax.quiver(
            mdates.date2num(vector_x),
            np.zeros(len(vector_indices)),
            vector_u,
            vector_v,
            angles="uv",
            scale_units="height",
            scale=peak_speed * 7.0,
            color="#D94841",
            width=0.0032,
            headwidth=3.4,
            headlength=4.2,
            headaxislength=3.8,
            pivot="tail",
        )
        vector_ax.axhline(0, color="#9AA0A6", linewidth=0.65)
        vector_ax.set_ylim(-1, 1)
        vector_ax.set_yticks([])
        vector_ax.set_ylabel("风向", fontsize=9)

        speed_ax.plot(timestamps, wind_speeds, color="#356AE6", linewidth=line_width)
        speed_ax.fill_between(timestamps, 0, wind_speeds, color="#356AE6", alpha=0.10)
        speed_ax.set_ylim(bottom=0)
        speed_ax.set_ylabel(f"风速\n({wind_speed_unit})", fontsize=9)

        pollutant_ax.plot(timestamps, concentrations, color="#A23B72", linewidth=line_width)
        pollutant_ax.fill_between(timestamps, 0, concentrations, color="#A23B72", alpha=0.10)
        pollutant_ax.set_ylim(bottom=0)
        pollutant_label = (
            f"{pollutant_name}\n({pollutant_unit})" if pollutant_unit else pollutant_name
        )
        pollutant_ax.set_ylabel(pollutant_label, fontsize=9)
        pollutant_ax.set_xlabel("时间", fontsize=9)

        next_axis = 3
        if include_humidity:
            humidity_ax = axes[next_axis]
            humidity_ax.plot(timestamps, humidity, color="#2A9D8F", linewidth=line_width, label="相对湿度")
            humidity_ax.set_ylim(0, 100)
            humidity_ax.set_ylabel("湿度\n(%)", fontsize=9)
            next_axis += 1
        if include_precipitation:
            precipitation_ax = axes[next_axis]
            precipitation_ax.bar(timestamps, precipitation, width=0.025, color="#457B9D", alpha=0.75, label="降水")
            precipitation_ax.set_ylim(bottom=0)
            precipitation_ax.set_ylabel("降水\n(mm)", fontsize=9)

        for index, ax in enumerate(axes):
            ax.text(
                0.012,
                0.88,
                f"({chr(65 + index)})",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                color="#333333",
            )
            ax.grid(axis="y", color="#DADCE0", linewidth=0.55, alpha=0.7)
            ax.tick_params(axis="both", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#9AA0A6")
                spine.set_linewidth(0.65)

        locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
        pollutant_ax.xaxis.set_major_locator(locator)
        pollutant_ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月%d日\n%H:%M"))
        fig.suptitle(
            str(normalize_matplotlib_label_text(title)), fontsize=14, fontweight="bold", y=0.995
        )
        fig.align_ylabels(axes)
        fig.subplots_adjust(left=0.13, right=0.975, top=0.945, bottom=0.10)
        apply_font_to_figure(fig)
        return (
            _figure_to_base64(fig),
            {
                "pollutant_name": pollutant_name,
                "unit": pollutant_unit,
                "wind_speed_unit": wind_speed_unit,
                "wind_direction_convention": prepared["wind_direction_convention"],
                "input_mode": prepared["input_mode"],
                "valid_point_count": len(timestamps),
                "rendered_vector_count": len(vector_indices),
                "start_time": timestamps[0].isoformat(sep=" "),
                "end_time": timestamps[-1].isoformat(sep=" "),
            },
            _dedupe(warnings),
        )
    finally:
        plt.close(fig)


def _prepare_data(
    data: dict[str, Any], options: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    records = data.get("records")
    warnings: list[str] = []
    if isinstance(records, list):
        prepared, dropped = _prepare_records(records, data, options)
        if dropped:
            warnings.append("invalid_records_dropped")
        return prepared, warnings

    raw_timestamps = data.get("timestamps") or data.get("times") or data.get("dates")
    concentrations = (
        data.get("concentrations") or data.get("pollutant_values") or data.get("values")
    )
    if not isinstance(raw_timestamps, list) or not isinstance(concentrations, list):
        raise ChartDataError(
            "wind_timeseries 需要 timestamps、concentrations 和风速/风向或 east_u/north_v；也可提供 records。"
        )
    timestamps = [_parse_timestamp(value) for value in raw_timestamps]
    concentration_values = _float_array(concentrations, "concentrations", allow_nan=True)
    humidity_values = data.get("humidity")
    precipitation_values = data.get("precipitation")

    east_values = data.get("east_u") or data.get("east_components") or data.get("u")
    north_values = data.get("north_v") or data.get("north_components") or data.get("v")
    if isinstance(east_values, list) and isinstance(north_values, list):
        east_u = _float_array(east_values, "east_u")
        north_v = _float_array(north_values, "north_v")
        convention = "components"
        input_mode = "components"
    else:
        wind_speeds = _float_array(data.get("wind_speeds"), "wind_speeds")
        wind_directions = _float_array(data.get("wind_directions"), "wind_directions")
        convention = _direction_convention(data, options)
        east_u, north_v = _components_from_speed_direction(wind_speeds, wind_directions, convention)
        input_mode = "speed_direction"

    _validate_lengths(timestamps, east_u, north_v, concentration_values)
    _validate_prepared(timestamps, east_u, north_v, concentration_values)
    return {
        "timestamps": timestamps,
        "east_u": east_u,
        "north_v": north_v,
        "concentrations": concentration_values,
        "wind_direction_convention": convention,
        "input_mode": input_mode,
        "humidity": _optional_float_array(humidity_values, "humidity", len(timestamps)),
        "precipitation": _optional_float_array(precipitation_values, "precipitation", len(timestamps)),
    }, warnings


def _prepare_records(
    records: Sequence[Any], data: dict[str, Any], options: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    time_field = data.get("time_field") or options.get("time_field")
    speed_field = data.get("wind_speed_field") or options.get("wind_speed_field")
    direction_field = data.get("wind_direction_field") or options.get("wind_direction_field")
    east_field = data.get("east_field") or options.get("east_field")
    north_field = data.get("north_field") or options.get("north_field")
    concentration_field = data.get("concentration_field") or options.get("concentration_field")
    pollutant_name = str(data.get("pollutant_name") or options.get("pollutant_name") or "PM2.5")
    use_components = any(
        isinstance(record, dict)
        and _has_field(record, [east_field, "east_u", "east", "u"])
        and _has_field(record, [north_field, "north_v", "north", "v"])
        for record in records
    )
    convention = "components" if use_components else _direction_convention(data, options)

    timestamps: list[datetime] = []
    east_u: list[float] = []
    north_v: list[float] = []
    concentrations: list[float] = []
    humidity: list[float] = []
    precipitation: list[float] = []
    dropped = 0
    for record in records:
        if not isinstance(record, dict):
            dropped += 1
            continue
        try:
            timestamp = _parse_timestamp(
                _field_value(
                    record,
                    [time_field, "timestamp", "time", "datetime", "date", "监测时间", "时间"],
                )
            )
            concentration = float(
                _field_value(
                    record,
                    [
                        concentration_field,
                        pollutant_name,
                        pollutant_name.replace(".", ""),
                        "concentration",
                        "value",
                        "浓度",
                    ],
                )
            )
            if use_components:
                east = float(_field_value(record, [east_field, "east_u", "east", "u"]))
                north = float(_field_value(record, [north_field, "north_v", "north", "v"]))
            else:
                speed = float(
                    _field_value(
                        record,
                        [speed_field, "wind_speed_10m", "wind_speed", "WS", "ws", "speed", "风速"],
                    )
                )
                direction = float(
                    _field_value(
                        record,
                        [
                            direction_field,
                            "wind_direction_10m",
                            "wind_direction",
                            "WD",
                            "wd",
                            "direction",
                            "风向",
                        ],
                    )
                )
                east_values, north_values = _components_from_speed_direction(
                    [speed], [direction], convention
                )
                east, north = east_values[0], north_values[0]
            # Keep a timestamp when pollutant concentration is missing so the
            # meteorology panels still retain the complete hourly timeline.
            if not all(math.isfinite(value) for value in (east, north)):
                raise ValueError("non-finite wind value")
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        timestamps.append(timestamp)
        east_u.append(east)
        north_v.append(north)
        concentrations.append(concentration)
        humidity.append(_optional_record_value(record, ["humidity", "relative_humidity_2m", "relativeHumidity", "湿度"]))
        precipitation.append(_optional_record_value(record, ["precipitation", "rain1h", "降水"]))

    _validate_prepared(timestamps, east_u, north_v, concentrations)
    return {
        "timestamps": timestamps,
        "east_u": east_u,
        "north_v": north_v,
        "concentrations": concentrations,
        "wind_direction_convention": convention,
        "input_mode": "records_components" if use_components else "records_speed_direction",
        "humidity": humidity,
        "precipitation": precipitation,
    }, dropped


def _components_from_speed_direction(
    speeds: Sequence[float], directions: Sequence[float], convention: str
) -> tuple[list[float], list[float]]:
    if len(speeds) != len(directions):
        raise ChartDataError("wind_timeseries 的 wind_speeds 与 wind_directions 长度必须一致。")
    radians = np.deg2rad(np.asarray(directions, dtype=float))
    speed_values = np.asarray(speeds, dtype=float)
    if np.any(speed_values < 0):
        raise ChartDataError("wind_timeseries 的风速不能为负数。")
    if convention == "meteorological_from":
        return (-speed_values * np.sin(radians)).tolist(), (
            -speed_values * np.cos(radians)
        ).tolist()
    return (speed_values * np.cos(radians)).tolist(), (speed_values * np.sin(radians)).tolist()


def _direction_convention(data: dict[str, Any], options: dict[str, Any]) -> str:
    raw_value = data.get("wind_direction_convention") or options.get("wind_direction_convention")
    if raw_value is None:
        raise ChartDataError(
            "wind_timeseries 使用 wind_speeds/wind_directions 时必须显式提供 "
            "wind_direction_convention；气象来向使用 meteorological_from，"
            "数学去向使用 mathematical_to。工具不会预设风向定义。"
        )
    value = str(raw_value)
    if value not in {"meteorological_from", "mathematical_to"}:
        raise ChartDataError(
            "wind_timeseries 的 wind_direction_convention 仅支持 meteorological_from 或 mathematical_to。"
        )
    return value


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value is None:
        raise ChartDataError("wind_timeseries 的时间值不能为空。")
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ChartDataError(f"wind_timeseries 无法解析时间：{value}。") from exc


def _float_array(values: Any, name: str, allow_nan: bool = False) -> list[float]:
    if not isinstance(values, list):
        raise ChartDataError(f"wind_timeseries 需要 {name} 数组。")
    converted: list[float] = []
    for value in values:
        if value is None and allow_nan:
            converted.append(float("nan"))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ChartDataError(f"wind_timeseries 的 {name} 包含非数值。") from exc
        if not math.isfinite(number) and not (allow_nan and math.isnan(number)):
            raise ChartDataError(f"wind_timeseries 的 {name} 包含无效数值。")
        converted.append(number)
    return converted


def _optional_float_array(values: Any, name: str, length: int) -> list[float]:
    if values is None:
        return [float("nan")] * length
    converted = _float_array(values, name, allow_nan=True)
    if len(converted) != length:
        raise ChartDataError(f"wind_timeseries 的 {name} 长度必须与时间一致。")
    return converted


def _optional_record_value(record: dict[str, Any], candidates: Sequence[str]) -> float:
    for candidate in candidates:
        value = record.get(candidate)
        if value is not None:
            try:
                number = float(value)
                return number if math.isfinite(number) else float("nan")
            except (TypeError, ValueError):
                return float("nan")
    return float("nan")


def _validate_lengths(*arrays: Sequence[Any]) -> None:
    lengths = {len(values) for values in arrays}
    if len(lengths) != 1:
        raise ChartDataError("wind_timeseries 的时间、风场和污染物数组长度必须一致。")


def _validate_prepared(
    timestamps: Sequence[datetime],
    east_u: Sequence[float],
    north_v: Sequence[float],
    concentrations: Sequence[float],
) -> None:
    _validate_lengths(timestamps, east_u, north_v, concentrations)
    if len(timestamps) < 2:
        raise ChartDataError("wind_timeseries 至少需要 2 个有效数据点。")
    if not any(math.isfinite(float(value)) for value in concentrations):
        raise ChartDataError("wind_timeseries 没有可渲染的污染物浓度。")


def _field_value(record: dict[str, Any], candidates: Sequence[Any]) -> Any:
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in record and record[candidate] is not None:
            return record[candidate]
    raise KeyError("missing field")


def _has_field(record: dict[str, Any], candidates: Sequence[Any]) -> bool:
    return any(
        isinstance(candidate, str) and candidate in record and record[candidate] is not None
        for candidate in candidates
    )


def _evenly_spaced_indices(count: int, maximum: int) -> np.ndarray:
    if count <= maximum:
        return np.arange(count, dtype=int)
    return np.unique(np.linspace(0, count - 1, maximum, dtype=int))


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(max(int(value), minimum), maximum)
    except (TypeError, ValueError):
        return default


def _figure_to_base64(fig) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=180, facecolor="white")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
