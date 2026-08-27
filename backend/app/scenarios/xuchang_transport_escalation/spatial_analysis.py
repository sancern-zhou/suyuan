"""Local corridor identification and conservative trajectory-enterprise screening."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import asin, atan2, cos, degrees, exp, log1p, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

from app.tools.analysis.xuchang_upwind_permit_sources.engine import (
    XUCHANG_WEATHER_STATIONS,
    nearest_station,
)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

SECTORS = (
    ("N", "北部通道"),
    ("NE", "东北通道"),
    ("E", "东部通道"),
    ("SE", "东南通道"),
    ("S", "南部通道"),
    ("SW", "西南通道"),
    ("W", "西部通道"),
    ("NW", "西北通道"),
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    value = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * radius_km * asin(sqrt(value))


ENTERPRISE_FILTERS = {
    "PM2.5": {"max_height_m": 500.0, "max_age_hours": 24.0, "buffer_km": 5.0},
    "O3": {"max_height_m": 500.0, "max_age_hours": 24.0, "buffer_km": 10.0},
    "NOX": {"max_height_m": 300.0, "max_age_hours": 12.0, "buffer_km": 3.0},
}
ENTERPRISE_SCORE_WEIGHTS = {
    "trajectory_hit": 0.30,
    "pollutant_relevance": 0.20,
    "emission_intensity": 0.25,
    "path_distance": 0.15,
    "wind_transport": 0.10,
}


def _pollutant_relevance(pollutant: str, permit_pollutants: str | None) -> str:
    text = (permit_pollutants or "").lower().replace(" ", "")
    mappings = {
        "PM2.5": (
            ("颗粒物", "烟尘"),
            ("二氧化硫", "so2", "氮氧化物", "nox", "挥发性有机物", "vocs"),
        ),
        "O3": ((), ("vocs", "挥发性有机物", "非甲烷总烃", "氮氧化物", "nox", "no2")),
        "NOX": (("二氧化氮", "氮氧化物", "nox", "no2"), ()),
    }
    direct, precursor = mappings[pollutant]
    if any(token in text for token in direct):
        return "exact_match"
    if any(token in text for token in precursor):
        return "precursor_match"
    return "no_recorded_match"


def _emission_indicator(pollutant: str, emissions: dict[str, Any] | None) -> float | None:
    if not emissions:
        return None
    fields = {
        "PM2.5": ("emission_pm25",),
        "O3": ("emission_vocs", "emission_nox"),
        "NOX": ("emission_nox",),
    }[pollutant]
    try:
        return sum(max(0.0, float(emissions.get(field) or 0.0)) for field in fields)
    except (TypeError, ValueError):
        return None


def _strongest_relevance(permit_relevance: str, emission_value: float | None, pollutant: str) -> str:
    inventory_relevance = (
        "precursor_match"
        if pollutant == "O3" and emission_value is not None and emission_value > 0
        else "exact_match"
        if emission_value is not None and emission_value > 0
        else "no_recorded_match"
    )
    rank = {"no_recorded_match": 0, "precursor_match": 1, "exact_match": 2}
    return max((permit_relevance, inventory_relevance), key=rank.get)


def _hour(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_lon = radians(lon2 - lon1)
    y = sin(delta_lon) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(delta_lon)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def _sector(bearing: float) -> tuple[str, str]:
    return SECTORS[int((bearing + 22.5) // 45) % 8]


def _circular_mean_deg(values: list[float]) -> float:
    x = sum(cos(radians(value)) for value in values)
    y = sum(sin(radians(value)) for value in values)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def identify_transport_corridors(
    endpoints: list[dict[str, Any]],
    *,
    receptor_lat: float,
    receptor_lon: float,
) -> list[dict[str, Any]]:
    """Summarize trajectory origins by geographic sector without claiming a source."""
    trajectories: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for endpoint in endpoints:
        key = (int(endpoint.get("batch_index", 0)), int(endpoint.get("trajectory_id", 1)))
        trajectories[key].append(endpoint)

    grouped: dict[str, dict[str, Any]] = {}
    for key, points in trajectories.items():
        farthest = max(points, key=lambda item: abs(float(item.get("age_hours", 0))))
        bearing = _bearing_deg(
            receptor_lat, receptor_lon, float(farthest["lat"]), float(farthest["lon"])
        )
        sector, label = _sector(bearing)
        item = grouped.setdefault(
            sector,
            {
                "sector": sector,
                "label": label,
                "trajectory_keys": [],
                "bearings": [],
                "distances_km": [],
            },
        )
        item["trajectory_keys"].append(f"{key[0]}:{key[1]}")
        item["bearings"].append(bearing)
        item["distances_km"].append(
            _haversine_km(
                receptor_lat, receptor_lon, float(farthest["lat"]), float(farthest["lon"])
            )
        )

    total = max(1, len(trajectories))
    corridors = []
    for item in grouped.values():
        count = len(item["trajectory_keys"])
        corridors.append(
            {
                "sector": item["sector"],
                "label": item["label"],
                "trajectory_count": count,
                "trajectory_share": round(count / total, 3),
                "mean_bearing_deg": round(_circular_mean_deg(item["bearings"]), 1),
                "mean_path_extent_km": round(sum(item["distances_km"]) / count, 1),
                "trajectory_keys": item["trajectory_keys"],
                "method": "endpoint_origin_sector_screening",
            }
        )
    return sorted(corridors, key=lambda item: item["trajectory_count"], reverse=True)


def identify_transport_corridors_by_height(
    endpoints: list[dict[str, Any]],
    *,
    heights_m_agl: list[int],
    receptor_lat: float,
    receptor_lon: float,
) -> dict[str, list[dict[str, Any]]]:
    """Keep vertical transport regimes separate when summarizing corridors."""
    corridors_by_height = {}
    for trajectory_id, height in enumerate(heights_m_agl, 1):
        height_endpoints = [
            endpoint
            for endpoint in endpoints
            if int(endpoint.get("trajectory_id", 1)) == trajectory_id
        ]
        corridors = identify_transport_corridors(
            height_endpoints,
            receptor_lat=receptor_lat,
            receptor_lon=receptor_lon,
        )
        for corridor in corridors:
            corridor["start_height_m_agl"] = height
        corridors_by_height[str(height)] = corridors
    return corridors_by_height


def _interpolate_low_level_points(
    endpoints: list[dict[str, Any]],
    *,
    max_height_m: float,
    max_age_hours: float,
) -> list[dict[str, Any]]:
    trajectories: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for endpoint in endpoints:
        if float(endpoint.get("height", 0)) > max_height_m:
            continue
        if abs(float(endpoint.get("age_hours", 0))) > max_age_hours:
            continue
        key = (int(endpoint.get("batch_index", 0)), int(endpoint.get("trajectory_id", 1)))
        trajectories[key].append(endpoint)

    interpolated = []
    for key, points in trajectories.items():
        ordered = sorted(points, key=lambda item: abs(float(item.get("age_hours", 0))))
        for first, second in zip(ordered, ordered[1:], strict=False):
            distance = _haversine_km(
                float(first["lat"]), float(first["lon"]), float(second["lat"]), float(second["lon"])
            )
            steps = max(1, min(10, int(distance / 5.0) + 1))
            for index in range(steps):
                ratio = index / steps
                interpolated.append(
                    {
                        "lat": float(first["lat"])
                        + (float(second["lat"]) - float(first["lat"])) * ratio,
                        "lon": float(first["lon"])
                        + (float(second["lon"]) - float(first["lon"])) * ratio,
                        "age_hours": float(first.get("age_hours", 0)),
                        "height": float(first.get("height", 0)),
                        "trajectory_key": f"{key[0]}:{key[1]}",
                        "arrival_time": first.get("arrival_time"),
                    }
                )
        if ordered:
            last = ordered[-1]
            interpolated.append(
                {
                    "lat": float(last["lat"]),
                    "lon": float(last["lon"]),
                    "age_hours": float(last.get("age_hours", 0)),
                    "height": float(last.get("height", 0)),
                    "trajectory_key": f"{key[0]}:{key[1]}",
                    "arrival_time": last.get("arrival_time"),
                }
            )
    return interpolated


class TrajectoryEnterpriseScreener:
    def __init__(self, repository: Any | None = None) -> None:
        if repository is None:
            # Defer this import because the permit models currently live below
            # app.fetchers, whose package initializer registers Scenario 2.
            from app.tools.analysis.xuchang_upwind_permit_sources.repository import (
                XuchangUpwindPermitRepository,
            )

            repository = XuchangUpwindPermitRepository()
        self.repository = repository

    async def screen(
        self,
        endpoints: list[dict[str, Any]],
        *,
        pollutant: str,
        receptor_lat: float | None = None,
        receptor_lon: float | None = None,
        top_n: int = 30,
    ) -> dict[str, Any]:
        config = ENTERPRISE_FILTERS[pollutant]
        path_points = _interpolate_low_level_points(
            endpoints,
            **{
                "max_height_m": config["max_height_m"],
                "max_age_hours": config["max_age_hours"],
            },
        )
        if not path_points:
            return {"enterprises": [], "coverage": {**config, "path_point_count": 0}}

        margin = config["buffer_km"] / 100.0
        candidates = await self.repository.load_candidates_in_bounds(
            min_lat=min(item["lat"] for item in path_points) - margin,
            max_lat=max(item["lat"] for item in path_points) + margin,
            min_lon=min(item["lon"] for item in path_points) - margin,
            max_lon=max(item["lon"] for item in path_points) + margin,
        )
        wind_by_hour, wind_coverage = await self._load_wind_by_hour(
            path_points,
            receptor_lat=receptor_lat,
            receptor_lon=receptor_lon,
        )
        matched = []
        pollutant_mismatch_count = 0
        for candidate in candidates:
            distances = [
                (
                    _haversine_km(
                        float(candidate["latitude"]),
                        float(candidate["longitude"]),
                        point["lat"],
                        point["lon"],
                    ),
                    point,
                )
                for point in path_points
            ]
            minimum_distance, closest = min(distances, key=lambda item: item[0])
            if minimum_distance > config["buffer_km"]:
                continue
            permit_pollutant_text = " ".join(
                filter(
                    None,
                    [
                        candidate.get("permit_pollutants"),
                        candidate.get("main_pollutant_categories"),
                    ],
                )
            )
            permit_relevance = _pollutant_relevance(pollutant, permit_pollutant_text)
            emission_value = _emission_indicator(
                pollutant, candidate.get("inventory_emissions")
            )
            relevance = _strongest_relevance(permit_relevance, emission_value, pollutant)
            if relevance == "no_recorded_match":
                pollutant_mismatch_count += 1
                continue
            matched_keys = {
                point["trajectory_key"]
                for distance, point in distances
                if distance <= config["buffer_km"]
            }
            matched_hours = sorted({
                point["arrival_time"]
                for distance, point in distances
                if distance <= config["buffer_km"] and point.get("arrival_time")
            })
            wind_values = [
                wind_by_hour[_hour(value).isoformat()]
                for value in matched_hours
                if _hour(value).isoformat() in wind_by_hour
            ]
            hourly_min_distances = {
                arrival_time: round(min(
                    distance
                    for distance, point in distances
                    if point.get("arrival_time") == arrival_time
                ), 3)
                for arrival_time in matched_hours
            }
            wind_speeds_by_hour = {
                arrival_time: wind_by_hour.get(_hour(arrival_time).isoformat())
                for arrival_time in matched_hours
            }
            matched.append(
                {
                    **candidate,
                    "pollutant_relevance": relevance,
                    "permit_pollutant_relevance": permit_relevance,
                    "emission_value_tonnes": emission_value,
                    "minimum_path_distance_km": round(minimum_distance, 2),
                    "closest_path_age_hours": round(abs(float(closest["age_hours"])), 1),
                    "closest_path_height_m": round(float(closest["height"]), 1),
                    "matched_trajectory_count": len(matched_keys),
                    "matched_hour_count": len(matched_hours),
                    "matched_arrival_hours": matched_hours,
                    "hourly_min_path_distance_km": hourly_min_distances,
                    "wind_speeds_by_hour_ms": wind_speeds_by_hour,
                    "mean_wind_speed_ms": (
                        round(sum(wind_values) / len(wind_values), 3)
                        if wind_values else None
                    ),
                    "screening_label": "trajectory_coverage_candidate",
                }
            )
        self._score_matches(matched, config=config, total_hours=len({
            point.get("arrival_time") for point in path_points if point.get("arrival_time")
        }))
        matched.sort(key=lambda item: item["final_screening_score"], reverse=True)
        hourly_analyses = self._hourly_analyses(
            matched, config=config, top_n=min(top_n, 10)
        )
        return {
            "enterprises": matched[:top_n],
            "hourly_candidate_analyses": hourly_analyses,
            "coverage": {
                **config,
                "path_point_count": len(path_points),
                "candidate_count": len(candidates),
                "matched_count": len(matched),
                "pollutant_mismatch_excluded_count": pollutant_mismatch_count,
                "pollutant_filter": "permit_or_inventory_pollutant_match",
                "hourly_analysis_count": len(hourly_analyses),
                "wind": wind_coverage,
                "score_weights": ENTERPRISE_SCORE_WEIGHTS,
                "score_method": "weighted_normalized_evidence_score",
                "interpretation_limit": "企业仅为低层轨迹缓冲区覆盖候选，不表示排放贡献或责任。",
            },
        }

    async def _load_wind_by_hour(
        self,
        path_points: list[dict[str, Any]],
        *,
        receptor_lat: float | None,
        receptor_lon: float | None,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        loader = getattr(self.repository, "load_weather", None)
        arrival_times = sorted({
            _hour(point["arrival_time"])
            for point in path_points
            if point.get("arrival_time")
        })
        if loader is None or receptor_lat is None or receptor_lon is None or not arrival_times:
            return {}, {"status": "unavailable", "matched_hours": 0}
        representative = nearest_station(receptor_lat, receptor_lon)
        observed, _ = await loader(
            station_ids=[station.station_id for station in XUCHANG_WEATHER_STATIONS],
            start_time=arrival_times[0],
            end_time=arrival_times[-1],
            receptor_lat=receptor_lat,
            receptor_lon=receptor_lon,
        )
        wind = {}
        for record in observed:
            if record.station_id != representative.station_id or record.wind_speed_10m is None:
                continue
            speed = float(record.wind_speed_10m)
            if speed >= 0:
                wind[_hour(record.time).isoformat()] = speed
        return wind, {
            "status": "available" if wind else "unavailable",
            "representative_station_id": representative.station_id,
            "representative_station_name": representative.station_name,
            "requested_hours": len(arrival_times),
            "matched_hours": len(wind),
            "normalization": "clip((wind_speed_ms - 0.5) / 4.5, 0, 1)",
        }

    @staticmethod
    def _score_matches(
        matched: list[dict[str, Any]], *, config: dict[str, float], total_hours: int
    ) -> None:
        max_log_emission = max(
            (
                log1p(float(item["emission_value_tonnes"]))
                for item in matched
                if item.get("emission_value_tonnes") is not None
            ),
            default=0.0,
        )
        relevance_scores = {"exact_match": 1.0, "precursor_match": 0.8, "no_recorded_match": 0.0}
        for item in matched:
            emission = item.get("emission_value_tonnes")
            components = {
                "trajectory_hit": min(1.0, item["matched_hour_count"] / max(1, total_hours)),
                "pollutant_relevance": relevance_scores[item["pollutant_relevance"]],
                "emission_intensity": (
                    log1p(float(emission)) / max_log_emission
                    if emission is not None and max_log_emission > 0 else 0.0
                ),
                "path_distance": exp(-item["minimum_path_distance_km"] / config["buffer_km"]),
                "wind_transport": (
                    min(1.0, max(0.0, (item["mean_wind_speed_ms"] - 0.5) / 4.5))
                    if item.get("mean_wind_speed_ms") is not None else 0.5
                ),
            }
            item["normalized_scores"] = {
                key: round(value, 6) for key, value in components.items()
            }
            item["final_screening_score"] = round(sum(
                components[key] * ENTERPRISE_SCORE_WEIGHTS[key]
                for key in ENTERPRISE_SCORE_WEIGHTS
            ), 6)
            item["score_type"] = "screening_priority_not_contribution"

    @staticmethod
    def _hourly_analyses(
        matched: list[dict[str, Any]], *, config: dict[str, float], top_n: int
    ) -> list[dict[str, Any]]:
        by_hour: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for enterprise in matched:
            for arrival_time in enterprise["matched_arrival_hours"]:
                distance = enterprise["hourly_min_path_distance_km"][arrival_time]
                wind_speed = enterprise["wind_speeds_by_hour_ms"].get(arrival_time)
                components = {
                    "trajectory_hit": 1.0,
                    "pollutant_relevance": enterprise["normalized_scores"]["pollutant_relevance"],
                    "emission_intensity": enterprise["normalized_scores"]["emission_intensity"],
                    "path_distance": exp(-distance / config["buffer_km"]),
                    "wind_transport": (
                        min(1.0, max(0.0, (wind_speed - 0.5) / 4.5))
                        if wind_speed is not None else 0.5
                    ),
                }
                hourly_score = sum(
                    components[key] * ENTERPRISE_SCORE_WEIGHTS[key]
                    for key in ENTERPRISE_SCORE_WEIGHTS
                )
                by_hour[arrival_time].append({
                    "enterprise_name": enterprise["enterprise_name"],
                    "industry_category": enterprise.get("industry_category"),
                    "minimum_path_distance_km": distance,
                    "pollutant_relevance": enterprise["pollutant_relevance"],
                    "emission_value_tonnes": enterprise.get("emission_value_tonnes"),
                    "wind_speed_ms": wind_speed,
                    "normalized_scores": {
                        key: round(value, 6) for key, value in components.items()
                    },
                    "final_screening_score": round(hourly_score, 6),
                    "data_sources": enterprise.get("data_sources") or [],
                })
        return [
            {
                "arrival_time": arrival_time,
                "candidates": sorted(
                    candidates,
                    key=lambda item: item["final_screening_score"],
                    reverse=True,
                )[:top_n],
            }
            for arrival_time, candidates in sorted(by_hour.items())
        ]
