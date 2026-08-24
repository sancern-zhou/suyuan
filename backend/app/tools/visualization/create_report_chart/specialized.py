from __future__ import annotations

import base64
import calendar
import math
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Sequence

import matplotlib.pyplot as plt
import numpy as np

from app.utils.font_utils import apply_font_to_figure, configure_chinese_font
from app.services.image_cache import get_image_cache
from app.tools.visualization.create_report_chart.renderer import ChartDataError, WORD_TARGET_WIDTH_IN
from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.utils.font_utils import apply_font_to_figure


def render_specialized_chart(
    chart_id: str | None,
    chart_type: str,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    configure_chinese_font()
    if chart_type == "aqi_calendar":
        return _render_aqi_calendar(chart_id, title, data, output_context, options)
    if chart_type == "pollutant_wind_rose":
        return _render_pollutant_wind_rose(chart_id, title, data, output_context, options)
    if chart_type == "pollutant_calendar":
        return _render_pollutant_calendar(chart_id, title, data, output_context, options)
    if chart_type == "generic_pollutant_wind_rose":
        return _render_generic_pollutant_wind_rose(chart_id, title, data, output_context, options)
    if chart_type == "wind_timeseries":
        return _render_wind_timeseries(chart_id, title, data, output_context, style_profile, options)
    if chart_type == "henan_city_map":
        from app.tools.visualization.create_report_chart.domain.henan_city_map import render_henan_city_map

        image_base64, metadata, warnings = render_henan_city_map(title, data, options, output_context)
        visual = _cache_base64_image(image_base64, chart_id or "henan_city_map", title)
        return {
            "chart_id": visual["image_id"],
            "title": title,
            "visuals": [visual],
            "layout_warnings": warnings,
            "metadata": {
                "requested_chart_type": "henan_city_map",
                "applied_chart_type": "henan_city_map",
                "output_context": output_context,
                **metadata,
            },
            "summary": f"报告图表已生成：{title}。",
        }
    raise ChartDataError(f"不支持的专用 chart_type：{chart_type}。")


def _render_wind_timeseries(
    chart_id: str | None,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    from app.tools.visualization.create_report_chart.domain.wind_timeseries import (
        render_wind_timeseries,
    )

    image_base64, metadata, warnings = render_wind_timeseries(
        title=title,
        data=data,
        options=options,
        output_context=output_context,
        style_profile=style_profile,
    )
    pollutant_name = metadata["pollutant_name"]
    visual = _cache_base64_image(
        image_base64,
        chart_id or f"wind_timeseries_{pollutant_name}",
        title,
    )
    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": warnings,
        "metadata": {
            "requested_chart_type": "wind_timeseries",
            "applied_chart_type": "wind_timeseries",
            "scope": "generic",
            "output_context": output_context,
            **metadata,
        },
        "summary": f"报告图表已生成：{title}。",
    }


def _render_aqi_calendar(
    chart_id: str | None,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    from app.tools.visualization.create_report_chart.domain.aqi_calendar import (
        AQICalendarRenderer,
        GUANGDONG_CITIES,
        _process_city_data_impl,
    )

    year = _int_option(data, options, "year")
    month = _int_option(data, options, "month")
    pollutant = str(data.get("pollutant") or options.get("pollutant") or "AQI")
    if year is None or month is None:
        raise ChartDataError("aqi_calendar 需要 year 和 month。")
    if month < 1 or month > 12:
        raise ChartDataError("aqi_calendar 的 month 必须为 1-12。")

    city_data_map = data.get("city_data_map")
    if isinstance(city_data_map, dict):
        prepared = _normalize_city_data_map(city_data_map)
    else:
        records = _records_from_data(data)
        if not records:
            raise ChartDataError("aqi_calendar 需要 city_data_map 或 records。")
        cities = data.get("cities") or options.get("cities")
        if not isinstance(cities, list) or not cities:
            cities = _cities_from_records(records) or GUANGDONG_CITIES
        prepared = _process_city_data_impl(records, cities[:21], year, month, pollutant)

    if not any(day_map for day_map in prepared.values()):
        raise ChartDataError("aqi_calendar 没有可渲染的有效日期数据。")

    image_base64 = AQICalendarRenderer().render_calendar(
        prepared,
        year,
        month,
        pollutant,
        font_scale=options.get("font_scale"),
    )
    visual = _cache_base64_image(image_base64, chart_id or f"aqi_calendar_{year}_{month}_{pollutant}", title)
    statistics = _calendar_statistics(prepared, year, month)

    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": [],
        "metadata": {
            "requested_chart_type": "aqi_calendar",
            "applied_chart_type": "aqi_calendar",
            "scope": "guangdong_only",
            "scope_note": "广东省专用图表，其他地区请使用 pollutant_calendar。",
            "output_context": output_context,
            "year": year,
            "month": month,
            "pollutant": pollutant,
            **statistics,
        },
        "summary": f"报告图表已生成：{title}。",
    }


def _render_pollutant_wind_rose(
    chart_id: str | None,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    from app.tools.visualization.create_report_chart.domain.pollutant_wind_rose import (
        aggregate_by_time,
        generate_pollution_rose_contour,
    )

    pollutant_name = str(data.get("pollutant_name") or options.get("pollutant_name") or "PM10")
    unit = str(normalize_matplotlib_label_text(data.get("unit") or options.get("unit") or "μg/m³"))

    wind_directions = _number_sequence(data.get("wind_directions"))
    wind_speeds = _number_sequence(data.get("wind_speeds"))
    concentrations = _number_sequence(data.get("concentrations"))

    records = _records_from_data(data)
    if not wind_directions and records:
        extracted = _extract_wind_rose_arrays(records, data, options, pollutant_name)
        wind_directions = extracted["wind_directions"]
        wind_speeds = extracted["wind_speeds"]
        concentrations = extracted["concentrations"]
        timestamps = extracted["timestamps"]
        time_resolution = str(data.get("time_resolution") or options.get("time_resolution") or "5min")
        if time_resolution in {"hour", "day"} and timestamps:
            wind_directions, wind_speeds, concentrations = aggregate_by_time(
                timestamps=timestamps,
                wind_directions=wind_directions,
                wind_speeds=wind_speeds,
                concentrations=concentrations,
                resolution=time_resolution,
            )

    if not (wind_directions and wind_speeds and concentrations):
        raise ChartDataError("pollutant_wind_rose 需要 wind_directions、wind_speeds、concentrations 或 records。")
    if not (len(wind_directions) == len(wind_speeds) == len(concentrations)):
        raise ChartDataError("pollutant_wind_rose 的风向、风速、浓度长度必须一致。")

    image_base64 = generate_pollution_rose_contour(
        wind_directions=wind_directions,
        wind_speeds=wind_speeds,
        concentrations=concentrations,
        title=title,
        pollutant_name=pollutant_name,
        unit=unit,
        use_six_level=bool(options.get("use_six_level", data.get("use_six_level", True))),
        output_context=output_context,
        target_width_in=WORD_TARGET_WIDTH_IN,
        font_scale=options.get("font_scale"),
    )
    visual = _cache_base64_image(image_base64, chart_id or f"pollutant_wind_rose_{pollutant_name}", title)

    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": [],
        "metadata": {
            "requested_chart_type": "pollutant_wind_rose",
            "applied_chart_type": "pollutant_wind_rose",
            "scope": "guangdong_only",
            "scope_note": "广东省专用图表，其他地区请使用 generic_pollutant_wind_rose。",
            "output_context": output_context,
            "pollutant_name": pollutant_name,
            "unit": unit,
            "valid_point_count": len(wind_directions),
            "use_six_level": bool(options.get("use_six_level", data.get("use_six_level", True))),
        },
        "summary": f"报告图表已生成：{title}。",
    }


def _render_pollutant_calendar(
    chart_id: str | None,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    year = _int_option(data, options, "year")
    month = _int_option(data, options, "month")
    pollutant = str(normalize_matplotlib_label_text(data.get("pollutant") or options.get("pollutant") or "污染物"))
    unit = str(normalize_matplotlib_label_text(data.get("unit") or options.get("unit") or ""))
    if year is None or month is None:
        raise ChartDataError("pollutant_calendar 需要 year 和 month。")
    if month < 1 or month > 12:
        raise ChartDataError("pollutant_calendar 的 month 必须为 1-12。")

    day_values = _extract_calendar_day_values(data, year, month)
    if not day_values:
        raise ChartDataError("pollutant_calendar 需要 values 或 records 中包含 date/value。")

    image_base64 = _render_generic_calendar_image(
        title=title,
        year=year,
        month=month,
        pollutant=pollutant,
        unit=unit,
        day_values=day_values,
    )
    visual = _cache_base64_image(image_base64, chart_id or f"pollutant_calendar_{year}_{month}_{pollutant}", title)
    values = list(day_values.values())
    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": [],
        "metadata": {
            "requested_chart_type": "pollutant_calendar",
            "applied_chart_type": "pollutant_calendar",
            "scope": "generic",
            "output_context": output_context,
            "year": year,
            "month": month,
            "pollutant": pollutant,
            "unit": unit,
            "days_in_month": calendar.monthrange(year, month)[1],
            "covered_days": len(day_values),
            "avg_value": f"{sum(values) / len(values):.1f}",
            "max_value": max(values),
            "min_value": min(values),
        },
        "summary": f"报告图表已生成：{title}。",
    }


def _render_generic_pollutant_wind_rose(
    chart_id: str | None,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    pollutant_name = str(normalize_matplotlib_label_text(data.get("pollutant_name") or options.get("pollutant_name") or "污染物"))
    unit = str(normalize_matplotlib_label_text(data.get("unit") or options.get("unit") or "μg/m³"))
    wind_directions = _number_sequence(data.get("wind_directions"))
    wind_speeds = _number_sequence(data.get("wind_speeds"))
    concentrations = _number_sequence(data.get("concentrations"))
    records = _records_from_data(data)
    if not wind_directions and records:
        extracted = _extract_wind_rose_arrays(records, data, options, pollutant_name)
        wind_directions = extracted["wind_directions"]
        wind_speeds = extracted["wind_speeds"]
        concentrations = extracted["concentrations"]

    if not (wind_directions and wind_speeds and concentrations):
        raise ChartDataError("generic_pollutant_wind_rose 需要 wind_directions、wind_speeds、concentrations 或 records。")
    if not (len(wind_directions) == len(wind_speeds) == len(concentrations)):
        raise ChartDataError("generic_pollutant_wind_rose 的风向、风速、浓度长度必须一致。")
    direction_bins = int(options.get("direction_bins") or data.get("direction_bins") or 16)
    direction_bins = min(max(direction_bins, 4), 36)
    image_base64, valid_count = _render_generic_wind_rose_image(
        title=title,
        pollutant_name=pollutant_name,
        unit=unit,
        wind_directions=wind_directions,
        wind_speeds=wind_speeds,
        concentrations=concentrations,
        direction_bins=direction_bins,
    )
    visual = _cache_base64_image(image_base64, chart_id or f"generic_pollutant_wind_rose_{pollutant_name}", title)
    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": [],
        "metadata": {
            "requested_chart_type": "generic_pollutant_wind_rose",
            "applied_chart_type": "generic_pollutant_wind_rose",
            "scope": "generic",
            "output_context": output_context,
            "pollutant_name": pollutant_name,
            "unit": unit,
            "direction_bin_count": direction_bins,
            "valid_point_count": valid_count,
        },
        "summary": f"报告图表已生成：{title}。",
    }


def _records_from_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = data.get("records")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]
    return []


