"""Structured business metadata for the Xuchang Cube metrics tool."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.utils.path_config import resolve_agent_path

REGISTRY_PATH = resolve_agent_path("projects/xuchang/data-ops/semantic/registry.yaml")


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(REGISTRY_PATH).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"version": 0, "project": "xuchang", "cubes": {}}
    if not isinstance(value.get("cubes"), dict):
        value["cubes"] = {}
    return value


def cube_metadata(cube: str, catalog: dict[str, Any]) -> dict[str, Any]:
    registry = load_registry()
    entry = dict(registry.get("cubes", {}).get(cube) or {})
    measures = {k: dict(v) for k, v in (entry.get("measures") or {}).items()}
    for item in catalog.get(cube, {}).get("measures", []):
        name = item.get("name")
        if name and name not in measures:
            measures[name] = {"name": item.get("title", name), "definition": item.get("title", name)}
    entry["measures"] = measures
    entry["registry_version"] = registry.get("version", 0)
    return entry
