"""Fill missing legends for named multi-series Cartesian ECharts options."""

from __future__ import annotations

from typing import Any


def ensure_echarts_legend(option: dict[str, Any]) -> dict[str, Any]:
    """Keep explicit legend choices, but label generated multi-city series."""
    if not isinstance(option, dict) or "legend" in option:
        return option
    if "xAxis" not in option or "yAxis" not in option:
        return option
    series = option.get("series")
    if not isinstance(series, list):
        return option
    names = list(dict.fromkeys(
        item.get("name") for item in series
        if isinstance(item, dict) and isinstance(item.get("name"), str)
        and item["name"].strip()
    ))
    if len(names) < 2:
        return option
    option["legend"] = {"data": names, "orient": "horizontal", "bottom": 35}
    grid = option.get("grid")
    if grid is None:
        option["grid"] = {"bottom": 84, "containLabel": True}
    return option
