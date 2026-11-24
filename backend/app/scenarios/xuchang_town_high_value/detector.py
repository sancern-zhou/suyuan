"""同小时、同因子的乡镇站空间离群判定，不含 IO 与推送。"""

from __future__ import annotations

import math
from datetime import datetime
from statistics import median
from typing import Any

from app.fetchers.xuchang_town_hour_day import iaqi_legacy

from .config import HighValueConfig

POLLUTANT_COLUMNS = {"PM2.5": "PM25", "PM10": "PM10"}
LEVEL_NAMES = ("优", "良", "轻度污染", "中度污染", "重度污染", "严重污染")


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def pollution_level(pollutant: str, concentration: float) -> int:
    """统一按 TownStationData 历史 IAQI 折点换算六级污染等级（0~5）。"""
    score = iaqi_legacy("pm25" if pollutant == "PM2.5" else "pm10", concentration, daily=False)
    if score is None:
        raise ValueError("有效浓度必须可计算 IAQI")
    return min(5, max(0, (score - 1) // 50)) if score > 0 else 0


def _station_id(row: dict[str, Any]) -> str:
    return str(row.get("Tsno") or row.get("tsno") or row.get("station_id") or "").strip()


def _station_name(row: dict[str, Any]) -> str:
    return str(row.get("StationName") or row.get("station_name") or row.get("name") or _station_id(row)).strip()


def _time(row: dict[str, Any]) -> datetime | None:
    value = row.get("CollectionTime") or row.get("collection_time") or row.get("data_time")
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def detect_high_value_groups(
    rows: list[dict[str, Any]],
    *,
    hour: datetime | None = None,
    config: HighValueConfig | None = None,
) -> tuple[datetime | None, list[dict[str, Any]]]:
    """返回最新完整小时及高值组；候选设备异常记录保留在组内供流水留痕。

    浓度差与相对差须同时达到阈值，避免低浓度小绝对差、高浓度小比例差误报。
    modified z 使用其他有效站的 MAD；MAD=0 时不以 z 判设备异常。
    """
    config = config or HighValueConfig()
    valid_hours = [value for row in rows if (value := _time(row)) is not None]
    if not valid_hours:
        return None, []
    latest = hour or max(valid_hours).replace(minute=0, second=0, microsecond=0)
    current = [row for row in rows if _time(row) == latest]
    groups: list[dict[str, Any]] = []
    for pollutant, column in POLLUTANT_COLUMNS.items():
        candidates: list[dict[str, Any]] = []
        for row in current:
            value = number(row.get(column, row.get(column.lower())))
            if value is not None and _station_id(row):
                candidates.append({"row": row, "value": value})
        if len(candidates) < config.minimum_peer_stations + 1:
            continue
        alerts: list[dict[str, Any]] = []
        for candidate in candidates:
            value = candidate["value"]
            peers = [item["value"] for item in candidates if item is not candidate]
            baseline = median(peers)
            absolute = value - baseline
            relative = absolute / baseline if baseline > 0 else (math.inf if absolute > 0 else 0.0)
            level = pollution_level(pollutant, value)
            peer_level = pollution_level(pollutant, baseline)
            level_difference = level - peer_level
            deviations = [abs(peer - baseline) for peer in peers]
            mad = median(deviations)
            modified_z = 0.6745 * (value - baseline) / mad if mad > 0 else None
            equipment_reason = None
            if level_difference >= config.equipment_level_difference:
                equipment_reason = "level_difference"
            elif modified_z is not None and modified_z >= config.equipment_modified_z:
                equipment_reason = "modified_z"
            if (
                level_difference < config.min_level_difference
                or absolute < config.min_absolute_difference
                or relative < config.min_relative_difference
            ):
                continue
            row = candidate["row"]
            alerts.append({
                "station_id": _station_id(row),
                "station_name": _station_name(row),
                "value": value,
                "baseline": baseline,
                "absolute_difference": absolute,
                "relative_difference": relative,
                "level": level,
                "level_name": LEVEL_NAMES[level],
                "peer_level": peer_level,
                "peer_level_name": LEVEL_NAMES[peer_level],
                "level_difference": level_difference,
                "modified_z": modified_z,
                "peer_count": len(peers),
                "equipment_suspected": equipment_reason is not None,
                "equipment_reason": equipment_reason,
            })
        if not alerts:
            continue
        alerts.sort(key=lambda item: (item["station_id"], item["station_name"]))
        deliverable = [item for item in alerts if not item["equipment_suspected"]]
        groups.append({
            "group_id": f"{latest:%Y%m%d%H}-{pollutant}",
            "pollutant": pollutant,
            "hour": latest,
            "alerts": alerts,
            "stations": deliverable,
            "delivery_mode": "aggregate",
            "out_of_scope": len(deliverable) > config.max_alert_stations,
        })
    return latest, groups
