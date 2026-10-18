"""Validate the Jiangsu semantic registry against project sources."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_semantic_artifacts import _load_catalog

ROOT = Path(__file__).resolve().parents[4]
REGISTRY = Path(__file__).resolve().with_name("registry.yaml")
SCHEMA_DIR = ROOT / "projects/jiangsu-ops/data-ops/cube/schema"
DATASET_DIR = ROOT / "projects/jiangsu-ops/data-ops/sync/datasets"


def main() -> int:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    cubes = data.get("cubes") or {}
    schema_text = "\n".join(p.read_text(encoding="utf-8") for p in SCHEMA_DIR.glob("*.js"))
    schema_cubes = set(re.findall(r"cube\(`([^`]+)`", schema_text))
    # CATALOG 提取复用生成器的 AST 路径(正则提取在格式变化时会静默得到空集,
    # 让"CATALOG cubes missing from registry"检查退化为永远通过 — 禁止)
    try:
        catalog = _load_catalog()
    except (RuntimeError, SyntaxError, ValueError) as exc:
        print("SEMANTIC_REGISTRY_INVALID")
        print(f"- CATALOG extraction from tool.py failed: {exc}")
        return 1
    catalog_cubes = set(catalog)
    errors: list[str] = []
    missing_registry = sorted(catalog_cubes - set(cubes))
    if missing_registry:
        errors.append("CATALOG cubes missing from registry: " + ", ".join(missing_registry))
    for cube, spec in cubes.items():
        if cube not in schema_cubes:
            errors.append(f"{cube}: missing Cube schema")
        if cube not in catalog_cubes:
            errors.append(f"{cube}: missing from tool.py CATALOG")
        catalog_members = {
            item.get("name") for item in (catalog.get(cube) or {}).get("measures", [])
        }
        dataset = spec.get("dataset")
        if dataset and not (DATASET_DIR / f"{dataset}.yaml").exists():
            errors.append(f"{cube}: missing dataset contract {dataset}")
        for measure, metric in (spec.get("measures") or {}).items():
            if measure not in catalog_members:
                errors.append(
                    f"{cube}.{measure}: not a CATALOG measure member "
                    "(typo would be silently dropped by the generator)"
                )
            if not metric.get("name") or not metric.get("definition"):
                errors.append(f"{cube}.{measure}: name and definition are required")
            if "rate" in measure.lower() and not metric.get("denominator"):
                errors.append(f"{cube}.{measure}: rate metric requires denominator")
    if errors:
        print("SEMANTIC_REGISTRY_INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"SEMANTIC_REGISTRY_OK cubes={len(cubes)} version={data.get('version')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
