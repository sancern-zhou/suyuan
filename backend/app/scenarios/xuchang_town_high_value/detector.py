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

# 中心城区站点密集，合并为一个参照群体避免小辖区不足最少站数无法判定；
# 告警条目仍保留站点实际辖区，用于按属地提醒。
CENTRAL_URBAN_COUNTIES = frozenset({"魏都区", "建安区", "东城区", "开发区", "示范区"})
CENTRAL_URBAN_BASELINE = "中心城区"


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


def _county(row: dict[str, Any]) -> str:
    return str(row.get("CountyName") or row.get("county_name") or "").strip()


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

    以站点所在区县为参照群体（魏都/建安/东城/开发区/示范区合并为中心城区）：
    浓度差与相对差相对区县内其他站点中位数须同时达到阈值，
    避免低浓度小绝对差、高浓度小比例差误报，也避免区域整体偏高被误报为单站离群。
    区县有效站点不足 minimum_peer_stations + 1 时该区县不判定；无辖区归属的站点不参与。
    modified z 对良/轻度污染仅作空间孤立证据，避免误删真实单站污染；
    设备异常仅保留中度及以上、与周边至少相差 2 个污染等级且 modified z 极高的极端离群。
    大范围候选中若只有一站达到轻度及以上，该站优先单独提醒，普通良站作区域背景。
    """
    config = config or HighValueConfig()
    valid_hours = [value for row in rows if (value := _time(row)) is not None]
    if not valid_hours:
        return None, []
    latest = hour or max(valid_hours).replace(minute=0, second=0, microsecond=0)
    current = [row for row in rows if _time(row) == latest]
    groups: list[dict[str, Any]] = []
    for pollutant, column in POLLUTANT_COLUMNS.items():
        county_candidates: dict[str, list[dict[str, Any]]] = {}
        for row in current:
            value = number(row.get(column, row.get(column.lower())))
            county = _county(row)
            if value is not None and _station_id(row) and county:
                if county in CENTRAL_URBAN_COUNTIES:
                    county = CENTRAL_URBAN_BASELINE
                county_candidates.setdefault(county, []).append({"row": row, "value": value})
        alerts: list[dict[str, Any]] = []
        for peers in county_candidates.values():
            if len(peers) < config.minimum_peer_stations + 1:
                continue
            for candidate in peers:
                value = candidate["value"]
                peer_values = [item["value"] for item in peers if item is not candidate]
                baseline = median(peer_values)
                absolute = value - baseline
                relative = absolute / baseline if baseline > 0 else (math.inf if absolute > 0 else 0.0)
                level = pollution_level(pollutant, value)
                peer_level = pollution_level(pollutant, baseline)
                level_difference = level - peer_level
                deviations = [abs(peer - baseline) for peer in peer_values]
                mad = median(deviations)
                modified_z = 0.6745 * (value - baseline) / mad if mad > 0 else None
                equipment_reason = None
                # 轻度污染仍可能是用户关注的孤立高值，不因相对等级差或 z 值误删。
                # 中度及以上且与周边至少相差 2 级，同时仍须是极端空间离群。
                if (
                    level >= 3
                    and level_difference >= config.equipment_level_difference
                    and modified_z is not None
                    and modified_z >= config.equipment_modified_z
                ):
                    equipment_reason = "moderate_or_worse_extreme_outlier"
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
                    "county_name": _county(row) or None,
                    "station_type": str(row.get("StationType") or row.get("station_type") or "").strip() or None,
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
                    "peer_count": len(peer_values),
                    "equipment_suspected": equipment_reason is not None,
                    "equipment_reason": equipment_reason,
                })
        if not alerts:
            continue
        alerts.sort(key=lambda item: (item["station_id"], item["station_name"]))
        deliverable = [item for item in alerts if not item["equipment_suspected"]]
        polluted = [item for item in deliverable if item["level"] >= 2]
        if len(deliverable) > config.max_alert_stations and len(polluted) == 1:
            deliverable = polluted
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