def _normalize_city_data_map(city_data_map: Dict[str, Any]) -> Dict[str, Dict[int, int]]:
    prepared: Dict[str, Dict[int, int]] = {}
    for city, day_map in city_data_map.items():
        if not isinstance(day_map, dict):
            continue
        prepared[str(city)] = {}
        for day, value in day_map.items():
            try:
                prepared[str(city)][int(day)] = int(value)
            except (TypeError, ValueError):
                continue
    return prepared


def _cities_from_records(records: Sequence[Dict[str, Any]]) -> List[str]:
    cities: List[str] = []
    for record in records:
        city = record.get("name") or record.get("city") or record.get("city_name") or record.get("station_name")
        if city and str(city) not in cities:
            cities.append(str(city))
    return cities


def _calendar_statistics(city_data_map: Dict[str, Dict[int, int]], year: int, month: int) -> Dict[str, Any]:
    days_in_month = calendar.monthrange(year, month)[1]
    city_count = len(city_data_map)
    covered_days = sum(len(day_map) for day_map in city_data_map.values())
    total_days = city_count * days_in_month
    values = [value for day_map in city_data_map.values() for value in day_map.values()]
    return {
        "city_count": city_count,
        "days_in_month": days_in_month,
        "covered_days": covered_days,
        "coverage_rate": f"{covered_days / total_days * 100:.1f}%" if total_days else "0.0%",
        "avg_value": f"{sum(values) / len(values):.1f}" if values else "0.0",
        "max_value": max(values) if values else 0,
        "min_value": min(values) if values else 0,
    }


