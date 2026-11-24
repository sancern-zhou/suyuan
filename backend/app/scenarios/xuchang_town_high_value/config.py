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
    minimum_peer_stations: int = 5
    # 单因子有效高值达到 5 站属于大范围污染，不由本场景推送。
    max_alert_stations: int = 4
    equipment_level_difference: int = 4
    equipment_modified_z: float = 8.0
    weather_lookback_hours: int = 3
    latest_hour_max_age_hours: int = 2

    @classmethod
    def from_env(cls) -> "HighValueConfig":
        return cls(
            min_level_difference=int(_number("TOWN_HIGH_VALUE_MIN_LEVEL_DIFF", 1)),
            min_absolute_difference=_number("TOWN_HIGH_VALUE_MIN_ABS_DIFF", 20),
            min_relative_difference=_number("TOWN_HIGH_VALUE_MIN_REL_DIFF", 0.5),
            minimum_peer_stations=int(_number("TOWN_HIGH_VALUE_MIN_PEERS", 5)),
            max_alert_stations=int(_number("TOWN_HIGH_VALUE_MAX_STATIONS", 4)),
            equipment_level_difference=int(_number("TOWN_HIGH_VALUE_EQUIPMENT_LEVEL_DIFF", 4)),
            equipment_modified_z=_number("TOWN_HIGH_VALUE_EQUIPMENT_Z", 8),
            weather_lookback_hours=int(_number("TOWN_HIGH_VALUE_WEATHER_HOURS", 3)),
            latest_hour_max_age_hours=int(_number("TOWN_HIGH_VALUE_MAX_AGE_HOURS", 2)),
        )
