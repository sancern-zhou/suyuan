from __future__ import annotations

from typing import Any

from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.tools.visualization.create_report_chart.validation import (
    ChartDataError,
    finite_number,
    finite_numbers,
    require_labels,
    require_matching_length,
    require_series,
    series_values,
)

PALETTE = ["#3f7fb5", "#d17a3a", "#4e9a73", "#8a6bb8", "#c6535f", "#6f8798"]


def draw_waterfall(ax, title: str, data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _source_font,
    )

    labels = require_labels(data, "waterfall")
    values = finite_numbers(data.get("values"), "waterfall.values")
    require_matching_length("waterfall.values", values, labels)
    raw_measures = data.get("measures")
    if raw_measures is None:
        measures = ["relative"] * len(labels)
    else:
        if not isinstance(raw_measures, list):
            raise ChartDataError("waterfall.measures 必须是数组。")
        require_matching_length("waterfall.measures", raw_measures, labels)
        measures = [str(value).lower() for value in raw_measures]
        unknown = [value for value in measures if value not in {"relative", "subtotal", "total"}]
        if unknown:
            raise ChartDataError("waterfall.measures 只允许 relative、subtotal 或 total。")
    has_start = data.get("start_value") is not None
    start = finite_number(data.get("start_value"), "waterfall.start_value", default=0.0)
    show_total = bool(data.get("show_total", options.get("show_total", True)))
    plot_labels: list[str] = []
    plot_values: list[float] = []
    bottoms: list[float] = []
    colors: list[str] = []
    kinds: list[str] = []
    if has_start:
        plot_labels.append(
            str(normalize_matplotlib_label_text(options.get("start_label") or "期初"))
        )
        plot_values.append(start)
        bottoms.append(0.0)
        colors.append("#6f8798")
        kinds.append("start")
    current = start
    cumulative_positions = []
    for label, value, measure in zip(labels, values, measures, strict=True):
        if measure in {"subtotal", "total"}:
            bottom = 0.0
            height = value
            current = value
            color = "#6f8798" if measure == "subtotal" else "#3f7fb5"
            kind = measure
        else:
            bottom = current if value >= 0 else current + value
            height = abs(value)
            current += value
            color = "#4e9a73" if value >= 0 else "#c6535f"
            kind = "increase" if value >= 0 else "decrease"
        plot_labels.append(label)
        plot_values.append(height)
        bottoms.append(bottom)
        colors.append(color)
        kinds.append(kind)
        cumulative_positions.append(current)
    if show_total and (not measures or measures[-1] != "total"):
        plot_labels.append(
            str(normalize_matplotlib_label_text(options.get("total_label") or "合计"))
        )
        plot_values.append(current)
        bottoms.append(0.0)
        colors.append("#3f7fb5")
        kinds.append("total")
    positions = list(range(len(plot_labels)))
    ax.bar(positions, plot_values, bottom=bottoms, color=colors, width=0.62)
    for index in range(len(plot_labels) - 1):
        if kinds[index] in {"start", "subtotal", "total"}:
            level = plot_values[index]
        else:
            level = (
                bottoms[index] + plot_values[index]
                if kinds[index] == "increase"
                else bottoms[index]
            )
        ax.plot(
            [positions[index] + 0.31, positions[index + 1] - 0.31],
            [level, level],
            color="#777",
            linewidth=0.8,
        )
    tick_metadata = _apply_x_tick_labels(ax, positions, plot_labels, options)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.axhline(0, color="#555", linewidth=0.8)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    return {
        "series_count": 1,
        "axis_count": 1,
        "geometry_types": ["bar", "connector_line"],
        "step_count": len(values),
        "start_value": start,
        "cumulative_positions": cumulative_positions,
        "measures": measures,
        "final_value": current,
        "show_total": show_total,
        "bar_kinds": kinds,
        "normalized_text": {"title": normalized_title, "labels": plot_labels},
        **tick_metadata,
    }


def draw_diverging_bar(
    ax, title: str, data: dict[str, Any], options: dict[str, Any]
) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _source_font,
    )

    labels = require_labels(data, "diverging_bar")
    values = finite_numbers(data.get("values"), "diverging_bar.values")
    require_matching_length("diverging_bar.values", values, labels)
    orientation = str(options.get("orientation") or "auto").lower()
    if orientation not in {"auto", "horizontal", "vertical"}:
        raise ChartDataError(
            "diverging_bar.options.orientation 只允许 auto、horizontal 或 vertical。"
        )
    if orientation == "auto":
        orientation = (
            "horizontal"
            if max(len(label) for label in labels) > 10 or len(labels) > 8
            else "vertical"
        )
    colors = ["#4e9a73" if value >= 0 else "#c6535f" for value in values]
    positions = list(range(len(labels)))
    normalized_title = str(normalize_matplotlib_label_text(title))
    if orientation == "horizontal":
        bars = ax.barh(positions, values, color=colors)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.axvline(0, color="#444", linewidth=1)
        ax.grid(axis="x", alpha=0.25, linestyle="--")
        tick_metadata: dict[str, Any] = {"x_tick_label_strategy": {"mode": "numeric"}}
    else:
        bars = ax.bar(positions, values, color=colors)
        ax.axhline(0, color="#444", linewidth=1)
        ax.grid(axis="y", alpha=0.25, linestyle="--")
        tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    for bar, value in zip(bars, values, strict=True):
        if value < 0:
            bar.set_hatch("//")
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    return {
        "series_count": 1,
        "axis_count": 1,
        "geometry_types": ["bar"],
        "orientation": orientation,
        "positive_count": sum(value >= 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
        "normalized_text": {"title": normalized_title, "labels": labels},
        **tick_metadata,
    }


def draw_step_line(ax, title: str, data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _source_font,
    )

    labels = require_labels(data, "step_line")
    where = str(options.get("step") or "post").lower()
    if where not in {"pre", "mid", "post"}:
        raise ChartDataError("step_line.options.step 只允许 pre、mid 或 post。")
    raw_series = data.get("series")
    parsed = []
    if isinstance(raw_series, list) and raw_series:
        require_series(data, "step_line")
        for index, item in enumerate(raw_series):
            parsed.append(
                {
                    "name": str(
                        normalize_matplotlib_label_text(item.get("name") or f"系列{index + 1}")
                    ),
                    "values": series_values(item, f"step_line.series[{index}]", labels),
                }
            )
    else:
        values = finite_numbers(data.get("values") or data.get("y"), "step_line.values")
        require_matching_length("step_line.values", values, labels)
        parsed.append(
            {
                "name": str(normalize_matplotlib_label_text(data.get("name") or "数值")),
                "values": values,
            }
        )
    positions = list(range(len(labels)))
    for index, item in enumerate(parsed):
        ax.step(
            positions,
            item["values"],
            where=where,
            linewidth=2.1,
            label=item["name"],
            color=PALETTE[index % len(PALETTE)],
        )
        ax.plot(
            positions,
            item["values"],
            linestyle="none",
            marker="o",
            markersize=4,
            color=PALETTE[index % len(PALETTE)],
        )
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(alpha=0.25, linestyle="--")
    if options.get("legend", True) and len(parsed) > 1:
        ax.legend(fontsize=_source_font(9.2), frameon=False)
    return {
        "series_count": len(parsed),
        "axis_count": 1,
        "geometry_types": ["line"],
        "step_where": where,
        "normalized_text": {
            "title": normalized_title,
            "series_names": [item["name"] for item in parsed],
        },
        **tick_metadata,
    }