def _extract_calendar_day_values(data: Dict[str, Any], year: int, month: int) -> Dict[int, float]:
    values = data.get("values")
    records = _records_from_data(data)
    items = values if isinstance(values, list) else records
    day_values: Dict[int, float] = {}
    if not isinstance(items, list):
        return day_values
    for item in items:
        if isinstance(item, dict):
            raw_date = item.get("date") or item.get("time") or item.get("timestamp")
            raw_value = item.get("value")
            if raw_value is None:
                raw_value = item.get("concentration") or item.get("aqi") or item.get("AQI")
            parsed_day = _day_from_date(raw_date, year, month)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if parsed_day is not None:
                day_values[parsed_day] = value
        elif isinstance(item, (int, float)):
            day = len(day_values) + 1
            if 1 <= day <= calendar.monthrange(year, month)[1]:
                day_values[day] = float(item)
    return day_values


def _day_from_date(value: Any, year: int, month: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        parsed = value
    else:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.year != year or parsed.month != month:
        return None
    return int(parsed.day)


def _render_generic_calendar_image(
    title: str,
    year: int,
    month: int,
    pollutant: str,
    unit: str,
    day_values: Dict[int, float],
) -> str:
    first_weekday, days_in_month = calendar.monthrange(year, month)
    weeks = math.ceil((first_weekday + days_in_month) / 7)
    grid = np.full((weeks, 7), np.nan)
    for day, value in day_values.items():
        if 1 <= day <= days_in_month:
            index = first_weekday + day - 1
            grid[index // 7, index % 7] = value

    fig, ax = plt.subplots(figsize=(8.2, max(4.2, weeks * 0.72)), dpi=180)
    masked = np.ma.masked_invalid(grid)
    im = ax.imshow(masked, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(7))
    ax.set_xticklabels(["一", "二", "三", "四", "五", "六", "日"], fontsize=10)
    ax.set_yticks(range(weeks))
    ax.set_yticklabels([f"第{i + 1}周" for i in range(weeks)], fontsize=10)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=15, fontweight="bold", pad=12)
    for day in range(1, days_in_month + 1):
        index = first_weekday + day - 1
        row, col = index // 7, index % 7
        value = day_values.get(day)
        text = f"{day}\n{value:g}" if value is not None else f"{day}"
        ax.text(col, row, text, ha="center", va="center", fontsize=9, color="#222")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(-0.5, 7, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, weeks, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", bottom=False, left=False)
    cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02)
    label = f"{pollutant} ({unit})" if unit else pollutant
    cbar.set_label(str(normalize_matplotlib_label_text(label)), fontsize=10)
    fig.tight_layout(pad=1.0)
    return _figure_to_base64(fig)


def _render_generic_wind_rose_image(
    title: str,
    pollutant_name: str,
    unit: str,
    wind_directions: Sequence[float],
    wind_speeds: Sequence[float],
    concentrations: Sequence[float],
    direction_bins: int,
) -> tuple[str, int]:
    valid = [
        (float(direction) % 360, float(speed), float(concentration))
        for direction, speed, concentration in zip(wind_directions, wind_speeds, concentrations)
        if speed >= 0
    ]
    if not valid:
        raise ChartDataError("generic_pollutant_wind_rose 没有可渲染的有效数据点。")

    bin_width = 360 / direction_bins
    means = []
    counts = []
    for index in range(direction_bins):
        start = index * bin_width
        end = start + bin_width
        bin_values = [concentration for direction, _, concentration in valid if start <= direction < end]
        counts.append(len(bin_values))
        means.append(sum(bin_values) / len(bin_values) if bin_values else 0.0)

    theta = np.deg2rad(np.arange(direction_bins) * bin_width + bin_width / 2)
    radii = np.array(means)
    width = np.deg2rad(bin_width * 0.88)
    fig, ax = plt.subplots(figsize=(6.2, 6.2), dpi=180, subplot_kw={"polar": True})
    cmap = plt.get_cmap("YlOrRd")
    vmax = max(means) if any(means) else 1.0
    colors = [cmap(value / vmax if vmax else 0) for value in means]
    ax.bar(theta, radii, width=width, color=colors, edgecolor="white", linewidth=0.8)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_title(str(normalize_matplotlib_label_text(title)), fontsize=14, fontweight="bold", pad=18)
    ax.set_rlabel_position(135)
    ax.tick_params(labelsize=9)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.72, pad=0.1)
    cbar.set_label(str(normalize_matplotlib_label_text(f"{pollutant_name} ({unit})")), fontsize=10)
    ax.text(
        0.5,
        -0.08,
        f"有效点位: {len(valid)}；方向分箱: {direction_bins}",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(pad=1.0)
    return _figure_to_base64(fig), len(valid)


def _extract_wind_rose_arrays(
    records: Sequence[Dict[str, Any]],
    data: Dict[str, Any],
    options: Dict[str, Any],
    pollutant_name: str,
) -> Dict[str, List[Any]]:
    direction_field = data.get("wind_direction_field") or options.get("wind_direction_field")
    speed_field = data.get("wind_speed_field") or options.get("wind_speed_field")
    concentration_field = data.get("concentration_field") or options.get("concentration_field")

    wind_directions: List[float] = []
    wind_speeds: List[float] = []
    concentrations: List[float] = []
    timestamps: List[str] = []

    for record in records:
        try:
            direction = _field_value(record, [direction_field, "wind_direction_10m", "wind_direction", "WD", "wd", "direction", "风向"])
            speed = _field_value(record, [speed_field, "wind_speed_10m", "wind_speed", "WS", "ws", "speed", "风速"])
            concentration = _field_value(
                record,
                [concentration_field, pollutant_name, pollutant_name.replace(".", ""), "concentration", "conc", "浓度"],
            )
            wind_directions.append(float(direction))
            wind_speeds.append(float(speed))
            concentrations.append(float(concentration))
            timestamp = record.get("timestamp") or record.get("time") or record.get("date")
            if timestamp is not None:
                timestamps.append(str(timestamp))
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "wind_directions": wind_directions,
        "wind_speeds": wind_speeds,
        "concentrations": concentrations,
        "timestamps": timestamps,
    }


def _field_value(record: Dict[str, Any], candidates: Sequence[Any]) -> Any:
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in record:
            return record[candidate]
    raise KeyError("missing field")


def _number_sequence(values: Any) -> List[float]:
    if not isinstance(values, list):
        return []
    numbers: List[float] = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _int_option(data: Dict[str, Any], options: Dict[str, Any], key: str) -> int | None:
    value = data.get(key, options.get(key))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cache_base64_image(image_base64: str, chart_id: str, title: str) -> Dict[str, Any]:
    cached = get_image_cache().save(image_base64, chart_id=chart_id)
    return {
        "id": cached["image_id"],
        "image_id": cached["image_id"],
        "title": title,
        "type": "image",
        "url": cached["url"],
        "image_url": cached["url"],
        "local_path": cached["local_path"],
        "size_kb": cached["size_kb"],
    }


def _figure_to_base64(fig) -> str:
    buffer = BytesIO()
    apply_font_to_figure(fig)
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=180)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
