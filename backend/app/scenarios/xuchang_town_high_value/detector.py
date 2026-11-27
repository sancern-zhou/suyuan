"""同小时、同因子的乡镇站空间离群判定，不含 IO 与推送。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from app.scenarios.xuchang_city_exceedance.aqi import iaqi

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
    """按 GB 3095—2026 过渡限值换算六级污染等级（0~5）。"""
    score = iaqi("pm25" if pollutant == "PM2.5" else "pm10", concentration)
    if score is None:
        raise ValueError("有效浓度必须可计算 IAQI")
    return min(5, max(0, int((score - 1) // 50))) if score > 0 else 0


def _minimum_concentration(pollutant: str, config: HighValueConfig) -> float:
    return config.min_pm25_concentration if pollutant == "PM2.5" else config.min_pm10_concentration


def _is_persistent(
    rows: list[dict[str, Any]], *, station_id: str, column: str,
    hour: datetime, hours: int, minimum: float,
) -> bool:
    """候选站须连续达到绝对门槛，避免单小时突峰触发排查提醒。"""
    for offset in range(hours):
        expected = hour.replace(minute=0, second=0, microsecond=0) - timedelta(hours=offset)
        values = [
            number(row.get(column, row.get(column.lower())))
            for row in rows
            if _station_id(row) == station_id and _time(row) == expected
        ]
        if not values or values[0] is None or values[0] < minimum:
            return False
    return True


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
    先达到 GB 3095—2026 过渡限值的轻度污染门槛且连续高值，再要求浓度差、
    相对差和污染等级差相对区县内其他站点中位数同时达到阈值，避免低浓度相对离群误报。
    区县有效站点不足 minimum_peer_stations + 1 时该区县不判定；参照站较少时提高相对差门槛。
    modified z 仅作设备异常证据；设备异常保留中度及以上、与周边至少相差 2 个污染等级
    且 modified z 极高的极端离群，单小时即可识别，不受连续高值条件限制。
    大范围候选中若只有一站达到轻度及以上，该站优先单独提醒。
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
        minimum_concentration = _minimum_concentration(pollutant, config)
        for peers in county_candidates.values():
            if len(peers) < config.minimum_peer_stations + 1:
                continue
            relative_threshold = (
                config.sparse_peer_relative_difference
                if len(peers) < config.sparse_peer_threshold
                else config.min_relative_difference
            )
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
                if equipment_reason is None and (
                    value < minimum_concentration
                    or level < 2
                    or level_difference < config.min_level_difference
                    or absolute < config.min_absolute_difference
                    or relative < relative_threshold
                    or not _is_persistent(
                        rows, station_id=_station_id(candidate["row"]), column=column,
                        hour=latest, hours=config.consecutive_hours, minimum=minimum_concentration,
                    )
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
                    "relative_threshold": relative_threshold,
                    "minimum_concentration": minimum_concentration,
                    "consecutive_hours": config.consecutive_hours,
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
