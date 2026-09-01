from __future__ import annotations

import base64
import math
import textwrap
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from app.services.image_cache import get_image_cache
from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text
from app.tools.visualization.create_report_chart.text_layout import (
    TextLayoutRegistry,
    govern_text_layout,
)
from app.tools.visualization.create_report_chart.validation import ChartDataError
from app.utils.font_utils import (
    apply_font_to_figure,
    chinese_font_prop,
    configure_chinese_font,
)


WORD_TARGET_WIDTH_IN = 5.8
WORD_SOURCE_WIDTH_IN = 8.2
WORD_SOURCE_HEIGHT_IN = 5.2
LEGEND_MAX_COLUMNS = 4
LEGEND_MAX_RESERVED_FRACTION = 0.26
GENERAL_CHART_TYPES = {
    "bar",
    "horizontal_bar",
    "line",
    "scatter",
    "pie",
    "stacked_area",
    "dual_axis_line",
    "stacked_bar",
    "percent_stacked_bar",
    "histogram",
    "correlation_heatmap",
    "boxplot",
    "combo",
    "range_line",
    "waterfall",
    "pareto",
    "diverging_bar",
    "step_line",
    "error_bar",
}
SPECIALIZED_CHART_TYPES = {
    "aqi_calendar",
    "pollutant_wind_rose",
    "pollutant_calendar",
    "generic_pollutant_wind_rose",
    "wind_timeseries",
    "weather_timeseries",
    "henan_city_map",
}
CHART_TYPE_ALIASES = {"timeseries": "line"}


