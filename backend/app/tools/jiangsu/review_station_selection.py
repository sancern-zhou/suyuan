"""Select same-district stations and rank known coordinates for SOP reviews."""

from __future__ import annotations

import math
from typing import Any

from app.tools.jiangsu.station_type import station_type_from_row


def _text(row: dict[str, Any], *keys: str) -> str:
    return next((str(row[key]).strip() for key in keys if row.get(key)), "")


def _coordinates(row: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lon = float(_text(row, "longitude", "Longitude", "lng"))
        lat = float(_text(row, "latitude", "Latitude", "lat"))
    except ValueError:
        return None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return (lon, lat) if (lon, lat) != (0, 0) else None


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def select_district_stations(station: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    code = str(station.get("station_code") or "").strip()
    directory = {_text(row, "stationCode", "StationCode"): row for row in rows if _text(row, "stationCode", "StationCode")}
    target = directory.get(code, {})
    district_code = _text(target, "districtCode", "areaCode") or _text(station, "district_code")
    district_name = _text(target, "districtName") or _text(station, "district_name")
    city_name = _text(target, "cityName") or _text(station, "city_name")
    city_code = _text(target, "cityCode") or _text(station, "city_code")
    if not code or not (district_code or (district_name and (city_code or city_name))):
        raise ValueError("缺少可唯一定位的站点/区县信息，无法查询同区站点。")
    origin = _coordinates(target) or _coordinates(station)
    neighbors = []
    for candidate_code, row in directory.items():
        if candidate_code == code:
            continue
        # Same-district evidence must use the same provincial-control
        # monitoring population as the fault-work-order workflow.  Unknown
        # types are excluded so a missing classification cannot silently
        # broaden the comparison scope.
        if station_type_from_row(row) != "省控":
            continue
        candidate_district = _text(row, "districtCode", "areaCode")
        if district_code and candidate_district:
            same_district = district_code == candidate_district
        else:
            same_city = city_code == _text(row, "cityCode") if city_code and _text(row, "cityCode") else city_name == _text(row, "cityName")
            same_district = bool(district_name and same_city and district_name == _text(row, "districtName"))
        if not same_district:
            continue
        coordinates = _coordinates(row)
        distance = _distance(origin, coordinates) if origin and coordinates else None
        neighbors.append({
            "station_code": candidate_code,
            "station_name": _text(row, "positionName", "stationName") or candidate_code,
            "station_type": "省控",
            "distance_km": distance,
        })
    neighbors.sort(key=lambda item: (item["distance_km"] is None, item["distance_km"] or 0, item["station_code"]))
    ranked_neighbors = [item for item in neighbors if item["distance_km"] is not None][:3]
    nearest = ranked_neighbors[0]["station_code"] if ranked_neighbors else None
    complete = bool(neighbors) and all(item["distance_km"] is not None for item in neighbors)
    for item in neighbors:
        item["is_nearest"] = item["station_code"] == nearest
        if item["distance_km"] is not None:
            item["distance_km"] = round(item["distance_km"], 3)
    note = "同区省控站点按直线距离由近到远排列。"
    if not neighbors:
        note = "目录中未找到其他同区站点。"
    elif not nearest:
        note = "缺少有效经纬度，无法判断最近站点；保留同区站点。"
    elif not complete:
        note = "部分站点缺少经纬度；最近站点仅指可计算距离的同区站点。"
    return {
        "comparison_scope": "same_district", "target_station_code": code,
        "station_type": "省控",
        "city_name": city_name, "district_name": district_name, "district_code": district_code,
        "comparison_stations": neighbors, "nearest_station_code": nearest,
        "distance_ranking_complete": complete, "selection_note": note,
        "station_codes": [item["station_code"] for item in neighbors] + [code],
    }
