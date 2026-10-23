"""Shared report defaults for interactive ECharts figures.

Defaults are applied only when an option does not provide an explicit value.
Environmental grade/risk colors remain caller-owned because they have domain
semantics different from the general series palette.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.utils.chart_theme import SERIES_COLORS
from app.utils.font_utils import BROWSER_CHART_FONT_FAMILY


def apply_echarts_report_theme(option: dict[str, Any]) -> dict[str, Any]:
    """Apply accessible font and series-color defaults without overwriting intent."""
    if not isinstance(option, dict):
        return option
    option = deepcopy(option)
    option.setdefault("color", list(SERIES_COLORS))
    option.setdefault("backgroundColor", "white")
    option["textStyle"] = _with_font(option.get("textStyle"))
    if isinstance(option.get("title"), dict):
        option["title"]["textStyle"] = _with_font(option["title"].get("textStyle"))
    for legend in _as_list(option.get("legend")):
        if isinstance(legend, dict):
            legend["textStyle"] = _with_font(legend.get("textStyle"))
    for axis in (*_as_list(option.get("xAxis")), *_as_list(option.get("yAxis"))):
        if not isinstance(axis, dict):
            continue
        axis["axisLabel"] = _with_font(axis.get("axisLabel"))
        if axis.get("name"):
            axis["nameTextStyle"] = _with_font(axis.get("nameTextStyle"))
    return option


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _with_font(value: Any) -> dict[str, Any]:
    style = dict(value) if isinstance(value, dict) else {}
    style.setdefault("fontFamily", BROWSER_CHART_FONT_FAMILY)
    return style
