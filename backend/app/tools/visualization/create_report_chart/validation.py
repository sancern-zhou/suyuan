from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from app.tools.visualization.create_report_chart.text import normalize_matplotlib_label_text


class ChartDataError(ValueError):
    """User-facing create_report_chart data validation error."""


def require_labels(data: dict[str, Any], chart_type: str) -> list[str]:
    raw = data.get("labels") or data.get("categories") or data.get("x") or []
    if not isinstance(raw, list) or not raw:
        raise ChartDataError(f"{chart_type} 图需要非空 labels/x。")
    return [str(normalize_matplotlib_label_text(value)) for value in raw]


def finite_numbers(
    values: Any,
    path: str,
    *,
    nonnegative: bool = False,
) -> list[float]:
    if not isinstance(values, list) or not values:
        raise ChartDataError(f"{path} 需要非空数值数组。")
    result: list[float] = []
    for index, value in enumerate(values):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ChartDataError(f"{path}[{index}] 不是有效数值。") from None
        if not math.isfinite(number):
            raise ChartDataError(f"{path}[{index}] 必须是有限数值。")
        if nonnegative and number < 0:
            raise ChartDataError(f"{path}[{index}] 不允许包含负数。")
        result.append(number)
    return result


def finite_number(value: Any, path: str, *, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ChartDataError(f"{path} 不是有效数值。") from None
    if not math.isfinite(number):
        raise ChartDataError(f"{path} 必须是有限数值。")
    return number


def require_matching_length(path: str, values: Sequence[Any], labels: Sequence[Any]) -> None:
    if len(values) != len(labels):
        raise ChartDataError(f"{path} 长度为 {len(values)}，与 labels 长度 {len(labels)} 不一致。")


def require_series(data: dict[str, Any], chart_type: str) -> list[dict[str, Any]]:
    series = data.get("series")
    if not isinstance(series, list) or not series:
        raise ChartDataError(f"{chart_type} 图需要非空 series。")
    for index, item in enumerate(series):
        if not isinstance(item, dict):
            raise ChartDataError(f"{chart_type}.series[{index}] 必须是对象。")
    return series


def series_values(item: dict[str, Any], path: str, labels: Sequence[Any]) -> list[float]:
    raw = item.get("values")
    if raw is None:
        raw = item.get("data")
    values = finite_numbers(raw, f"{path}.values")
    require_matching_length(f"{path}.values", values, labels)
    return values
