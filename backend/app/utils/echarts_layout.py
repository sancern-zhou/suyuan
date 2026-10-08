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

from typing import Any, Dict, List

LEGEND_HEIGHT = 25
X_AXIS_LABEL_HEIGHT = 24
LAYOUT_GAP = 0
MIN_BOTTOM_LEGEND_OFFSET = 35
AXIS_NAME_EXTRA = 16
DEFAULT_AXIS_NAME_GAP = 15


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

    required_bottom = (
        effective_offset
        + LEGEND_HEIGHT
        + X_AXIS_LABEL_HEIGHT
        + LAYOUT_GAP
        + _x_axis_name_space(option)
    )

    def apply(grid: Any) -> Any:
        if not isinstance(grid, dict):
            return grid
        current = _numeric(grid.get("bottom")) or 0.0
        adjusted = dict(grid)
        adjusted["bottom"] = max(current, required_bottom)
        return adjusted

    if isinstance(grid_value, list):
        option["grid"] = [apply(item) for item in grid_value]
    else:
        option["grid"] = apply(grid_value)
    return option
