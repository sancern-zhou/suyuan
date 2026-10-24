"""Load the project semantic registry used to explain Cube results."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog
import yaml

from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger()

REGISTRY_PATH = resolve_agent_path(
    "projects/guangdong/data-ops/semantic/registry.yaml"
)


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    try:
        with REGISTRY_PATH.open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        # fail-open: 目录标题兜底, 但必须让部署侧看得见注册表不可用
        logger.warning("guangdong_semantic_registry_unavailable", error=str(exc))
        return {"version": 0, "project": "guangdong", "cubes": {}}
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
    """Dataset-level explanation for a mart table (SQL evidence side)."""
    for cube, spec in load_registry().get("cubes", {}).items():
        if spec.get("dataset") == dataset:
            return {
                "cube": cube,
                "dataset": dataset,
                "grain": spec.get("grain"),
                "applicability": spec.get("applicability"),
                "source_window": spec.get("source_window"),
                "freshness_slo": spec.get("freshness_slo"),
                "limitations": spec.get("limitations", []),
                "registry_version": load_registry().get("version", 0),
            }
    return {"dataset": dataset, "registry_version": load_registry().get("version", 0)}
