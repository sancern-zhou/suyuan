"""Validate Xuchang semantic registry, Cube schemas, and Python catalog."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = Path(__file__).resolve().with_name("registry.yaml")
SCHEMA_DIR = ROOT / "projects/xuchang/data-ops/cube/schema"
TOOL_PATH = ROOT / "backend/app/tools/query/xuchang_cube_metrics/tool.py"


def catalog() -> dict:
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "CATALOG":
            return ast.literal_eval(node.value)
    raise RuntimeError("CATALOG assignment not found")


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    registered = registry.get("cubes") or {}
    current_catalog = catalog()
    schema_text = "\n".join(p.read_text(encoding="utf-8") for p in SCHEMA_DIR.glob("*.js"))
    schema_cubes = set(re.findall(r"cube\(`([^`]+)`", schema_text))
    errors = []
    if set(current_catalog) != schema_cubes:
        errors.append(f"CATALOG/schema mismatch: catalog_only={sorted(set(current_catalog)-schema_cubes)}, schema_only={sorted(schema_cubes-set(current_catalog))}")
    missing = sorted(set(current_catalog) - set(registered))
    if missing:
        errors.append("CATALOG cubes missing from registry: " + ", ".join(missing))
    for cube, spec in registered.items():
        for field in ("dataset", "grain", "applicability", "source_window"):
            if not spec.get(field):
                errors.append(f"{cube}: missing {field}")
        if cube not in schema_cubes:
            errors.append(f"{cube}: missing Cube schema")
    if errors:
        print("XUCHANG_SEMANTIC_REGISTRY_INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"XUCHANG_SEMANTIC_REGISTRY_OK cubes={len(registered)} version={registry.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
