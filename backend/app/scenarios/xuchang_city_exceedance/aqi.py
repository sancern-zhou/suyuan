"""HJ 633 hourly AQI helpers for rows sourced from the zhongda hour table.

中大平台站点小时表不提供首要污染物与等级列；按《环境空气质量指数（AQI）
技术规定》实时发布规则由六参数浓度计算：SO2/NO2/O3/CO 用 1 小时 IAQI
浓度限值表，PM10/PM2.5 用 24 小时浓度限值表，取最大 IAQI 为 AQI、对应
污染物为首要污染物（AQI≤50 时无首要污染物）。
"""

from __future__ import annotations

from typing import Any

_IAQI_LEVELS = (0, 50, 100, 150, 200, 300, 400, 500)

# 单位：μg/m3（co 为 mg/m3）；pm10/pm25 为 24h 限值表（实时发布规则）。
BREAKPOINTS = {
    "so2": (0, 150, 500, 650, 800, 1600, 2100, 2620),
    "no2": (0, 100, 200, 700, 1200, 2340, 3090, 3840),
    "o3": (0, 160, 200, 300, 400, 800, 1000, 1200),
    "co": (0, 5, 10, 35, 60, 90, 120, 150),
    "pm10": (0, 50, 150, 250, 350, 420, 500, 600),
    "pm25": (0, 35, 75, 115, 150, 250, 350, 500),
}

PRIMARY_LABELS = {
    "so2": "SO2", "no2": "NO2", "o3": "O3",
    "co": "CO", "pm10": "PM10", "pm25": "PM2.5",
}

_AQI_LEVEL_BANDS = ((0, 50, 1), (51, 100, 2), (101, 150, 3), (151, 200, 4), (201, 300, 5), (301, None, 6))


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def iaqi(pollutant: str, concentration: Any) -> float | None:
    value = _number(concentration)
    if value is None:
        return None
    low, high = BREAKPOINTS[pollutant][0], BREAKPOINTS[pollutant][-1]
    if value > high:
        return 500.0
    for index in range(1, len(_IAQI_LEVELS)):
        bp_low, bp_high = BREAKPOINTS[pollutant][index - 1], BREAKPOINTS[pollutant][index]
        if value <= bp_high:
            iaqi_low, iaqi_high = _IAQI_LEVELS[index - 1], _IAQI_LEVELS[index]
            return round(
                (iaqi_high - iaqi_low) / (bp_high - bp_low) * (value - bp_low) + iaqi_low, 1
            )
    return None


def hourly_aqi_and_primary(row: dict[str, Any]) -> tuple[float | None, str | None]:
    """返回 (小时AQI, 首要污染物)；AQI 为各因子最大 IAQI，≤50 无首要污染物。"""
    scores: list[tuple[float, str]] = []
    for pollutant, label in PRIMARY_LABELS.items():
        score = iaqi(pollutant, row.get(pollutant))
        if score is not None:
            scores.append((score, label))
    if not scores:
        return None, None
    top = max(scores)
    return top[0], (top[1] if top[0] > 50 else None)


def aqi_level(aqi: Any) -> int | None:
    value = _number(aqi)
    if value is None:
        return None
    for low, high, level in _AQI_LEVEL_BANDS:
        if high is None or value <= high:
            return level if value >= low else 1
    return None
