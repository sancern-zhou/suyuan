"""Interactive map programs for Xuchang Scenario 2 transport analysis."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


def _feature(geometry: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def _trajectory_features(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for endpoint in endpoints:
        key = (
            int(endpoint.get("batch_index", 0)),
            int(endpoint.get("trajectory_id", 1)),
        )
        grouped[key].append(endpoint)

    features = []
    for (batch_index, trajectory_id), points in sorted(grouped.items()):
        ordered = sorted(points, key=lambda item: abs(float(item.get("age_hours", 0))))
        coordinates = [
            [float(item["lon"]), float(item["lat"])]
            for item in ordered
            if item.get("lon") is not None and item.get("lat") is not None
        ]
        if len(coordinates) < 2:
            continue
        features.append(
            _feature(
                {"type": "LineString", "coordinates": coordinates},
                {
                    "batch_index": batch_index,
                    "trajectory_id": trajectory_id,
                    "start_height_m_agl": float(ordered[0].get("height", 0)),
                },
            )
        )
    return features


def _station_feature(
    *, station_name: str, receptor_lat: float, receptor_lon: float, pollutant: str
) -> dict[str, Any]:
    return _feature(
        {"type": "Point", "coordinates": [receptor_lon, receptor_lat]},
        {
            "station_name": station_name,
            "target_pollutant": pollutant,
            "feature_role": "receptor",
        },
    )


def _enterprise_features(enterprise_screening: dict[str, Any]) -> list[dict[str, Any]]:
    features = []
    for enterprise in enterprise_screening.get("enterprises", []):
        longitude = enterprise.get("longitude")
        latitude = enterprise.get("latitude")
        if longitude is None or latitude is None:
            continue
        features.append(
            _feature(
                {"type": "Point", "coordinates": [float(longitude), float(latitude)]},
                {
                    "enterprise_name": enterprise.get("enterprise_name"),
                    "industry_category": enterprise.get("industry_category"),
                    "pollutant_relevance": enterprise.get("pollutant_relevance"),
                    "minimum_path_distance_km": enterprise.get("minimum_path_distance_km"),
                    "matched_trajectory_count": enterprise.get("matched_trajectory_count"),
                },
            )
        )
    return features


def _program(
    *,
    program_id: str,
    intent: str,
    receptor: dict[str, Any],
    trajectory_features: list[dict[str, Any]],
    enterprise_features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    layers = [
        {
            "id": f"{program_id}-trajectory",
            "name": "后向轨迹",
            "layer_type": "line",
            "data": {"type": "inline_geojson", "features": trajectory_features},
            "geometry": {"type": "geojson", "geometry_field": "geometry"},
            "style": {
                "type": "classified",
                "field": "start_height_m_agl",
                "colors": ["#d95f02", "#1b9e77", "#5e4fa2"],
                "stroke_weight": 2,
                "stroke_opacity": 0.75,
            },
            "interactions": {
                "selectable": True,
                "popup_fields": ["batch_index", "trajectory_id", "start_height_m_agl"],
            },
        },
        {
            "id": f"{program_id}-receptor",
            "name": "异常受体站",
            "layer_type": "point",
            "data": {"type": "inline_geojson", "features": [receptor]},
            "geometry": {"type": "geojson", "geometry_field": "geometry"},
            "style": {"type": "simple", "color": "#c53030", "size": 14},
            "interactions": {
                "selectable": True,
                "popup_fields": ["station_name", "target_pollutant"],
            },
        },
    ]
    if enterprise_features is not None:
        layers.append(
            {
                "id": f"{program_id}-enterprises",
                "name": "轨迹覆盖企业",
                "layer_type": "point",
                "data": {"type": "inline_geojson", "features": enterprise_features},
                "geometry": {"type": "geojson", "geometry_field": "geometry"},
                "style": {
                    "type": "classified",
                    "field": "pollutant_relevance",
                    "colors": ["#c53030", "#dd6b20", "#718096"],
                    "size": 9,
                },
                "interactions": {
                    "selectable": True,
                    "popup_fields": [
                        "enterprise_name",
                        "industry_category",
                        "pollutant_relevance",
                        "minimum_path_distance_km",
                    ],
                },
            }
        )

    return {
        "type": "map_program",
        "version": "0.1",
        "renderer": "amap-compatible",
        "program_id": program_id,
        "intent": intent,
        "state": {"view": {"fit_bounds": True}, "layers": layers},
        "lineage": {
            "analysis_crs": "WGS84",
            "display_crs": "GCJ02",
            "coordinate_conversion": "frontend_renderer",
        },
    }


def build_transport_map_programs(
    *,
    job_id: str,
    station_name: str,
    pollutant: str,
    endpoints: list[dict[str, Any]],
    corridors: list[dict[str, Any]],
    enterprise_screening: dict[str, Any],
    receptor_lat: float,
    receptor_lon: float,
) -> dict[str, dict[str, Any]]:
    del corridors
    trajectories = _trajectory_features(endpoints)
    receptor = _station_feature(
        station_name=station_name,
        receptor_lat=receptor_lat,
        receptor_lon=receptor_lon,
        pollutant=pollutant,
    )
    enterprises = _enterprise_features(enterprise_screening)
    return {
        "regional": _program(
            program_id=f"{job_id}-regional",
            intent=f"展示{station_name}{pollutant}区域后向轨迹",
            receptor=receptor,
            trajectory_features=trajectories,
        ),
        "enterprise": _program(
            program_id=f"{job_id}-enterprise",
            intent=f"展示{station_name}{pollutant}近地轨迹覆盖企业",
            receptor=receptor,
            trajectory_features=trajectories,
            enterprise_features=enterprises,
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def write_transport_map_programs(
    *, output_dir: Path, job_id: str, programs: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    artifacts = []
    for key, role, title in (
        ("regional", "regional_interactive_map", "区域后向轨迹交互地图"),
        ("enterprise", "enterprise_interactive_map", "轨迹覆盖企业交互地图"),
    ):
        path = output_dir / f"{job_id}.{key}-map-program.json"
        _write_json(path, programs[key])
        artifacts.append(
            {
                "type": "map_program",
                "role": role,
                "path": path,
                "title": title,
            }
        )
    return artifacts
