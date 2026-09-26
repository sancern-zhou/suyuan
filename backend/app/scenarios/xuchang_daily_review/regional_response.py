"""Episode-anchored deterministic regional response and transport evidence.

Implements 昨日污染回顾乡镇站区域响应与传输确定性计算方案 §4-§8:
before/during/after windows, per-station co-rise, temporal lead/lag,
coordinate-strict spatial gradient and the bounded transport expression.
All outputs carry explicit rules, sample counts and threshold versions so the
report Agent can quote them without recomputing anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import asin, atan2, cos, pi, radians, sin, sqrt
from statistics import median
from typing import Any

import numpy as np

from app.scenarios.xuchang_daily_review.episodes import (
    REGIONAL_RESPONSE_PROFILE,
    normalize_hour,
)

WINDOW_BEFORE_HOURS = 3
WINDOW_AFTER_HOURS = 3
WINDOW_MINIMUM_SAMPLES = {"before": 2, "during": 1, "after": 2}
WINDOW_POLICY_NOTE = (
    "before/after 背景窗至少需要 2 个有效小时样本；during 窗为 episode 本身"
    "（场景一 0.5h 不活跃关闭策略下通常为单个告警小时），至少 1 个有效小时样本。"
)
THRESHOLD_VERSION = REGIONAL_RESPONSE_PROFILE
REGIONAL_RISE_THRESHOLDS: dict[str, dict[str, float]] = {
    "PM2.5": {"absolute": 10.0, "relative": 0.20},
    "PM10": {"absolute": 15.0, "relative": 0.20},
    "SO2": {"absolute": 8.0, "relative": 0.20},
    "NO2": {"absolute": 8.0, "relative": 0.20},
    "NOX": {"absolute": 8.0, "relative": 0.20},
    "CO": {"absolute": 0.2, "relative": 0.20},
    "O3": {"absolute": 30.0, "relative": 0.20},
}
RISE_RULE_TEMPLATE = (
    "during_delta >= {absolute} AND during_ratio >= {relative} "
    "(ratio undefined when before-mean <= 0, absolute threshold applies); "
    "decline when during_delta <= -{absolute}"
)
POLLUTANT_SERIES_KEY = {
    "PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "NOX": "no2",
    "CO": "co", "O3": "o3",
}
MIN_VALID_NEIGHBORS = 3
CO_RISE_RATIO = 0.6
DECLINE_RATIO = 0.6
DELAYED_RISE_DELTA = 0.2
LOCAL_NOT_RISE_RATIO = 0.5
REGIONAL_CLASSIFICATION_RULE = (
    f"insufficient_evidence if valid_neighbors < {MIN_VALID_NEIGHBORS}; "
    f"regional_co_rise if during_rise_ratio >= {CO_RISE_RATIO}; "
    f"delayed_regional_rise if after_rise_ratio - during_rise_ratio >= {DELAYED_RISE_DELTA}; "
    f"regional_decline if during_decline_ratio >= {DECLINE_RATIO}; "
    f"local_target_only if target rises AND during_rise_ratio < {LOCAL_NOT_RISE_RATIO}; "
    "else insufficient_evidence(no_dominant_regional_pattern)"
)
PLANE_FIT_MIN_STATIONS = 3
COLLINEARITY_EPSILON_KM2 = 1e-3
EARTH_RADIUS_KM = 6371.0088
EXPRESSION_BOUNDARY = (
    "空间梯度只描述空间结构，不能单独证明传输方向；"
    "禁止输出确定传输方向、具体源区、企业责任或污染贡献率结论。"
)
ALLOWED_CONCLUSIONS = {
    "regional_co_rise": "区域同步抬升",
    "neighbor_lead_rise": "周边提前抬升",
    "post_alert_spread": "告警后扩散",
    "local_prominence": "局地突出",
    "no_directional_conclusion": "无方向性结论",
}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _window_hours(episode_start: str, episode_end: str) -> dict[str, list[datetime]]:
    start = normalize_hour(episode_start)
    end = normalize_hour(episode_end) or start
    if start is None:
        return {"before": [], "during": [], "after": []}
    end = max(start, end)
    before = [start - timedelta(hours=offset) for offset in range(WINDOW_BEFORE_HOURS, 0, -1)]
    span_hours = int((end - start).total_seconds() // 3600)
    during = [start + timedelta(hours=offset) for offset in range(span_hours + 1)]
    after = [end + timedelta(hours=offset) for offset in range(1, WINDOW_AFTER_HOURS + 1)]
    return {"before": before, "during": during, "after": after}


def build_window_policy(windows: dict[str, list[datetime]]) -> dict[str, Any]:
    return {
        "window_before_hours": WINDOW_BEFORE_HOURS,
        "window_after_hours": WINDOW_AFTER_HOURS,
        "window_minimum_samples": dict(WINDOW_MINIMUM_SAMPLES),
        "window_policy_note": WINDOW_POLICY_NOTE,
        "windows": {
            name: [hour.isoformat() for hour in hours]
            for name, hours in windows.items()
        },
    }


def _series(rows: list[dict[str, Any]], station_id: str, key: str) -> dict[datetime, float]:
    series: dict[datetime, float] = {}
    for row in rows:
        if str(row.get("station_id")) != station_id:
            continue
        hour = normalize_hour(row.get("data_time"))
        value = _number(row.get(key))
        if hour is not None and value is not None:
            series[hour] = value
    return series


def _window_stats(series: dict[datetime, float], hours: list[datetime], minimum: int) -> dict[str, Any]:
    values = [series[hour] for hour in hours if hour in series]
    if len(values) < minimum:
        return {
            "status": "insufficient_data",
            "valid_hours": len(values),
            "expected_hours": len(hours),
            "mean": None,
        }
    return {
        "status": "ok",
        "valid_hours": len(values),
        "expected_hours": len(hours),
        "mean": _round(sum(values) / len(values)),
    }


def _meets_rise(before_mean: float, value: float, thresholds: dict[str, float]) -> dict[str, Any]:
    delta = value - before_mean
    ratio = delta / before_mean if before_mean > 0 else None
    absolute_ok = delta >= thresholds["absolute"]
    relative_ok = ratio is None or ratio >= thresholds["relative"]
    return {
        "value": _round(value),
        "delta": _round(delta),
        "ratio": _round(ratio, 4),
        "meets": bool(absolute_ok and relative_ok),
    }


def classify_station_response(
    station: dict[str, Any],
    series: dict[datetime, float],
    windows: dict[str, list[datetime]],
    episode_start: datetime,
    thresholds: dict[str, float],
    *,
    is_target: bool,
) -> dict[str, Any]:
    """Per-station window means, deltas, ratios and rise classification."""
    before = _window_stats(series, windows["before"], WINDOW_MINIMUM_SAMPLES["before"])
    during = _window_stats(series, windows["during"], WINDOW_MINIMUM_SAMPLES["during"])
    after = _window_stats(series, windows["after"], WINDOW_MINIMUM_SAMPLES["after"])
    during_delta = during_ratio = after_delta = after_ratio = None
    during_classification = after_classification = "insufficient_data"
    if before["status"] == "ok" and during["status"] == "ok":
        during_delta = during["mean"] - before["mean"]
        during_ratio = during_delta / before["mean"] if before["mean"] > 0 else None
        rise = _meets_rise(before["mean"], during["mean"], thresholds)
        if rise["meets"]:
            during_classification = "rise"
        elif during_delta <= -thresholds["absolute"]:
            during_classification = "decline"
        else:
            during_classification = "flat"
    if before["status"] == "ok" and after["status"] == "ok":
        after_delta = after["mean"] - before["mean"]
        after_ratio = after_delta / before["mean"] if before["mean"] > 0 else None
        after_rise = _meets_rise(before["mean"], after["mean"], thresholds)
        if after_rise["meets"]:
            after_classification = "rise"
        elif after_delta <= -thresholds["absolute"]:
            after_classification = "decline"
        else:
            after_classification = "flat"
    first_rise_hour = None
    lead_hours_to_target = None
    lead_status = "no_detected_rise"
    if before["status"] == "ok":
        span = windows["before"] + windows["during"] + windows["after"]
        for hour in sorted(span):
            value = series.get(hour)
            if value is None:
                continue
            check = _meets_rise(before["mean"], value, thresholds)
            if check["meets"]:
                first_rise_hour = hour
                lead_hours_to_target = int((hour - episode_start).total_seconds() // 3600)
                lead_status = "lead" if lead_hours_to_target < 0 else (
                    "synchronous" if lead_hours_to_target == 0 else "lag"
                )
                break
    return {
        "station_id": station["station_id"],
        "station_name": station.get("name") or station["station_id"],
        "station_type": station.get("station_type", "regular"),
        "district": station.get("district"),
        "is_target": is_target,
        "coordinate_status": "available" if station.get("lat") is not None and station.get("lon") is not None else "missing_coordinates",
        "lat": station.get("lat"),
        "lon": station.get("lon"),
        "series_valid_hours": len(series),
        "before": before,
        "during": during,
        "after": after,
        "during_delta": _round(during_delta),
        "during_ratio": _round(during_ratio, 4),
        "after_delta": _round(after_delta),
        "after_ratio": _round(after_ratio, 4),
        "during_classification": during_classification,
        "after_classification": after_classification,
        "first_rise_hour": first_rise_hour.isoformat() if first_rise_hour else None,
        "lead_hours_to_target": lead_hours_to_target,
        "lead_status": lead_status,
    }


def regional_classification(
    target_response: dict[str, Any], neighbor_responses: list[dict[str, Any]]
) -> dict[str, Any]:
    valid = [item for item in neighbor_responses if item["during_classification"] != "insufficient_data"]
    risen = sum(1 for item in valid if item["during_classification"] == "rise")
    declined = sum(1 for item in valid if item["during_classification"] == "decline")
    after_valid = [item for item in neighbor_responses if item["after_classification"] != "insufficient_data"]
    after_risen = sum(1 for item in after_valid if item["after_classification"] == "rise")
    during_rise_ratio = risen / len(valid) if valid else None
    during_decline_ratio = declined / len(valid) if valid else None
    after_rise_ratio = after_risen / len(after_valid) if after_valid else None
    classification = "insufficient_evidence"
    reason = "no_dominant_regional_pattern"
    if len(valid) < MIN_VALID_NEIGHBORS:
        reason = f"fewer_than_{MIN_VALID_NEIGHBORS}_valid_neighbor_stations"
    elif during_rise_ratio >= CO_RISE_RATIO:
        classification = "regional_co_rise"
        reason = None
    elif (
        after_rise_ratio is not None
        and after_rise_ratio - (during_rise_ratio or 0.0) >= DELAYED_RISE_DELTA
    ):
        classification = "delayed_regional_rise"
        reason = None
    elif during_decline_ratio >= DECLINE_RATIO:
        classification = "regional_decline"
        reason = None
    elif (
        target_response["during_classification"] == "rise"
        and during_rise_ratio < LOCAL_NOT_RISE_RATIO
    ):
        classification = "local_target_only"
        reason = None
    return {
        "classification": classification,
        "reason": reason,
        "valid_neighbor_count": len(valid),
        "neighbor_count": len(neighbor_responses),
        "during_rise_count": risen,
        "during_rise_ratio": _round(during_rise_ratio, 4),
        "during_decline_count": declined,
        "during_decline_ratio": _round(during_decline_ratio, 4),
        "after_rise_count": after_risen,
        "after_rise_ratio": _round(after_rise_ratio, 4),
        "rule": REGIONAL_CLASSIFICATION_RULE,
    }


def temporal_lead_lag(
    neighbor_responses: list[dict[str, Any]], episode_start: str
) -> dict[str, Any]:
    entries = [
        {
            "station_id": item["station_id"],
            "station_type": item["station_type"],
            "first_rise_hour": item["first_rise_hour"],
            "lead_hours_to_target": item["lead_hours_to_target"],
            "lead_status": item["lead_status"],
        }
        for item in neighbor_responses
        if item["lead_status"] != "no_detected_rise"
    ]
    leads = [item["lead_hours_to_target"] for item in entries]
    median_lead = _round(median(leads), 1) if leads else None
    return {
        "episode_start": episode_start,
        "detected_rise_count": len(entries),
        "no_detected_rise_count": sum(
            1 for item in neighbor_responses if item["lead_status"] == "no_detected_rise"
        ),
        "lead_count": sum(1 for item in entries if item["lead_status"] == "lead"),
        "synchronous_count": sum(1 for item in entries if item["lead_status"] == "synchronous"),
        "lag_count": sum(1 for item in entries if item["lead_status"] == "lag"),
        "median_lead_hours_to_target": median_lead,
        "stations": entries,
        "rule": "lead_hours_to_target = first_rise_hour - episode_start; <0 lead, =0 synchronous, >0 lag",
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    h = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    d_lambda = radians(lon2 - lon1)
    x = sin(d_lambda) * cos(phi2)
    y = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(d_lambda)
    return (atan2(x, y) * 180 / pi) % 360


def _local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    x = radians(lon - lon0) * EARTH_RADIUS_KM * cos(radians((lat + lat0) / 2))
    y = radians(lat - lat0) * EARTH_RADIUS_KM
    return x, y


def _is_collinear(points: list[tuple[float, float]]) -> bool:
    max_area = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            for k in range(j + 1, len(points)):
                (x1, y1), (x2, y2), (x3, y3) = points[i], points[j], points[k]
                area = abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2
                max_area = max(max_area, area)
    return max_area <= COLLINEARITY_EPSILON_KM2


def spatial_gradient(
    target_response: dict[str, Any],
    neighbor_responses: list[dict[str, Any]],
) -> dict[str, Any]:
    target_lat, target_lon = target_response.get("lat"), target_response.get("lon")
    township_items = [item for item in neighbor_responses if item.get("station_type") == "township"]
    township_with_coordinates = any(
        item.get("lat") is not None and item.get("lon") is not None for item in township_items
    )
    township_without_coordinates = any(
        item.get("lat") is None or item.get("lon") is None for item in township_items
    )
    township_coverage = (
        "available" if township_with_coordinates and not township_without_coordinates else
        "partial" if township_with_coordinates else
        "missing_coordinates"
    )
    if target_lat is None or target_lon is None:
        return {
            "spatial_status": "insufficient_coordinates",
            "reason": "target_station_coordinates_missing",
            "coordinate_coverage": {
                "regular": "available" if any(
                    item["coordinate_status"] == "available" for item in neighbor_responses
                ) else "missing",
                "township": township_coverage,
                "provincial": "not_integrated",
            },
            "township_note": "乡镇站无坐标，仅做浓度变化与区县汇总，不参与距离/方位/梯度计算",
            "expression_boundary": EXPRESSION_BOUNDARY,
        }
    geometry = []
    points: list[tuple[float, float]] = []
    for item in neighbor_responses:
        lat, lon = item.get("lat"), item.get("lon")
        if lat is None or lon is None or item["during_delta"] is None:
            continue
        distance_km = _haversine_km(target_lat, target_lon, lat, lon)
        if distance_km <= 1e-6:
            continue
        entry = {
            "station_id": item["station_id"],
            "station_type": item["station_type"],
            "distance_km": _round(distance_km, 2),
            "bearing_deg_from_target": _round(_bearing_deg(target_lat, target_lon, lat, lon), 1),
            "during_delta": item["during_delta"],
            "after_delta": item.get("after_delta"),
            "radial_gradient_per_km": _round(
                (item["during_delta"] - (target_response.get("during_delta") or 0.0)) / distance_km, 4
            ),
        }
        geometry.append(entry)
        points.append(_local_xy(lat, lon, target_lat, target_lon))
    unique_points = list(dict.fromkeys(points))
    plane_fit: dict[str, Any] = {
        "status": "not_run",
        "reason": None,
    }
    if len(unique_points) >= PLANE_FIT_MIN_STATIONS and _is_collinear(unique_points):
        plane_fit = {"status": "not_run", "reason": "collinear_or_degenerate_geometry"}
    elif len(unique_points) >= PLANE_FIT_MIN_STATIONS:
        deltas = []
        matrix = []
        used_points = []
        for point, item in zip(points, geometry, strict=True):
            if point not in used_points:
                used_points.append(point)
                deltas.append(item["during_delta"])
                matrix.append([point[0], point[1], 1.0])
        solution, *_ = np.linalg.lstsq(np.array(matrix), np.array(deltas), rcond=None)
        gradient_x, gradient_y = float(solution[0]), float(solution[1])
        plane_fit = {
            "status": "ok",
            "sample_count": len(deltas),
            "gradient_vector_per_km": {"east": _round(gradient_x, 4), "north": _round(gradient_y, 4)},
            "gradient_magnitude_per_km": _round(sqrt(gradient_x ** 2 + gradient_y ** 2), 4),
            "bearing_deg_toward_increase": _round((atan2(gradient_x, gradient_y) * 180 / pi) % 360, 1),
            "method": "least_squares_plane_fit_on_during_delta_over_local_east_north_km",
        }
    else:
        plane_fit = {
            "status": "not_run",
            "reason": f"fewer_than_{PLANE_FIT_MIN_STATIONS}_stations_with_coordinates_and_delta",
        }
    with_coords = len(geometry)
    if with_coords >= PLANE_FIT_MIN_STATIONS and plane_fit["status"] == "ok":
        spatial_status = "computed"
    elif with_coords >= 1:
        spatial_status = "partial_coordinates"
    else:
        spatial_status = "missing_coordinates"
    return {
        "spatial_status": spatial_status,
        "target_station": {
            "station_id": target_response["station_id"],
            "lat": target_lat,
            "lon": target_lon,
        },
        "coordinate_coverage": {
            "regular": "available",
            "township": township_coverage,
            "provincial": "not_integrated",
        },
        "neighbor_geometry": geometry,
        "neighbor_count_with_coordinates": with_coords,
        "neighbor_count_without_coordinates": sum(
            1 for item in neighbor_responses if item["coordinate_status"] == "missing_coordinates"
        ),
        "radial_gradient_rule": "(during_delta_neighbor - during_delta_target) / distance_km",
        "plane_fit": plane_fit,
        "township_note": "乡镇站无坐标，仅做浓度变化与区县汇总，不参与距离/方位/梯度计算",
        "expression_boundary": EXPRESSION_BOUNDARY,
    }


def district_summary(neighbor_responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    districts: dict[str, dict[str, Any]] = {}
    for item in neighbor_responses:
        if item.get("station_type") != "township" or not item.get("district"):
            continue
        bucket = districts.setdefault(item["district"], {
            "district": item["district"],
            "station_count": 0,
            "valid_during_count": 0,
            "rise_count": 0,
            "decline_count": 0,
            "during_delta_sum": 0.0,
            "delta_sample_count": 0,
        })
        bucket["station_count"] += 1
        if item["during_classification"] != "insufficient_data":
            bucket["valid_during_count"] += 1
        if item["during_classification"] == "rise":
            bucket["rise_count"] += 1
        if item["during_classification"] == "decline":
            bucket["decline_count"] += 1
        if item["during_delta"] is not None:
            bucket["during_delta_sum"] += item["during_delta"]
            bucket["delta_sample_count"] += 1
    summary = []
    for bucket in districts.values():
        delta_sum = bucket.pop("during_delta_sum")
        sample_count = bucket.pop("delta_sample_count")
        bucket["mean_during_delta"] = _round(delta_sum / sample_count) if sample_count else None
        summary.append(bucket)
    return sorted(summary, key=lambda item: item["district"])


def transport_consistency(
    regional: dict[str, Any], lead_lag: dict[str, Any], spatial: dict[str, Any]
) -> dict[str, Any]:
    classification = regional["classification"]
    if classification == "regional_co_rise" and (lead_lag["median_lead_hours_to_target"] or 0) < 0:
        conclusion = "neighbor_lead_rise"
    elif classification == "regional_co_rise":
        conclusion = "regional_co_rise"
    elif classification == "delayed_regional_rise":
        conclusion = "post_alert_spread"
    elif classification == "local_target_only":
        conclusion = "local_prominence"
    else:
        conclusion = "no_directional_conclusion"
    limits = [
        "结论仅描述站点观测时序与空间结构，不构成传输方向、源区或责任判断",
        EXPRESSION_BOUNDARY,
    ]
    if regional["classification"] == "insufficient_evidence":
        limits.append(f"区域分类证据不足: {regional.get('reason')}")
    if spatial["spatial_status"] in ("missing_coordinates", "insufficient_coordinates"):
        limits.append(f"空间证据受限: spatial_status={spatial['spatial_status']}")
    return {
        "conclusion": conclusion,
        "conclusion_label": ALLOWED_CONCLUSIONS[conclusion],
        "allowed_conclusions": dict(ALLOWED_CONCLUSIONS),
        "supporting_facts": {
            "regional_classification": classification,
            "during_rise_ratio": regional["during_rise_ratio"],
            "median_lead_hours_to_target": lead_lag["median_lead_hours_to_target"],
            "spatial_status": spatial["spatial_status"],
        },
        "evidence_limits": limits,
        "expression_boundary": EXPRESSION_BOUNDARY,
        "rule": (
            "regional_co_rise + median_lead<0 -> neighbor_lead_rise; "
            "regional_co_rise -> regional_co_rise; delayed_regional_rise -> post_alert_spread; "
            "local_target_only -> local_prominence; else no_directional_conclusion"
        ),
    }


def calculate_regional_response(
    anchor: dict[str, Any],
    *,
    regular_rows: list[dict[str, Any]],
    township_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute the full deterministic evidence block for one episode anchor."""
    pollutant = anchor.get("target_pollutant")
    base = {
        "analysis_id": anchor.get("analysis_id"),
        "episode_id": anchor.get("episode_id"),
        "parent_alert_event_ids": anchor.get("parent_alert_event_ids", []),
        "source_evidence_package_path": anchor.get("source_evidence_package_path"),
        "target_date": anchor.get("target_date"),
        "evidence_version": anchor.get("evidence_version"),
        "source_features": anchor.get("source_features", []),
        "alert_anchor": {
            "station_id": anchor.get("station_id"),
            "station_name": anchor.get("station_name"),
            "target_pollutant": pollutant,
            "episode_start": anchor.get("episode_start"),
            "episode_end": anchor.get("episode_end"),
            "alert_hours": anchor.get("alert_hours", []),
            "peak_time": anchor.get("peak_time"),
            "peak_value": anchor.get("peak_value"),
            "episode_status": anchor.get("episode_status"),
            "alert_type": anchor.get("alert_type"),
            "measurement_granularity": anchor.get("measurement_granularity"),
        },
        "data_sources": {
            "regular_stations": "dbo.dat_zhongda_station_hour（场景一告警基线同源）",
            "township_stations": "大气环境监测数据接口中台 v_t_h_src（乡镇小时-原始）",
            "provincial_stations": "not_integrated",
        },
    }
    series_key = POLLUTANT_SERIES_KEY.get(str(pollutant))
    thresholds = REGIONAL_RISE_THRESHOLDS.get(str(pollutant))
    if series_key is None or thresholds is None:
        return {
            **base,
            "calculation_status": "not_enabled_for_pollutant",
            "enabled_pollutants": sorted(REGIONAL_RISE_THRESHOLDS),
            "threshold_version": THRESHOLD_VERSION,
        }
    windows = _window_hours(anchor["episode_start"], anchor["episode_end"])
    episode_start = normalize_hour(anchor["episode_start"])
    target_id = str(anchor["station_id"])
    target_station_payload = next(
        (
            {"station_id": target_id, "name": row.get("name"), "station_type": "regular",
             "district": None, "lat": row.get("lat"), "lon": row.get("lon")}
            for row in regular_rows if str(row.get("station_id")) == target_id
        ),
        {"station_id": target_id, "name": anchor.get("station_name"), "station_type": "regular",
         "district": None, "lat": None, "lon": None},
    )
    neighbor_ids: list[dict[str, Any]] = []
    seen_ids: set[str] = {target_id}
    for row in regular_rows:
        station_id = str(row.get("station_id") or "")
        if not station_id or station_id in seen_ids:
            continue
        seen_ids.add(station_id)
        neighbor_ids.append({
            "station_id": station_id, "name": row.get("name"), "station_type": "regular",
            "district": None, "lat": row.get("lat"), "lon": row.get("lon"),
        })
    township_by_id: dict[str, dict[str, Any]] = {}
    for row in township_rows:
        station_id = str(row.get("station_id") or "")
        if not station_id:
            continue
        township_by_id[station_id] = {
            "station_id": station_id, "name": row.get("name"), "station_type": "township",
            "district": row.get("district"), "lat": row.get("lat"), "lon": row.get("lon"),
        }
    all_rows = list(regular_rows) + list(township_rows)
    target_response = classify_station_response(
        target_station_payload, _series(all_rows, target_id, series_key),
        windows, episode_start, thresholds, is_target=True,
    )
    neighbor_responses = [
        classify_station_response(
            station, _series(all_rows, station["station_id"], series_key),
            windows, episode_start, thresholds, is_target=False,
        )
        for station in [*neighbor_ids, *township_by_id.values()]
    ]
    regional = regional_classification(target_response, neighbor_responses)
    lead_lag = temporal_lead_lag(neighbor_responses, anchor["episode_start"])
    spatial = spatial_gradient(target_response, neighbor_responses)
    geometry_by_id = {
        item["station_id"]: item
        for item in spatial.get("neighbor_geometry", [])
    }
    map_records = []
    for item in [target_response, *neighbor_responses]:
        if item.get("lat") is None or item.get("lon") is None:
            continue
        during = item.get("during") or {}
        geometry = geometry_by_id.get(item["station_id"], {})
        target_mean = (target_response.get("during") or {}).get("mean")
        concentration = during.get("mean")
        map_records.append({
            "station_id": item["station_id"],
            "station_name": item.get("station_name"),
            "station_type": item.get("station_type"),
            "district": item.get("district"),
            "longitude": item["lon"],
            "latitude": item["lat"],
            "concentration": concentration,
            "comparison": (
                "target" if item.get("is_target") else
                "higher_than_target" if concentration is not None and target_mean is not None and concentration > target_mean else
                "lower_or_equal_target"
            ),
            "distance_km": geometry.get("distance_km"),
            "bearing_deg": geometry.get("bearing_deg_from_target"),
            "during_delta": item.get("during_delta"),
            "during_classification": item.get("during_classification"),
        })
    spatial_map = {
        "status": "ready" if map_records else "no_coordinates",
        "target_station_id": target_response["station_id"],
        "pollutant": pollutant,
        "records": map_records,
        "line_rule": "连接目标国控点与有坐标乡镇站，仅表示空间对比关系，不表示污染贡献率",
    }
    if not anchor.get("peak_time") and target_response["during"]["status"] == "ok":
        during_values = {
            hour: value for hour, value in _series(all_rows, target_id, series_key).items()
            if hour in windows["during"]
        }
        if during_values:
            peak_hour = max(sorted(during_values), key=lambda hour: during_values[hour])
            target_response["peak_fallback"] = {
                "peak_time": peak_hour.isoformat(),
                "peak_value": _round(during_values[peak_hour]),
                "source": "target_station_hourly_max_within_during_window",
            }
    return {
        **base,
        "calculation_status": "calculated",
        "threshold_version": THRESHOLD_VERSION,
        "thresholds": dict(thresholds),
        "series_proxy_note": (
            "NOX告警以站点NO2小时浓度为空间异常代理" if str(pollutant) == "NOX" else None
        ),
        "rise_rule": RISE_RULE_TEMPLATE.format(**thresholds),
        "window_policy": build_window_policy(windows),
        "target_response": target_response,
        "station_response_by_window": neighbor_responses,
        "regional_co_rise": regional,
        "temporal_lead_lag": lead_lag,
        "spatial_gradient": spatial,
        "spatial_map": spatial_map,
        "township_district_summary": district_summary(neighbor_responses),
        "transport_consistency": transport_consistency(regional, lead_lag, spatial),
    }
