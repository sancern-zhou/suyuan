"""Generate a deterministic Xuchang semantic index for AI maintenance."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
TOOL_PATH = ROOT / "backend/app/tools/query/xuchang_cube_metrics/tool.py"
REGISTRY = Path(__file__).resolve().with_name("registry.yaml")
TARGET = Path(__file__).resolve().with_name("catalog.generated.yaml")


def _catalog():
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "CATALOG":
            return ast.literal_eval(node.value)
    raise RuntimeError("CATALOG assignment not found")


def build():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    entries = registry.get("cubes") or {}
    result = {}
    for cube, parts in sorted(_catalog().items()):
        semantic = entries.get(cube) or {}
        measures = {}
        for item in parts.get("measures", []):
            name = item["name"]
            measures[name] = dict((semantic.get("measures") or {}).get(name) or {
                "name": item.get("title", name), "definition": item.get("title", name)
            })
        result[cube] = {
            "dataset": semantic.get("dataset"),
            "grain": semantic.get("grain"),
            "applicability": semantic.get("applicability"),
            "source_window": semantic.get("source_window"),
            "limitations": semantic.get("limitations", []),
            "measures": measures,
            "dimensions": {i["name"]: i.get("title", i["name"]) for i in parts.get("dimensions", [])},
        }
    return {"version": registry.get("version", 0), "project": "xuchang", "generated_from": ["semantic/registry.yaml", "xuchang_cube_metrics/tool.py"], "cubes": result}


def main() -> int:
    content = "# GENERATED FILE - run gen_semantic_artifacts.py; do not edit by hand\n" + yaml.safe_dump(build(), allow_unicode=True, sort_keys=False)
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print("XUCHANG_SEMANTIC_ARTIFACT_DRIFT")
            return 1
        print(f"XUCHANG_SEMANTIC_ARTIFACT_OK cubes={len(build()['cubes'])}")
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"written: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
