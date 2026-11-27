"""Validate Xuchang semantic registry against schemas and the generated catalog."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from gen_semantic_artifacts import parse_schemas

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = Path(__file__).resolve().with_name("registry.yaml")
ARTIFACT = ROOT / "backend/app/tools/query/xuchang_cube_metrics/catalog.generated.json"


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    registered = registry.get("cubes") or {}
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))["cubes"]
    schema_cubes = parse_schemas()

    errors = []
    if set(artifact) != set(schema_cubes):
        errors.append(
            f"artifact/schema mismatch: artifact_only={sorted(set(artifact) - set(schema_cubes))}, "
            f"schema_only={sorted(set(schema_cubes) - set(artifact))}; 重跑 gen_semantic_artifacts.py"
        )
    if set(artifact) != set(registered):
        errors.append("registry/artifact cube mismatch: " + ", ".join(sorted(set(artifact) ^ set(registered))))
    for cube, spec in registered.items():
        for field in ("dataset", "grain", "applicability", "source_window"):
            if not spec.get(field):
                errors.append(f"{cube}: missing {field}")
        artifact_measures = {m["name"] for m in artifact.get(cube, {}).get("measures", [])}
        stale = sorted(set(spec.get("measures") or {}) - artifact_measures)
        if stale:
            errors.append(f"{cube}: registry 成员不在 schema 中: {stale}")
    if errors:
        print("XUCHANG_SEMANTIC_REGISTRY_INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"XUCHANG_SEMANTIC_REGISTRY_OK cubes={len(registered)} version={registry.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
