"""Shared ECharts layout normalization for interactive chart options.

Keeps layout consistent across every renderer: the legend sits horizontally
below the x-axis tick labels, the y-axis name is on the chart's left, and the
x-axis name is at the right end of the x-axis. The grid bottom is expanded so
the legend sits directly under the tick labels without overlapping them.

The legend is anchored ``MIN_BOTTOM_LEGEND_OFFSET`` pixels above the container
bottom so it does not hug the edge, and the grid bottom reserves exactly the
legend row plus the x-axis label row (no extra gap).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

LEGEND_HEIGHT = 25
X_AXIS_LABEL_HEIGHT = 24
LAYOUT_GAP = 0
MIN_BOTTOM_LEGEND_OFFSET = 35
AXIS_NAME_EXTRA = 16
DEFAULT_AXIS_NAME_GAP = 15
# 渲染容器默认宽度（chart_image_renderer 的 PNG 默认 800x500），仅用于图例换行估算
DEFAULT_CONTAINER_WIDTH = 800
_TIME_LABEL_SAMPLE = "2026-10-09 10:00"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _estimate_text_width(text: str, font_size: float) -> float:
    """CJK 视为全宽，其余按 0.6 倍字宽估算。"""
    width = 0.0
    for ch in text:
        width += font_size if ord(ch) > 0x2E7F else font_size * 0.6
    return width


def _axis_label_samples(axis: Dict[str, Any], series: List[Any]) -> List[str]:
    axis_type = axis.get("type") or "category"
    if axis_type == "category" and isinstance(axis.get("data"), list) and axis["data"]:
        return ["" if item is None else str(item) for item in axis["data"]]
    samples: List[str] = []
    for serie in series:
        if not isinstance(serie, dict) or not isinstance(serie.get("data"), list):
            continue
        data = serie["data"]
        if not data:
            continue
        for index in {0, len(data) // 2, len(data) - 1}:
            item = data[index]
            if item is None:
                continue
            if isinstance(item, list):
                value = item[0] if item else None
            elif isinstance(item, dict):
                value = (item.get("value")[0] if isinstance(item.get("value"), list) else None) or item.get("name")
            else:
                value = item
            if value is not None:
                samples.append(str(value))
    if not samples and axis_type == "time":
        samples.append(_TIME_LABEL_SAMPLE)
    return samples


def _x_axis_label_space(option: Dict[str, Any]) -> float:
    """估算 x 轴刻度文字的垂直占用：旋转/换行标签远超固定常量。"""
    series = option.get("series") if isinstance(option.get("series"), list) else []
    space = float(X_AXIS_LABEL_HEIGHT)
    for axis in _as_list(option.get("xAxis")):
        if not isinstance(axis, dict):
            continue
        label = axis.get("axisLabel") if isinstance(axis.get("axisLabel"), dict) else {}
        if label.get("show") is False:
            continue
        font_size = _numeric(label.get("fontSize")) or 12.0
        rotate = abs(_numeric(label.get("rotate")) or 0.0)
        samples = _axis_label_samples(axis, series)
        if not samples:
            continue
        longest = max(samples, key=len)
        text_width = _estimate_text_width(longest, font_size)
        if rotate > 0:
            rad = math.radians(rotate)
            height = text_width * math.sin(rad) + font_size * 1.25 * math.cos(rad)
        else:
            wrap_width = _numeric(label.get("width")) or 0.0
            breaks = wrap_width > 0 and "break" in str(label.get("overflow") or "")
            lines = max(1, math.ceil(text_width / wrap_width)) if breaks else 1
            height = lines * font_size * 1.25
        space = max(space, math.ceil(height))
    return space


def _legend_space(option: Dict[str, Any]) -> float:
    """估算底部图例块高度：横向图例换行时按行数折算。"""
    space = float(LEGEND_HEIGHT)
    for legend in _as_list(option.get("legend")):
        if not isinstance(legend, dict) or legend.get("show") is False:
            continue
        if isinstance(legend.get("data"), list) and legend["data"]:
            names = [
                str(item.get("name") if isinstance(item, dict) else item)
                for item in legend["data"] if item is not None
            ]
        else:
            names = []
            for serie in option.get("series") if isinstance(option.get("series"), list) else []:
                if isinstance(serie, dict) and isinstance(serie.get("name"), str) and serie["name"].strip():
                    name = serie["name"].strip()
                    if name not in names:
                        names.append(name)
        if not names:
            continue
        legend_style = legend.get("textStyle") if isinstance(legend.get("textStyle"), dict) else {}
        font_size = _numeric(legend_style.get("fontSize")) or 12.0
        if legend.get("type") == "scroll":
            space = max(space, math.ceil(font_size * 1.7))
            continue
        item_gap = _numeric(legend.get("itemGap"))
        item_gap = item_gap if item_gap is not None else 10.0
        total_width = sum(25 + _estimate_text_width(name, font_size) + item_gap for name in names)
        usable = max(DEFAULT_CONTAINER_WIDTH - 60, 180)
        rows = max(1, math.ceil(total_width / usable))
        space = max(space, math.ceil(rows * (font_size + 7) + (rows - 1) * item_gap))
    return space


def _x_axis_name_space(option: Dict[str, Any]) -> float:
    """Only a centered x-axis name needs its own row below the tick labels.

    When the name sits at the axis end (the default) it shares the legend's
    row at the far right, so reserving a full row there would leave a large
    gap between the plot and the bottom legend.
    """
    spaces = []
    for axis in _as_list(option.get("xAxis")):
        if not isinstance(axis, dict) or not axis.get("name"):
            continue
        if (axis.get("nameLocation") or "end") not in ("middle", "center"):
            continue
        name_gap = _numeric(axis.get("nameGap"))
        spaces.append(
            (name_gap if name_gap is not None else DEFAULT_AXIS_NAME_GAP)
            + AXIS_NAME_EXTRA
        )
    return max(spaces) if spaces else 0.0


def _bottom_legend_offset(option: Dict[str, Any]) -> float | None:
    """Bottom legend offset in px, or None when the legend is not at the bottom."""
    legend = option.get("legend")
    if not isinstance(legend, dict):
        return None
    if legend.get("top") is not None:
        return None
    if legend.get("bottom") is not None:
        numeric = _numeric(legend.get("bottom"))
        return numeric if numeric is not None else 0.0
    if legend.get("left") is not None or legend.get("right") is not None:
        return None
    return 0.0


def normalize_echarts_layout(option: Dict[str, Any]) -> Dict[str, Any]:
    """Anchor the bottom legend below the x-axis labels without a gap."""
    if not isinstance(option, dict):
        return option

    grid_value = option.get("grid")
    if grid_value is None:
        return option

    offset = _bottom_legend_offset(option)
    if offset is None:
        return option

    effective_offset = max(offset, float(MIN_BOTTOM_LEGEND_OFFSET))
    legend = option.get("legend")
    if isinstance(legend, dict):
        legend["bottom"] = effective_offset

    def apply(grid: Any) -> Any:
        if not isinstance(grid, dict):
            return grid
        # containLabel 开启时 ECharts 自动把刻度框进 grid，无需重复预留刻度行
        label_space = 0.0 if grid.get("containLabel") is True else _x_axis_label_space(option)
        required_bottom = (
            effective_offset
            + _legend_space(option)
            + label_space
            + LAYOUT_GAP
            + _x_axis_name_space(option)
        )
        current = _numeric(grid.get("bottom")) or 0.0
        adjusted = dict(grid)
        adjusted["bottom"] = max(current, required_bottom)
        return adjusted

    if isinstance(grid_value, list):
        option["grid"] = [apply(item) for item in grid_value]
    else:
        option["grid"] = apply(grid_value)
    return option
