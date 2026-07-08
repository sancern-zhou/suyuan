from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


PM25_DOMAIN = "PM2.5组分"
VOCS_DOMAIN = "VOCs"


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            return parent
    return current.parents[3]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_city_mapping(path: Path) -> dict[str, list[str]]:
    payload = _read_json(path)
    mappings: dict[str, list[str]] = {}
    for city, stations in payload.get("mappings", {}).items():
        city_key = str(city).strip().removesuffix("市")
        if isinstance(stations, str):
            stations = [stations]
        mappings[city_key] = [str(station).strip() for station in stations or [] if str(station).strip()]
    return mappings


def _domain_mapping(data_domain: str) -> dict[str, list[str]]:
    root = _repo_root()
    if data_domain == PM25_DOMAIN:
        return _load_city_mapping(root / "backend" / "app" / "config" / "particulate_city_multi_station_mapping.json")
    if data_domain == VOCS_DOMAIN:
        return _load_city_mapping(root / "backend" / "app" / "config" / "vocs_city_station_mapping.json")
    return {}


def resolve_component_station_names(
    city: str,
    *,
    data_domain: str,
    station_names: Iterable[str] | None = None,
) -> list[str]:
    """Return configured component station names for a city and data domain."""
    mapping = _domain_mapping(data_domain)
    city_key = str(city or "").strip().removesuffix("市")
    configured_names = {
        station
        for stations in mapping.values()
        for station in stations
    }
    names: list[str] = []
    for station_name in mapping.get(city_key, []):
        if station_name not in names:
            names.append(station_name)
    for station in station_names or []:
        station_name = str(station or "").strip()
        if station_name in configured_names and station_name not in names:
            names.append(station_name)
    return names
