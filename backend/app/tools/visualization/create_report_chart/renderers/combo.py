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


def draw_combo(ax, title: str, data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import (
        _apply_x_tick_labels,
        _line_width,
        _source_font,
    )

    labels = require_labels(data, "combo")
    raw_series = require_series(data, "combo")
    if len(raw_series) > 6:
        raise ChartDataError(f"combo.series 最多支持 6 个系列，当前为 {len(raw_series)} 个。")

    parsed: list[dict[str, Any]] = []
    uses_right_axis = False
    for index, item in enumerate(raw_series):
        path = f"combo.series[{index}]"
        geometry = str(item.get("type") or "").lower()
        if geometry not in {"bar", "line"}:
            raise ChartDataError(f"{path}.type 只允许 bar 或 line。")
        axis_name = str(item.get("axis") or "left").lower()
        if axis_name not in {"left", "right"}:
            raise ChartDataError(f"{path}.axis 只允许 left 或 right。")
        uses_right_axis = uses_right_axis or axis_name == "right"
        raw_stack = item.get("stack")
        stack = str(raw_stack) if raw_stack is not None and str(raw_stack) else None
        if geometry != "bar" and stack is not None:
            raise ChartDataError(f"{path}.stack 仅适用于 bar 系列。")
        parsed.append(
            {
                "name": str(
                    normalize_matplotlib_label_text(item.get("name") or f"系列{index + 1}")
                ),
                "type": geometry,
                "axis": axis_name,
                "stack": stack,
                "values": series_values(item, path, labels),
                "color": str(item.get("color") or PALETTE[index % len(PALETTE)]),
            }
        )

    if not any(item["type"] == "bar" for item in parsed) or not any(
        item["type"] == "line" for item in parsed
    ):
        raise ChartDataError("combo 图必须同时包含至少一个 bar 系列和一个 line 系列。")

    if uses_right_axis:
        left_meaning = (
            options.get("left_y_label")
            or options.get("left_unit")
            or options.get("y_label")
            or options.get("unit")
        )
        right_meaning = (
            options.get("right_y_label")
            or options.get("right_unit")
            or options.get("secondary_y_label")
        )
        if not left_meaning or not right_meaning:
            raise ChartDataError("combo 使用 right 轴时必须提供左右轴标题或单位。")

    right_ax = ax.twinx() if uses_right_axis else None
    axes = {"left": ax, "right": right_ax}
    positions = list(range(len(labels)))
    bar_slot_keys: list[tuple[str, str]] = []
    for index, item in enumerate(parsed):
        if item["type"] != "bar":
            continue
        key = (item["axis"], f"stack:{item['stack']}" if item["stack"] else f"series:{index}")
        if key not in bar_slot_keys:
            bar_slot_keys.append(key)
    width = min(0.72 / max(len(bar_slot_keys), 1), 0.34)
    offset_start = -width * (len(bar_slot_keys) - 1) / 2
    positive_bottoms: dict[tuple[str, str], list[float]] = {}
    negative_bottoms: dict[tuple[str, str], list[float]] = {}
    handles = []
    legend_labels = []

    for index, item in enumerate(parsed):
        target_ax = axes[item["axis"]]
        if item["type"] == "bar":
            key = (item["axis"], f"stack:{item['stack']}" if item["stack"] else f"series:{index}")
            slot_index = bar_slot_keys.index(key)
            offsets = [position + offset_start + slot_index * width for position in positions]
            if item["stack"]:
                positive = positive_bottoms.setdefault(key, [0.0] * len(labels))
                negative = negative_bottoms.setdefault(key, [0.0] * len(labels))
                bottoms = [
                    positive[i] if value >= 0 else negative[i]
                    for i, value in enumerate(item["values"])
                ]
            else:
                bottoms = [0.0] * len(labels)
            artist = target_ax.bar(
                offsets,
                item["values"],
                width=width,
                bottom=bottoms,
                label=item["name"],
                color=item["color"],
                alpha=0.82,
                zorder=2,
            )
            if item["stack"]:
                for value_index, value in enumerate(item["values"]):
                    if value >= 0:
                        positive[value_index] += value
                    else:
                        negative[value_index] += value
            handle = artist
        else:
            (handle,) = target_ax.plot(
                positions,
                item["values"],
                marker="o",
                linewidth=_line_width(options),
                label=item["name"],
                color=item["color"],
                zorder=4,
            )
        handles.append(handle)
        legend_labels.append(item["name"])

    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    normalized_title = str(normalize_matplotlib_label_text(title))
    ax.set_title(normalized_title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--", zorder=0)
    if right_ax is not None:
        right_ax.tick_params(axis="y", labelsize=_source_font(10.5))
    _apply_axis_labels(ax, right_ax, options, _source_font)
    if options.get("legend", True):
        ax.legend(
            handles, legend_labels, fontsize=_source_font(9.2), frameon=False, loc="upper left"
        )

    warnings = list(tick_metadata.pop("layout_warnings", []))
    if len(parsed) > 4:
        warnings.append("combo_many_series")
    if width < 0.18 or len(labels) * len(bar_slot_keys) > 36:
        warnings.append("combo_narrow_bars")
    left_magnitude = max(
        (abs(value) for item in parsed if item["axis"] == "left" for value in item["values"]),
        default=0.0,
    )
    right_magnitude = max(
        (abs(value) for item in parsed if item["axis"] == "right" for value in item["values"]),
        default=0.0,
    )
    if right_ax is not None and (left_magnitude == 0) != (right_magnitude == 0):
        axis_magnitude_ratio: float | str | None = "infinite"
    elif left_magnitude > 0 and right_magnitude > 0:
        axis_magnitude_ratio = max(left_magnitude, right_magnitude) / min(
            left_magnitude, right_magnitude
        )
    else:
        axis_magnitude_ratio = None
    if axis_magnitude_ratio == "infinite" or (
        isinstance(axis_magnitude_ratio, float) and axis_magnitude_ratio >= 100
    ):
        warnings.append("combo_dual_axis_scale_disparity")
    return {
        "series_count": len(parsed),
        "axis_count": 2 if right_ax is not None else 1,
        "axis_series_counts": {
            "left": sum(item["axis"] == "left" for item in parsed),
            "right": sum(item["axis"] == "right" for item in parsed),
        },
        "geometry_types": list(dict.fromkeys(item["type"] for item in parsed)),
        "stack_groups": list(
            dict.fromkeys(
                item["stack"] for item in parsed if item["type"] == "bar" and item["stack"]
            )
        ),
        "bar_slot_count": len(bar_slot_keys),
        "axis_magnitudes": {"left": left_magnitude, "right": right_magnitude},
        "axis_magnitude_ratio": axis_magnitude_ratio,
        "normalized_text": {"title": normalized_title, "series_names": legend_labels},
        "layout_warnings": warnings,
        **tick_metadata,
    }


def draw_pareto(ax, title: str, data: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    from app.tools.visualization.create_report_chart.renderer import _source_font

    labels = require_labels(data, "pareto")
    values = finite_numbers(data.get("values"), "pareto.values", nonnegative=True)
    require_matching_length("pareto.values", values, labels)
    total = sum(values)
    if total <= 0:
        raise ChartDataError("pareto.values 的合计必须大于 0，无法计算累计占比。")
    sort_mode = str(options.get("sort") or "descending").lower()
    if sort_mode not in {"descending", "none"}:
        raise ChartDataError("pareto.options.sort 只允许 descending 或 none。")
    rows = list(zip(labels, values, strict=True))
    if sort_mode == "descending":
        rows.sort(key=lambda item: item[1], reverse=True)
    sorted_labels = [item[0] for item in rows]
    sorted_values = [item[1] for item in rows]
    cumulative_values: list[float] = []
    running = 0.0
    for value in sorted_values:
        running += value
        cumulative_values.append(running)
    cumulative_percentages = [value / total * 100 for value in cumulative_values]
    combo_options = dict(options)
    combo_options.setdefault(
        "left_y_label", options.get("y_label") or options.get("unit") or "数值"
    )
    combo_options.setdefault("right_y_label", "累计占比（%）")
    metadata = draw_combo(
        ax,
        title,
        {
            "labels": sorted_labels,
            "series": [
                {"name": options.get("bar_name") or "数值", "type": "bar", "values": sorted_values},
                {
                    "name": options.get("line_name") or "累计占比",
                    "type": "line",
                    "axis": "right",
                    "values": cumulative_percentages,
                },
            ],
        },
        combo_options,
    )
    right_ax = ax.figure.axes[-1]
    right_ax.set_ylim(0, 105)
    raw_threshold = options.get("threshold_percent")
    threshold = finite_number(
        raw_threshold if raw_threshold is not None else 80,
        "pareto.options.threshold_percent",
    )
    if not 0 <= threshold <= 100:
        raise ChartDataError("pareto.options.threshold_percent 必须在 0 到 100 之间。")
    right_ax.axhline(threshold, color="#8d4b45", linestyle="--", linewidth=1, alpha=0.8)
    right_ax.text(
        0.99,
        threshold,
        f"{threshold:g}%",
        transform=right_ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        fontsize=_source_font(8.8),
        color="#8d4b45",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1},
    )
    metadata.update(
        {
            "sort_mode": sort_mode,
            "sorted_labels": sorted_labels,
            "sorted_values": sorted_values,
            "cumulative_values": cumulative_values,
            "cumulative_percentages": cumulative_percentages,
            "threshold_percent": threshold,
        }
    )
    return metadata


def _apply_axis_labels(ax, right_ax, options: dict[str, Any], source_font) -> None:
    left_label = options.get("left_y_label") or options.get("y_label")
    left_unit = options.get("left_unit") or options.get("unit")
    if left_label or left_unit:
        text = str(left_label or "")
        text = f"{text} ({left_unit})" if text and left_unit else (text or str(left_unit))
        ax.set_ylabel(str(normalize_matplotlib_label_text(text)), fontsize=source_font(11))
    if right_ax is not None:
        right_label = options.get("right_y_label") or options.get("secondary_y_label")
        right_unit = options.get("right_unit")
        if right_label or right_unit:
            text = str(right_label or "")
            text = f"{text} ({right_unit})" if text and right_unit else (text or str(right_unit))
            right_ax.set_ylabel(
                str(normalize_matplotlib_label_text(text)), fontsize=source_font(11)
            )
