"""Generate the AI-maintenance semantic index from registry and Cube catalog.

The registry remains the curated source for business meaning.  The Python
catalog remains the query member source.  This generated index joins both so
reviewers and coding agents can inspect one deterministic artifact and detect
drift without hand-copying descriptions.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[4]
TARGET = Path(__file__).resolve().with_name("catalog.generated.yaml")
REGISTRY = Path(__file__).resolve().with_name("registry.yaml")

TOOL_PATH = ROOT / "backend/app/tools/query/jiangsu_cube_metrics/tool.py"


HEADER = "# GENERATED FILE - run gen_semantic_artifacts.py; do not edit by hand\n"


def build() -> dict[str, Any]:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    registered = registry.get("cubes") or {}
    catalog = _load_catalog()
    cubes: dict[str, Any] = {}
    for cube in sorted(catalog):
        cube_catalog = catalog[cube]
        semantic = registered.get(cube) or {}
        measures = {}
        for item in cube_catalog.get("measures", []):
            name = item["name"]
            definition = dict(semantic.get("measures", {}).get(name) or {})
            definition.setdefault("name", item.get("title", name))
            definition.setdefault("definition", item.get("title", name))
            measures[name] = definition
        cubes[cube] = {
            "dataset": semantic.get("dataset"),
            "grain": semantic.get("grain"),
            "applicability": semantic.get("applicability"),
            "source_window": semantic.get("source_window"),
            "freshness_slo": semantic.get("freshness_slo"),
            "limitations": semantic.get("limitations", []),
            "measures": measures,
            "dimensions": {item["name"]: item.get("title", item["name"])
                           for item in cube_catalog.get("dimensions", [])},
        }
    return {
        "version": registry.get("version", 0),
        "project": registry.get("project", "jiangsu-ops"),
        "generated_from": ["semantic/registry.yaml", "cube_metrics/tool.py"],
        "cubes": cubes,
    }


def _load_catalog() -> dict[str, Any]:
    """Read the literal CATALOG without importing the application registry."""
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"), filename=str(TOOL_PATH))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "CATALOG":
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                return value
    raise RuntimeError(f"CATALOG assignment not found in {TOOL_PATH}")


def render() -> str:
    return HEADER + yaml.safe_dump(build(), allow_unicode=True, sort_keys=False)


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print(f"SEMANTIC_ARTIFACT_DRIFT: regenerate {TARGET}")
            return 1
        print(f"SEMANTIC_ARTIFACT_OK cubes={len(build()['cubes'])}")
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"written: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