def render_report_chart(
    chart_id: str | None,
    chart_type: str,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    if isinstance(data.get("charts"), list) and len(data["charts"]) > 1:
        return _render_split_charts(chart_id, title, data["charts"], output_context, style_profile, options)

    return _render_single_chart(
        chart_id=chart_id,
        chart_type=chart_type,
        title=title,
        data=data,
        output_context=output_context,
        style_profile=style_profile,
        options=options,
    )


def _render_split_charts(
    chart_id: str | None,
    title: str,
    charts: Sequence[Dict[str, Any]],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    visuals: List[Dict[str, Any]] = []
    child_results: List[Dict[str, Any]] = []
    base_id = _safe_chart_id(chart_id or title)
    for index, chart in enumerate(charts, start=1):
        child = _render_single_chart(
            chart_id=f"{base_id}_{index}",
            chart_type=str(chart.get("chart_type") or "bar"),
            title=str(chart.get("title") or f"{title} {index}"),
            data=dict(chart.get("data") or {}),
            output_context=output_context,
            style_profile=style_profile,
            options=options,
        )
        child_results.append(child)
        visuals.extend(child.get("visuals", []))

    warnings = ["split_complex_multi_chart_request"]
    for child in child_results:
        warnings.extend(child.get("layout_warnings", []))

    return {
        "chart_id": base_id,
        "title": title,
        "visuals": visuals,
        "layout_warnings": _dedupe(warnings),
        "metadata": {
            "render_strategy": "split_images",
            "image_count": len(visuals),
            "child_charts": [
                {
                    "chart_id": child.get("chart_id"),
                    "applied_chart_type": child.get("metadata", {}).get("applied_chart_type"),
                    "text_layout": child.get("metadata", {}).get("text_layout"),
                }
                for child in child_results
            ],
        },
        "summary": f"报告图表已拆分为 {len(visuals)} 张图片，避免复杂子图挤在同一张图中。",
    }


def _render_single_chart(
    chart_id: str | None,
    chart_type: str,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    warnings: List[str] = []
    applied_chart_type = _normalize_chart_type(chart_type)
    labels = _string_list(data.get("labels") or data.get("categories") or data.get("x") or [])

    if applied_chart_type == "bar":
        if _has_long_labels(labels):
            applied_chart_type = "horizontal_bar"
            warnings.append("long_labels_horizontal_bar")
        elif _has_crowded_categorical_labels(labels, output_context):
            applied_chart_type = "horizontal_bar"
            warnings.append("crowded_categorical_labels_horizontal_bar")

    if applied_chart_type in SPECIALIZED_CHART_TYPES:
        from app.tools.visualization.create_report_chart.specialized import render_specialized_chart

        return render_specialized_chart(
            chart_id=chart_id,
            chart_type=applied_chart_type,
            title=title,
            data=data,
            output_context=output_context,
            style_profile=style_profile,
            options=options,
        )
    if applied_chart_type not in GENERAL_CHART_TYPES:
        raise ChartDataError(f"不支持的 chart_type：{chart_type}。")

    fig, ax = _create_figure(output_context, style_profile)
    try:
        return _render_general_chart_figure(
            fig=fig,
            ax=ax,
            chart_id=chart_id,
            chart_type=chart_type,
            applied_chart_type=applied_chart_type,
            title=title,
            data=data,
            output_context=output_context,
            style_profile=style_profile,
            options=options,
            warnings=warnings,
        )
    finally:
        plt.close(fig)


def _render_general_chart_figure(
    fig,
    ax,
    chart_id: str | None,
    chart_type: str,
    applied_chart_type: str,
    title: str,
    data: Dict[str, Any],
    output_context: str,
    style_profile: str,
    options: Dict[str, Any],
    warnings: List[str],
) -> Dict[str, Any]:
    text_registry = TextLayoutRegistry()
    _apply_fonts()
    metadata = {
        "requested_chart_type": chart_type,
        "applied_chart_type": applied_chart_type,
        "output_context": output_context,
        "source_width_in": WORD_SOURCE_WIDTH_IN if output_context == "word" else 7.2,
        "target_width_in": WORD_TARGET_WIDTH_IN if output_context == "word" else None,
        "estimated_final_label_font_pt": 11,
    }

    if applied_chart_type == "horizontal_bar":
        draw_metadata = _draw_horizontal_bar(ax, title, data, options)
    elif applied_chart_type == "bar":
        draw_metadata = _draw_bar(ax, title, data, options)
    elif applied_chart_type == "line":
        draw_metadata = _draw_line(ax, title, data, options)
    elif applied_chart_type == "scatter":
        draw_metadata = _draw_scatter(ax, title, data, options)
    elif applied_chart_type == "pie":
        pie_warnings, pie_metadata = _draw_pie(ax, title, data, options, text_registry)
        warnings.extend(pie_warnings)
        draw_metadata = pie_metadata
    elif applied_chart_type == "stacked_area":
        draw_metadata = _draw_stacked_area(ax, title, data, options)
    elif applied_chart_type == "dual_axis_line":
        draw_metadata = _draw_dual_axis_line(ax, title, data, options)
    elif applied_chart_type == "stacked_bar":
        draw_metadata = _draw_stacked_bar(ax, title, data, options, percent=False)
    elif applied_chart_type == "percent_stacked_bar":
        draw_metadata = _draw_stacked_bar(ax, title, data, options, percent=True)
    elif applied_chart_type == "histogram":
        draw_metadata = _draw_histogram(ax, title, data, options)
    elif applied_chart_type == "correlation_heatmap":
        draw_metadata = _draw_correlation_heatmap(fig, ax, title, data, options)
    elif applied_chart_type == "boxplot":
        draw_metadata = _draw_boxplot(ax, title, data, options)
    elif applied_chart_type in {"combo", "pareto"}:
        from app.tools.visualization.create_report_chart.renderers.combo import draw_combo, draw_pareto

        draw_metadata = (
            draw_combo(ax, title, data, options)
            if applied_chart_type == "combo"
            else draw_pareto(ax, title, data, options)
        )
    elif applied_chart_type in {"range_line", "error_bar"}:
        from app.tools.visualization.create_report_chart.renderers.interval import draw_error_bar, draw_range_line

        draw_metadata = (
            draw_range_line(ax, title, data, options)
            if applied_chart_type == "range_line"
            else draw_error_bar(ax, title, data, options)
        )
    elif applied_chart_type in {"waterfall", "diverging_bar", "step_line"}:
        from app.tools.visualization.create_report_chart.renderers.analytical import (
            draw_diverging_bar,
            draw_step_line,
            draw_waterfall,
        )

        analytical_renderers = {
            "waterfall": draw_waterfall,
            "diverging_bar": draw_diverging_bar,
            "step_line": draw_step_line,
        }
        draw_metadata = analytical_renderers[applied_chart_type](ax, title, data, options)
    else:
        _draw_specialized_placeholder(ax, title, applied_chart_type, data)
        draw_metadata = {"renderer_note": "specialized_type_placeholder"}

    metadata.update(draw_metadata)
    warnings.extend(draw_metadata.get("layout_warnings", []))
    option_warnings, option_metadata = _apply_common_options(ax, options, text_registry)
    warnings.extend(option_warnings)
    if "normalized_text" in option_metadata:
        metadata.setdefault("normalized_text", {}).update(option_metadata.pop("normalized_text"))
    metadata.update(option_metadata)

    legend_layout = _position_legends_below_plot(fig)
    metadata["legend_layout"] = legend_layout
    layout_rect = (0.0, legend_layout["reserved_bottom_fraction"], 1.0, 1.0)
    try:
        fig.tight_layout(pad=1.1, rect=layout_rect)
    except Exception:
        warnings.append("tight_layout_failed")

    layout_warnings, text_layout_metadata = govern_text_layout(
        fig,
        text_registry,
        output_context=output_context,
    )
    warnings.extend(layout_warnings)
    metadata["text_layout"] = text_layout_metadata

    visual = _cache_figure(fig, chart_id or title, title)

    return {
        "chart_id": visual["image_id"],
        "title": title,
        "visuals": [visual],
        "layout_warnings": _dedupe(warnings),
        "metadata": metadata,
        "summary": _summary(title, warnings),
    }


def _create_figure(output_context: str, style_profile: str):
    if output_context == "word":
        width = WORD_SOURCE_WIDTH_IN
        height = WORD_SOURCE_HEIGHT_IN if style_profile != "compact" else 4.4
    else:
        width = 7.2
        height = 4.6
    return plt.subplots(figsize=(width, height), dpi=180)


def _apply_fonts() -> None:
    configure_chinese_font()


def select_chinese_font() -> str | None:
    font_prop = chinese_font_prop()
    if font_prop is None:
        return None
    try:
        from matplotlib import font_manager

        return font_manager.findfont(font_prop, fallback_to_default=False)
    except Exception:
        return None


def _chinese_font_prop():
    return chinese_font_prop()


def _apply_font_to_figure(fig) -> None:
    for text in fig.findobj(match=lambda obj: hasattr(obj, "set_fontproperties")):
        try:
            if hasattr(text, "get_text") and hasattr(text, "set_text"):
                text.set_text(str(normalize_matplotlib_label_text(text.get_text())))
        except Exception:
            continue
    apply_font_to_figure(fig)


def _source_font(final_pt: float) -> float:
    return final_pt * WORD_SOURCE_WIDTH_IN / WORD_TARGET_WIDTH_IN


def _line_width(options: Dict[str, Any], default: float = 2.0) -> float:
    value = options.get("line_width", default)
    try:
        width = float(value)
    except (TypeError, ValueError) as exc:
        raise ChartDataError("line_width 必须是正数。") from exc
    if not math.isfinite(width) or width <= 0:
        raise ChartDataError("line_width 必须是正数。")
    return width


def _position_legends_below_plot(fig) -> Dict[str, Any]:
    """Move axes legends into a measured band below the plotting area."""
    legends = []
    for axis_index, ax in enumerate(fig.axes):
        legend = ax.get_legend()
        if legend is None or not legend.get_visible() or not legend.get_texts():
            continue
        legends.append((axis_index, ax, legend))

    if not legends:
        return {
            "position": "none",
            "legend_count": 0,
            "reserved_bottom_fraction": 0.0,
            "items": [],
        }

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    next_anchor = 0.015
    items = []
    for axis_index, ax, legend in legends:
        handles = list(legend.legend_handles)
        labels = [text.get_text() for text in legend.get_texts()]
        item_count = len(labels)
        columns = min(LEGEND_MAX_COLUMNS, item_count)
        legend_options = {
            "fontsize": min(float(text.get_fontsize()) for text in legend.get_texts()),
            "frameon": legend.get_frame_on(),
            "loc": "lower center",
            "bbox_to_anchor": (0.5, next_anchor),
            "bbox_transform": fig.transFigure,
            "borderaxespad": 0.0,
            "ncol": columns,
        }
        title = legend.get_title().get_text()
        if title:
            legend_options["title"] = title
        legend.remove()
        legend = ax.legend(handles, labels, **legend_options)
        legend.set_in_layout(False)
        fig.canvas.draw()

        bbox = legend.get_window_extent(renderer=renderer)
        height_fraction = bbox.height / max(float(fig.bbox.height), 1.0)
        next_anchor += height_fraction + 0.012
        items.append(
            {
                "axis_index": axis_index,
                "item_count": item_count,
                "columns": columns,
            }
        )

    required_fraction = next_anchor + 0.015
    return {
        "position": "outside_bottom",
        "legend_count": len(legends),
        "reserved_bottom_fraction": min(
            LEGEND_MAX_RESERVED_FRACTION,
            required_fraction,
        ),
        "required_bottom_fraction": required_fraction,
        "items": items,
    }


def _apply_x_tick_labels(ax, positions: Sequence[int], labels: Sequence[str], options: Dict[str, Any]) -> Dict[str, Any]:
    normalized_labels = [str(normalize_matplotlib_label_text(label)) for label in labels]
    original_count = len(normalized_labels)
    max_labels = int(options.get("max_x_tick_labels") or 12)

    if original_count > max_labels:
        interval = math.ceil(original_count / max_labels)
        shown_positions = [pos for index, pos in enumerate(positions) if index % interval == 0]
        shown_labels = [label for index, label in enumerate(normalized_labels) if index % interval == 0]
        if positions and positions[-1] not in shown_positions:
            shown_positions.append(positions[-1])
            shown_labels.append(normalized_labels[-1])
        ax.set_xticks(shown_positions)
        ax.set_xticklabels(shown_labels)
        return {
            "x_tick_label_strategy": {
                "mode": "thinned",
                "original_count": original_count,
                "shown_count": len(shown_labels),
                "interval": interval,
            },
            "layout_warnings": ["dense_x_tick_labels_thinned"],
        }

    ax.set_xticks(list(positions))
    ax.set_xticklabels(normalized_labels)
    return {
        "x_tick_label_strategy": {
            "mode": "all",
            "original_count": original_count,
            "shown_count": original_count,
            "interval": 1,
        }
    }


def _normalized_text_metadata(title: str, series: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "title": str(normalize_matplotlib_label_text(title)),
        "series_names": [str(item.get("name") or "") for item in series],
    }


def _draw_bar(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    labels, series = _extract_labeled_series(data, "bar")
    positions = list(range(len(labels)))
    title = str(normalize_matplotlib_label_text(title))
    if len(series) == 1:
        ax.bar(positions, series[0]["values"], color="#3f7fb5", label=series[0]["name"])
        bar_mode = "single"
    else:
        width = min(0.8 / len(series), 0.32)
        offset_start = -width * (len(series) - 1) / 2
        for index, item in enumerate(series):
            offsets = [pos + offset_start + index * width for pos in positions]
            ax.bar(offsets, item["values"], width=width, label=item["name"])
        bar_mode = "grouped"
        if options.get("legend", True):
            ax.legend(fontsize=_source_font(9.5), frameon=False)
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    return {
        "series_count": len(series),
        "bar_mode": bar_mode,
        "normalized_text": _normalized_text_metadata(title, series),
        **tick_metadata,
    }


def _draw_horizontal_bar(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    labels, series = _extract_labeled_series(data, "horizontal_bar")
    title = str(normalize_matplotlib_label_text(title))
    wrapped = [_wrap_label(str(normalize_matplotlib_label_text(label)), width=16) for label in labels]
    y_positions = list(range(len(wrapped)))

    if len(series) == 1:
        ax.barh(y_positions, series[0]["values"], color="#3f7fb5", label=series[0]["name"])
        bar_mode = "horizontal"
    else:
        height = min(0.8 / len(series), 0.32)
        offset_start = -height * (len(series) - 1) / 2
        for index, item in enumerate(series):
            offsets = [pos + offset_start + index * height for pos in y_positions]
            ax.barh(offsets, item["values"], height=height, label=item["name"])
        bar_mode = "grouped_horizontal"
        if options.get("legend", True):
            ax.legend(fontsize=_source_font(9.5), frameon=False)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(wrapped, fontsize=_source_font(10.5))
    ax.invert_yaxis()
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="x", labelsize=_source_font(10.5))
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    if len(series) == 1:
        for y, value in zip(y_positions, series[0]["values"]):
            ax.text(value, y, f" {value:g}", va="center", fontsize=_source_font(10))
    return {
        "series_count": len(series),
        "bar_mode": bar_mode,
        "normalized_text": _normalized_text_metadata(title, series),
    }


def _draw_line(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    x, series = _extract_labeled_series(data, "line")
    title = str(normalize_matplotlib_label_text(title))
    positions = list(range(len(x)))
    for index, item in enumerate(series):
        ax.plot(positions, item["values"], marker="o", linewidth=_line_width(options), label=item["name"])
    tick_metadata = _apply_x_tick_labels(ax, positions, x, options)
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(alpha=0.25, linestyle="--")
    if len(series) > 1 and options.get("legend", True):
        ax.legend(fontsize=_source_font(9.5), frameon=False)
    return {
        "series_count": len(series),
        "normalized_text": _normalized_text_metadata(title, series),
        **tick_metadata,
    }


def _draw_stacked_area(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    labels, series = _extract_labeled_series(data, "stacked_area")
    if len(series) < 2:
        raise ChartDataError("stacked_area 需要至少两个 series。")
    positions = list(range(len(labels)))
    title = str(normalize_matplotlib_label_text(title))
    ax.stackplot(positions, [item["values"] for item in series], labels=[item["name"] for item in series], alpha=0.82)
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    if options.get("legend", True):
        ax.legend(fontsize=_source_font(9.2), frameon=False, loc="upper left")
    return {
        "series_count": len(series),
        "stack_mode": "area",
        "normalized_text": _normalized_text_metadata(title, series),
        **tick_metadata,
    }


def _draw_dual_axis_line(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    labels = _string_list(data.get("labels") or data.get("categories") or data.get("x") or [])
    raw_series = data.get("series")
    if not labels or not isinstance(raw_series, list) or len(raw_series) < 2:
        raise ChartDataError("dual_axis_line 需要 labels 和至少两个 series。")
    positions = list(range(len(labels)))
    title = str(normalize_matplotlib_label_text(title))
    right_ax = ax.twinx()
    axis_counts = {"left": 0, "right": 0}
    normalized_series: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_series, start=1):
        if not isinstance(item, dict):
            raise ChartDataError(f"dual_axis_line 图 series[{index - 1}] 必须是对象。")
        raw_values = item.get("data")
        if raw_values is None:
            raw_values = item.get("values")
        values = _number_list(raw_values or [])
        _validate_xy_lengths("dual_axis_line", labels, values)
        name = str(normalize_matplotlib_label_text(item.get("name") or f"系列{index}"))
        axis_name = str(item.get("axis") or item.get("y_axis") or ("right" if index == 2 else "left")).lower()
        axis_name = "right" if axis_name in {"right", "secondary", "y2"} else "left"
        target_ax = right_ax if axis_name == "right" else ax
        target_ax.plot(positions, values, marker="o", linewidth=_line_width(options), label=name)
        axis_counts[axis_name] += 1
        normalized_series.append({"name": name, "values": values})
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    left_y_label = options.get("left_y_label") or options.get("y_label")
    right_y_label = options.get("right_y_label") or options.get("secondary_y_label")
    normalized_text = _normalized_text_metadata(title, normalized_series)
    if left_y_label:
        normalized_left = str(normalize_matplotlib_label_text(left_y_label))
        ax.set_ylabel(normalized_left, fontsize=_source_font(11))
        normalized_text["left_y_label"] = normalized_left
    if right_y_label:
        normalized_right = str(normalize_matplotlib_label_text(right_y_label))
        right_ax.set_ylabel(normalized_right, fontsize=_source_font(11))
        normalized_text["right_y_label"] = normalized_right
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    right_ax.tick_params(axis="y", labelsize=_source_font(10.5))
    ax.grid(alpha=0.25, linestyle="--")
    if options.get("legend", True):
        handles, legend_labels = [], []
        for legend_ax in (ax, right_ax):
            ax_handles, ax_labels = legend_ax.get_legend_handles_labels()
            handles.extend(ax_handles)
            legend_labels.extend(ax_labels)
        ax.legend(handles, legend_labels, fontsize=_source_font(9.2), frameon=False, loc="upper left")
    return {
        "series_count": len(normalized_series),
        "axis_series_counts": axis_counts,
        "normalized_text": normalized_text,
        **tick_metadata,
    }


def _draw_scatter(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    x = _number_list(data.get("x") or [])
    y = _number_list(data.get("y") or [])
    _validate_xy_lengths("scatter", x, y)
    ax.scatter(x, y, color="#5b6fb2", alpha=0.8)
    title = str(normalize_matplotlib_label_text(title))
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(alpha=0.25, linestyle="--")
    return {"series_count": 1, "normalized_text": {"title": title}}


def _draw_pie(
    ax,
    title: str,
    data: Dict[str, Any],
    options: Dict[str, Any],
    text_registry: TextLayoutRegistry,
):
    labels = _string_list(data.get("labels") or [])
    labels = [str(normalize_matplotlib_label_text(label)) for label in labels]
    values = _number_list(data.get("values") or [])
    _validate_xy_lengths("pie", labels, values)
    total = sum(values) or 1
    shares = [value / total for value in values]
    warnings: List[str] = []
    metadata = {"label_strategy": "inside"}

    outside = any(share < 0.05 for share in shares) or len(labels) > 4
    if outside:
        warnings.append("pie_small_slices_outside_labels")
        metadata["label_strategy"] = "outside_leader_lines"

    wedges, _ = ax.pie(values, startangle=90, labels=None)
    ax.axis("equal")
    title = str(normalize_matplotlib_label_text(title))
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    for index, (wedge, label, value, share) in enumerate(zip(wedges, labels, values, shares)):
        angle = (wedge.theta2 + wedge.theta1) / 2
        x = math.cos(math.radians(angle))
        y = math.sin(math.radians(angle))
        text = f"{label} {share * 100:.1f}%"
        if outside:
            annotation = ax.annotate(
                text,
                xy=(x * 0.85, y * 0.85),
                xytext=(1.25 * (1 if x >= 0 else -1), 1.18 * y),
                ha="left" if x >= 0 else "right",
                va="center",
                arrowprops={"arrowstyle": "-", "color": "#666", "lw": 0.8},
                fontsize=_source_font(9.8),
            )
            text_registry.register(
                annotation,
                role="pie_label",
                domain=f"pie_labels:{'right' if x >= 0 else 'left'}",
                priority=share,
                payload={
                    "index": index,
                    "label": label,
                    "value": value,
                    "share": share,
                    "placement": "outside",
                    "side": 1 if x >= 0 else -1,
                    "desired_y": 1.18 * y,
                },
            )
        else:
            pie_text = ax.text(
                0.62 * x,
                0.62 * y,
                text,
                ha="center",
                va="center",
                fontsize=_source_font(9.8),
            )
            text_registry.register(
                pie_text,
                role="pie_label",
                domain="pie_labels:inside",
                priority=share,
                payload={
                    "index": index,
                    "label": label,
                    "value": value,
                    "share": share,
                    "placement": "inside",
                    "side": 1 if x >= 0 else -1,
                    "desired_y": 0.62 * y,
                },
            )
    metadata["normalized_text"] = {"title": title}
    return warnings, metadata


def _draw_stacked_bar(ax, title: str, data: Dict[str, Any], options: Dict[str, Any], percent: bool) -> Dict[str, Any]:
    labels, series = _extract_labeled_series(data, "percent_stacked_bar" if percent else "stacked_bar")
    if len(series) < 2:
        raise ChartDataError("stacked_bar 需要至少两个 series。")
    positions = list(range(len(labels)))
    values_by_series = [list(item["values"]) for item in series]
    category_totals = [sum(values[index] for values in values_by_series) for index in range(len(labels))]
    plot_values = values_by_series
    if percent:
        plot_values = [
            [(value / category_totals[index] * 100) if category_totals[index] else 0.0 for index, value in enumerate(values)]
            for values in values_by_series
        ]
    bottoms = [0.0 for _ in labels]
    for item, values in zip(series, plot_values):
        ax.bar(positions, values, bottom=bottoms, label=item["name"])
        bottoms = [current + value for current, value in zip(bottoms, values)]
    tick_metadata = _apply_x_tick_labels(ax, positions, labels, options)
    title = str(normalize_matplotlib_label_text(title))
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    if percent:
        ax.set_ylim(0, 100)
        ax.set_ylabel("占比 (%)", fontsize=_source_font(11))
    if options.get("legend", True):
        ax.legend(fontsize=_source_font(9.2), frameon=False)
    return {
        "series_count": len(series),
        "stack_mode": "percent" if percent else "absolute",
        "category_totals": [float(value) for value in category_totals],
        "normalized_text": _normalized_text_metadata(title, series),
        **tick_metadata,
    }


def _draw_histogram(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    values = _number_list(data.get("values") or data.get("data") or [])
    if not values:
        raise ChartDataError("histogram 需要非空 values。")
    bins = options.get("bins") or data.get("bins") or "auto"
    if isinstance(bins, str):
        bins_arg: Any = bins
    else:
        try:
            bins_arg = max(1, int(bins))
        except (TypeError, ValueError):
            bins_arg = "auto"
    counts, _, _ = ax.hist(values, bins=bins_arg, color="#4f7fa8", alpha=0.82, edgecolor="white")
    title = str(normalize_matplotlib_label_text(title))
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    return {
        "sample_count": len(values),
        "bin_count": int(len(counts)),
        "normalized_text": {"title": title},
    }


def _draw_correlation_heatmap(fig, ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    labels = _string_list(data.get("labels") or data.get("variables") or [])
    matrix = _number_matrix(data.get("matrix") or data.get("values") or [])
    if not labels:
        raise ChartDataError("correlation_heatmap 需要非空 labels。")
    if len(matrix) != len(labels) or any(len(row) != len(labels) for row in matrix):
        raise ChartDataError("correlation_heatmap 需要与 labels 长度一致的方阵 matrix。")

    normalized_labels = [str(normalize_matplotlib_label_text(label)) for label in labels]
    title = str(normalize_matplotlib_label_text(title))
    im = ax.imshow(matrix, cmap=str(options.get("cmap") or "RdBu_r"), vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(normalized_labels)))
    ax.set_yticks(range(len(normalized_labels)))
    ax.set_xticklabels(normalized_labels, fontsize=_source_font(10))
    ax.set_yticklabels(normalized_labels, fontsize=_source_font(10))
    ax.tick_params(axis="x", rotation=45)
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)

    annotated_cells = 0
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            ax.text(
                column_index,
                row_index,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=_source_font(8.6),
                fontweight="bold",
                color="white" if abs(value) >= 0.5 else "black",
            )
            annotated_cells += 1

    colorbar = fig.colorbar(im, ax=ax, shrink=0.86, pad=0.03)
    colorbar.set_label(str(normalize_matplotlib_label_text(options.get("colorbar_label") or "相关系数")), fontsize=_source_font(10))
    colorbar.ax.tick_params(labelsize=_source_font(8.5))
    return {
        "matrix_shape": [len(matrix), len(matrix[0]) if matrix else 0],
        "annotated_cells": annotated_cells,
        "color_scale": [-1, 1],
        "normalized_text": {"title": title, "labels": normalized_labels},
    }


def _draw_boxplot(ax, title: str, data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    groups = data.get("groups")
    labels: List[str] = []
    values: List[List[float]] = []
    if isinstance(groups, list) and groups:
        for index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                raise ChartDataError(f"boxplot 图 groups[{index - 1}] 必须是对象。")
            group_values = _number_list(group.get("values") or group.get("data") or [])
            if not group_values:
                raise ChartDataError(f"boxplot 图 groups[{index - 1}] 需要非空 values。")
            labels.append(str(normalize_matplotlib_label_text(group.get("name") or f"组{index}")))
            values.append(group_values)
    else:
        labels = [str(normalize_matplotlib_label_text(label)) for label in _string_list(data.get("labels") or [])]
        raw_values = data.get("values") or []
        if isinstance(raw_values, list):
            values = [_number_list(item) for item in raw_values if isinstance(item, list)]
        if not labels or len(labels) != len(values):
            raise ChartDataError("boxplot 需要 groups[{name, values}]，或等长 labels + values二维数组。")

    title = str(normalize_matplotlib_label_text(title))
    ax.boxplot(values, tick_labels=labels, patch_artist=True, showmeans=True)
    for patch in ax.patches:
        patch.set_facecolor("#dbe9f5")
        patch.set_edgecolor("#3f7fb5")
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.tick_params(axis="both", labelsize=_source_font(10.5))
    if sum(len(label) for label in labels) > 36:
        ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    return {
        "group_count": len(values),
        "sample_counts": [len(group_values) for group_values in values],
        "normalized_text": {"title": title, "labels": labels},
    }


def _draw_specialized_placeholder(ax, title: str, chart_type: str, data: Dict[str, Any]) -> None:
    ax.axis("off")
    ax.set_title(title, fontsize=_source_font(15), fontweight="bold", pad=14)
    ax.text(
        0.5,
        0.5,
        f"{chart_type}\n通过 create_report_chart 统一入口路由",
        ha="center",
        va="center",
        fontsize=_source_font(12),
    )


def _layout_warnings(fig) -> List[str]:
    warnings: List[str] = []
    try:
        _apply_font_to_figure(fig)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        text_boxes = []
        for text in fig.findobj(match=lambda obj: hasattr(obj, "get_text")):
            if not text.get_visible() or not str(text.get_text()).strip():
                continue
            bbox = text.get_window_extent(renderer=renderer)
            if bbox.width > 0 and bbox.height > 0:
                text_boxes.append(bbox)
        if len(text_boxes) > 45:
            warnings.append("high_text_density")
        for ax in fig.axes:
            if _has_overlapping_text_boxes(ax.get_xticklabels(), renderer, axis="x"):
                warnings.append("x_tick_label_overlap_detected")
            if _has_overlapping_text_boxes(ax.get_yticklabels(), renderer, axis="y"):
                warnings.append("y_tick_label_overlap_detected")
    except Exception:
        warnings.append("layout_check_failed")
    return warnings


def _cache_figure(fig, chart_id: str, title: str) -> Dict[str, Any]:
    buffer = BytesIO()
    _apply_font_to_figure(fig)
    visible_legends = [
        legend
        for ax in fig.axes
        if (legend := ax.get_legend()) is not None and legend.get_visible()
    ]
    fig.savefig(
        buffer,
        format="png",
        bbox_inches="tight",
        bbox_extra_artists=visible_legends,
        dpi=180,
    )
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    image_id = _safe_chart_id(chart_id)
    cached = get_image_cache().save(encoded, chart_id=image_id)
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


def _summary(title: str, warnings: Sequence[str]) -> str:
    if warnings:
        return f"报告图表已生成：{title}；已应用版面治理，警告：{', '.join(_dedupe(warnings))}。"
    return f"报告图表已生成：{title}。"


def _has_long_labels(labels: Sequence[str]) -> bool:
    return any(len(label) > 12 for label in labels) or sum(len(label) for label in labels) > 60


def _has_crowded_categorical_labels(labels: Sequence[str], output_context: str) -> bool:
    if len(labels) < 10:
        return False

    normalized_labels = [str(normalize_matplotlib_label_text(label)) for label in labels]
    label_lengths = [len(label) for label in normalized_labels if label]
    if not label_lengths:
        return False

    target_width = WORD_TARGET_WIDTH_IN if output_context == "word" else 7.2
    slot_width = target_width / max(len(labels), 1)
    widest_label_width = max(label_lengths) * 0.14 + 0.08
    average_label_width = (sum(label_lengths) / len(label_lengths)) * 0.14 + 0.08

    return (
        widest_label_width > slot_width * 0.9
        or (len(labels) >= 16 and average_label_width > slot_width * 0.72)
    )


def _has_overlapping_text_boxes(labels: Sequence[Any], renderer: Any, axis: str) -> bool:
    boxes = []
    for label in labels:
        try:
            if not label.get_visible() or not str(label.get_text()).strip():
                continue
            bbox = label.get_window_extent(renderer=renderer)
        except Exception:
            continue
        if bbox.width > 0 and bbox.height > 0:
            boxes.append(bbox)

    if len(boxes) < 2:
        return False

    key = (lambda box: box.x0) if axis == "x" else (lambda box: box.y0)
    sorted_boxes = sorted(boxes, key=key)
    return any(left.overlaps(right) for left, right in zip(sorted_boxes, sorted_boxes[1:]))


def _wrap_label(label: str, width: int) -> str:
    if len(label) <= width:
        return label
    return "\n".join(textwrap.wrap(label, width=width, break_long_words=True))


def _string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def _number_list(values: Any) -> List[float]:
    if not isinstance(values, list):
        return []
    numbers: List[float] = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            numbers.append(0.0)
    return numbers


def _number_matrix(values: Any) -> List[List[float]]:
    if not isinstance(values, list):
        return []
    matrix: List[List[float]] = []
    for row in values:
        if not isinstance(row, list):
            return []
        matrix.append(_number_list(row))
    return matrix


def _extract_labels_values(data: Dict[str, Any]) -> tuple[List[str], List[float]]:
    labels = _string_list(data.get("labels") or data.get("categories") or data.get("x") or [])
    raw_values = data.get("values") or data.get("y")
    if raw_values is None:
        series = data.get("series")
        if isinstance(series, list) and len(series) == 1 and isinstance(series[0], dict):
            raw_values = series[0].get("data")
            if raw_values is None:
                raw_values = series[0].get("values")
    values = _number_list(raw_values or [])
    return labels, values


def _extract_labeled_series(data: Dict[str, Any], chart_type: str) -> tuple[List[str], List[Dict[str, Any]]]:
    labels = _string_list(data.get("labels") or data.get("categories") or data.get("x") or [])
    series = data.get("series")
    parsed: List[Dict[str, Any]] = []

    if isinstance(series, list) and series:
        for index, item in enumerate(series, start=1):
            if not isinstance(item, dict):
                raise ChartDataError(f"{chart_type} 图 series[{index - 1}] 必须是对象。")
            raw_values = item.get("data")
            if raw_values is None:
                raw_values = item.get("values")
            values = _number_list(raw_values or [])
            _validate_xy_lengths(chart_type, labels, values)
            parsed.append({
                "name": str(normalize_matplotlib_label_text(item.get("name") or f"系列{index}")),
                "values": values,
            })
    else:
        labels, values = _extract_labels_values(data)
        _validate_xy_lengths(chart_type, labels, values)
        parsed.append({"name": str(normalize_matplotlib_label_text(data.get("name") or "数值")), "values": values})

    return labels, parsed


def _apply_common_options(
    ax,
    options: Dict[str, Any],
    text_registry: TextLayoutRegistry,
) -> tuple[List[str], Dict[str, Any]]:
    warnings: List[str] = []
    metadata: Dict[str, Any] = {}

    x_label = options.get("x_label")
    y_label = options.get("y_label")
    unit = options.get("unit")
    if x_label:
        ax.set_xlabel(str(normalize_matplotlib_label_text(x_label)), fontsize=_source_font(11))
    if y_label or unit:
        label = str(y_label or "")
        if unit:
            label = f"{label} ({unit})" if label else str(unit)
        normalized_y_label = str(normalize_matplotlib_label_text(label))
        ax.set_ylabel(normalized_y_label, fontsize=_source_font(11))
    if x_label or y_label or unit:
        warnings.append("axis_labels_applied")
        metadata["axis_labels"] = {
            "x": str(x_label) if x_label else None,
            "y": str(y_label) if y_label else None,
            "unit": str(unit) if unit else None,
        }

    reference_lines = options.get("reference_lines")
    line_count = 0
    if isinstance(reference_lines, list):
        for item in reference_lines:
            if not isinstance(item, dict):
                continue
            axis = str(item.get("axis") or "y").lower()
            try:
                value = float(item.get("value"))
            except (TypeError, ValueError):
                continue
            label = item.get("label")
            color = str(item.get("color") or "#9a3d3d")
            if axis == "x":
                ax.axvline(value, color=color, linestyle="--", linewidth=1, alpha=0.75)
                if label:
                    reference_text = ax.text(value, 0.98, str(normalize_matplotlib_label_text(label)), transform=ax.get_xaxis_transform(), va="top", fontsize=_source_font(8.8), color=color)
                    text_registry.register(
                        reference_text,
                        role="reference_label",
                        domain="reference_labels",
                        priority=80.0,
                        payload={"label": str(label), "axis": "x", "value": value},
                    )
            else:
                ax.axhline(value, color=color, linestyle="--", linewidth=1, alpha=0.75)
                if label:
                    reference_text = ax.text(0.99, value, str(normalize_matplotlib_label_text(label)), transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=_source_font(8.8), color=color)
                    text_registry.register(
                        reference_text,
                        role="reference_label",
                        domain="reference_labels",
                        priority=80.0,
                        payload={"label": str(label), "axis": "y", "value": value},
                    )
            line_count += 1
    if line_count:
        metadata["reference_line_count"] = line_count
    normalized_reference_labels = [
        str(normalize_matplotlib_label_text(item.get("label")))
        for item in reference_lines
        if isinstance(reference_lines, list) and isinstance(item, dict) and item.get("label")
    ] if isinstance(reference_lines, list) else []
    normalized_text: Dict[str, Any] = {}
    if y_label or unit:
        normalized_text["y_label"] = normalized_y_label
    if normalized_reference_labels:
        normalized_text["reference_labels"] = normalized_reference_labels
    if normalized_text:
        metadata["normalized_text"] = normalized_text

    return warnings, metadata


def _normalize_chart_type(chart_type: str) -> str:
    return CHART_TYPE_ALIASES.get(str(chart_type), str(chart_type))


def _validate_xy_lengths(chart_type: str, labels: Sequence[Any], values: Sequence[Any]) -> None:
    if not labels:
        raise ChartDataError(f"{chart_type} 图需要非空 labels/x。")
    if not values:
        raise ChartDataError(f"{chart_type} 图需要非空 values/y。")
    if len(labels) != len(values):
        raise ChartDataError(
            f"{chart_type} 图 labels/x 长度为 {len(labels)}，values/y 长度为 {len(values)}，两者必须一致。"
        )


def _safe_chart_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value).strip())
    safe = safe.strip("_")
    return safe[:80] or f"report_chart_{uuid.uuid4().hex[:10]}"


def _dedupe(values: Sequence[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
