"""Load the project semantic registry used to explain Cube results."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from app.utils.path_config import resolve_agent_path

REGISTRY_PATH = resolve_agent_path(
    "projects/jiangsu-ops/data-ops/semantic/registry.yaml"
)


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    try:
        with REGISTRY_PATH.open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {"version": 0, "project": "jiangsu-ops", "cubes": {}}
    cubes = value.get("cubes")
    if not isinstance(cubes, dict):
        value["cubes"] = {}
    return value


def cube_metadata(cube: str, catalog: dict[str, Any]) -> dict[str, Any]:
    """Return explainable metadata, with catalog titles as a safe fallback."""
    entry = dict(load_registry().get("cubes", {}).get(cube) or {})
    measures = entry.get("measures") if isinstance(entry.get("measures"), dict) else {}
    catalog_measures = catalog.get(cube, {}).get("measures", [])
    for item in catalog_measures:
        name = item.get("name")
        if name and name not in measures:
            measures[name] = {"name": item.get("title", name), "definition": item.get("title", name)}
    entry["measures"] = {
        name: dict(spec) for name, spec in measures.items()
    }
    entry["registry_version"] = load_registry().get("version", 0)
    return entry


def dataset_metadata(dataset: str) -> dict[str, Any]:
    """Return the registered semantic entry for a mart dataset."""
    registry = load_registry()
    for cube, entry in (registry.get("cubes") or {}).items():
        if entry.get("dataset") == dataset:
            result = dict(entry)
            result["cube"] = cube
            result["registry_version"] = registry.get("version", 0)
            return result
    return {"dataset": dataset, "cube": None, "registry_version": registry.get("version", 0)}
