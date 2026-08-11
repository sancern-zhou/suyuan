"""Local corridor identification and conservative trajectory-enterprise screening."""

from __future__ import annotations

from collections import defaultdict
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from typing import Any

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
            relevance = _pollutant_relevance(pollutant, permit_pollutant_text)
            if relevance == "no_recorded_match":
                pollutant_mismatch_count += 1
                continue
            matched_keys = {
                point["trajectory_key"]
                for distance, point in distances
                if distance <= config["buffer_km"]
            }
            matched.append(
                {
                    **candidate,
                    "pollutant_relevance": relevance,
                    "minimum_path_distance_km": round(minimum_distance, 2),
                    "closest_path_age_hours": round(abs(float(closest["age_hours"])), 1),
                    "closest_path_height_m": round(float(closest["height"]), 1),
                    "matched_trajectory_count": len(matched_keys),
                    "screening_label": "trajectory_coverage_candidate",
                }
            )
        matched.sort(
            key=lambda item: (
                item["pollutant_relevance"] == "no_recorded_match",
                item["minimum_path_distance_km"],
                -item["matched_trajectory_count"],
            )
        )
        return {
            "enterprises": matched[:top_n],
            "coverage": {
                **config,
                "path_point_count": len(path_points),
                "candidate_count": len(candidates),
                "matched_count": len(matched),
                "pollutant_mismatch_excluded_count": pollutant_mismatch_count,
                "pollutant_filter": "exclude_permit_pollutant_mismatch",
                "interpretation_limit": "企业仅为低层轨迹缓冲区覆盖候选，不表示排放贡献或责任。",
            },
        }
