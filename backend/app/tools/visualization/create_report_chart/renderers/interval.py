from __future__ import annotations

from typing import Any

from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.tools.visualization.create_report_chart.validation import (
    ChartDataError,
    finite_numbers,
    require_labels,
    require_matching_length,
    require_series,
    series_values,
)

PALETTE = ["#3f7fb5", "#d17a3a"]


def draw_range_line(
    ax, title: str, data: dict[str, Any], options: dict[str, Any]
) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _source_font,
    )

    labels = require_labels(data, "range_line")
    raw_series = require_series(data, "range_line")
    if len(raw_series) > 2:
        raise ChartDataError(f"range_line.series 最多支持 2 个系列，当前为 {len(raw_series)} 个。")
    positions = list(range(len(labels)))
    derived = []
    names = []
    interval_bounds = []
    for index, item in enumerate(raw_series):
        path = f"range_line.series[{index}]"
        values = series_values(item, path, labels)
        lower = finite_numbers(item.get("lower"), f"{path}.lower")
        upper = finite_numbers(item.get("upper"), f"{path}.upper")
        require_matching_length(f"{path}.lower", lower, labels)
        require_matching_length(f"{path}.upper", upper, labels)
        for point_index, (low, value, high) in enumerate(zip(lower, values, upper, strict=True)):
            if low > value:
                raise ChartDataError(
                    f"{path}.lower[{point_index}] 不得大于 values[{point_index}]。"
                )
            if value > high:
                raise ChartDataError(
                    f"{path}.upper[{point_index}] 不得小于 values[{point_index}]。"
                )
        name = str(normalize_matplotlib_label_text(item.get("name") or f"系列{index + 1}"))
        color = PALETTE[index]
        ax.fill_between(positions, lower, upper, color=color, alpha=0.18, zorder=1)
        ax.plot(positions, values, color=color, linewidth=2.1, marker="o", label=name, zorder=3)
        names.append(name)
        derived.append({"name": name, "lower": lower, "values": values, "upper": upper})
        interval_bounds.append((lower, upper))
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    if options.get("legend", True):
        ax.legend(fontsize=_source_font(9.2), frameon=False)
    warnings = list(tick_metadata.pop("layout_warnings", []))
    if len(interval_bounds) == 2 and _interval_overlap_ratio(*interval_bounds) >= 0.75:
        warnings.append("range_intervals_heavily_overlap")
    return {
        "series_count": len(raw_series),
        "axis_count": 1,
        "geometry_types": ["line", "interval_band"],
        "interval_series": derived,
        "normalized_text": {"title": normalized_title, "series_names": names},
        "layout_warnings": warnings,
        **tick_metadata,
    }


def _interval_overlap_ratio(
    first: tuple[list[float], list[float]],
    second: tuple[list[float], list[float]],
) -> float:
    ratios = []
    for low_a, high_a, low_b, high_b in zip(*first, *second, strict=True):
        intersection = max(0.0, min(high_a, high_b) - max(low_a, low_b))
        smaller_width = min(high_a - low_a, high_b - low_b)
        ratios.append(intersection / smaller_width if smaller_width > 0 else 0.0)
    return sum(ratios) / len(ratios) if ratios else 0.0


def draw_error_bar(ax, title: str, data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _source_font,
    )

    labels = require_labels(data, "error_bar")
    raw_series = require_series(data, "error_bar")
    positions = list(range(len(labels)))
    names: list[str] = []
    modes: list[str] = []
    width = min(0.7 / len(raw_series), 0.22)
    offset_start = -width * (len(raw_series) - 1) / 2
    for index, item in enumerate(raw_series):
        path = f"error_bar.series[{index}]"
        values = series_values(item, path, labels)
        errors = item.get("errors")
        lower_raw = item.get("lower_errors")
        upper_raw = item.get("upper_errors")
        if errors is not None and (lower_raw is not None or upper_raw is not None):
            raise ChartDataError(f"{path} 不能同时提供 errors 和非对称误差。")
        if errors is not None:
            yerr: Any = finite_numbers(errors, f"{path}.errors", nonnegative=True)
            require_matching_length(f"{path}.errors", yerr, labels)
            mode = "symmetric"
        else:
            if lower_raw is None or upper_raw is None:
                raise ChartDataError(
                    f"{path} 必须提供 errors，或同时提供 lower_errors 和 upper_errors。"
                )
            lower = finite_numbers(lower_raw, f"{path}.lower_errors", nonnegative=True)
            upper = finite_numbers(upper_raw, f"{path}.upper_errors", nonnegative=True)
            require_matching_length(f"{path}.lower_errors", lower, labels)
            require_matching_length(f"{path}.upper_errors", upper, labels)
            yerr = [lower, upper]
            mode = "asymmetric"
        name = str(normalize_matplotlib_label_text(item.get("name") or f"系列{index + 1}"))
        offsets = [position + offset_start + index * width for position in positions]
        ax.errorbar(
            offsets,
            values,
            yerr=yerr,
            fmt="o",
            capsize=4,
            elinewidth=1.4,
            markersize=5,
            color=PALETTE[index % len(PALETTE)],
            label=name,
        )
        names.append(name)
        modes.append(mode)
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    if options.get("legend", True) and (
        len(raw_series) > 1 or any(item.get("name") for item in raw_series)
    ):
        ax.legend(fontsize=_source_font(9.2), frameon=False)
    return {
        "series_count": len(raw_series),
        "axis_count": 1,
        "geometry_types": ["point", "error_bar"],
        "error_modes": modes,
        "normalized_text": {"title": normalized_title, "series_names": names},
        **tick_metadata,
    }
