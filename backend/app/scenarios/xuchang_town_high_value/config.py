"""乡镇小时高值判定配置；环境变量均为可选项。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class HighValueConfig:
    min_level_difference: int = 1
    min_absolute_difference: float = 20.0
    min_relative_difference: float = 0.5
    # GB 3095—2026 过渡限值：先达到轻度污染下限，再判断空间离群。
    min_pm25_concentration: float = 60.0
    min_pm10_concentration: float = 120.0
    # 区县内参与比较的最少周边站数（不含自身）；区县有效站点不足时该区县整组不判定。
    minimum_peer_stations: int = 5
    # 参照站较少时提高相对差门槛，降低缺站造成的假离群。
    sparse_peer_relative_difference: float = 0.8
    sparse_peer_threshold: int = 9
    # 普通高值要求连续小时达到绝对门槛；设备异常仍在单小时内独立识别。
    consecutive_hours: int = 2
    # 单因子有效高值达到 5 站通常视为大范围污染；若仅一站轻度及以上则优先孤立提醒。
    max_alert_stations: int = 4
    equipment_level_difference: int = 2
    equipment_modified_z: float = 8.0
    equipment_cooldown_hours: int = 24
    high_value_cooldown_hours: int = 2
    weather_lookback_hours: int = 3
    latest_hour_max_age_hours: int = 2

    @classmethod
    def from_env(cls) -> "HighValueConfig":
        return cls(
            min_level_difference=int(_number("TOWN_HIGH_VALUE_MIN_LEVEL_DIFF", 1)),
            min_absolute_difference=_number("TOWN_HIGH_VALUE_MIN_ABS_DIFF", 20),
            min_relative_difference=_number("TOWN_HIGH_VALUE_MIN_REL_DIFF", 0.5),
            min_pm25_concentration=_number("TOWN_HIGH_VALUE_MIN_PM25", 60),
            min_pm10_concentration=_number("TOWN_HIGH_VALUE_MIN_PM10", 120),
            minimum_peer_stations=int(_number("TOWN_HIGH_VALUE_MIN_PEERS", 5)),
            sparse_peer_relative_difference=_number("TOWN_HIGH_VALUE_SPARSE_REL_DIFF", 0.8),
            sparse_peer_threshold=int(_number("TOWN_HIGH_VALUE_SPARSE_PEER_THRESHOLD", 9)),
            consecutive_hours=int(_number("TOWN_HIGH_VALUE_CONSECUTIVE_HOURS", 2)),
            max_alert_stations=int(_number("TOWN_HIGH_VALUE_MAX_STATIONS", 4)),
            equipment_level_difference=int(_number("TOWN_HIGH_VALUE_EQUIPMENT_LEVEL_DIFF", 2)),
            equipment_modified_z=_number("TOWN_HIGH_VALUE_EQUIPMENT_Z", 8),
            equipment_cooldown_hours=int(_number("TOWN_HIGH_VALUE_EQUIPMENT_COOLDOWN_HOURS", 24)),
            high_value_cooldown_hours=int(_number("TOWN_HIGH_VALUE_COOLDOWN_HOURS", 2)),
            weather_lookback_hours=int(_number("TOWN_HIGH_VALUE_WEATHER_HOURS", 3)),
            latest_hour_max_age_hours=int(_number("TOWN_HIGH_VALUE_MAX_AGE_HOURS", 2)),
        )
