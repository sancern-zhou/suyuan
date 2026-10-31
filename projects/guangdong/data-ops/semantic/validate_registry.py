# -*- coding: utf-8 -*-
"""Validate the Guangdong semantic registry against project sources.

提交前语义校验（与 dq_check 的每日 gen --check 互补， dq_check 每日跑
gen_semantic_artifacts.py --check 做产物防漂移，本脚本做语义级校验）：

  1. registry cube 必须有 Cube schema —— 缺失会被生成器静默丢弃（硬错误）；
  2. registry measure 必须是 schema 成员 —— typo 会被生成器静默丢弃；
  3. measure 必须有 name+definition；率类指标必须有 denominator；
  4. registry dataset 必须有 sync/datasets 契约文件；
  5. catalog.generated.json 必须与当前 sources 的生成物逐字节一致
     （改了 schema/registry 忘了重新生成 → 此处拦截）。

成员真相 = cube/schema/*.js；业务语义真相 = registry.yaml；backend 不再持有
手工 CATALOG（2026-10-31 起，原"CATALOG 四方手工同步"一环已移除）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BACKEND = ROOT / "backend"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))

from cube_schema import SchemaParseError, parse_schema_dir  # noqa: E402
from gen_semantic_artifacts import TARGET, render  # noqa: E402

REGISTRY = HERE / "registry.yaml"
SCHEMA_DIR = ROOT / "projects/guangdong/data-ops/cube/schema"
DATASET_DIR = ROOT / "projects/guangdong/data-ops/sync/datasets"


def main() -> int:
    errors: list[str] = []
    try:
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        print("SEMANTIC_REGISTRY_INVALID")
        print(f"- registry.yaml unreadable: {exc}")
        return 1
    cubes = data.get("cubes") or {}

    try:
        schema = parse_schema_dir(SCHEMA_DIR)
    except SchemaParseError as exc:
        print("SEMANTIC_REGISTRY_INVALID")
        print(f"- cube schema parse failed (fail-closed): {exc}")
        return 1

    for cube, spec in cubes.items():
        if cube not in schema:
            errors.append(f"{cube}: no Cube schema (member would be silently dropped)")
            continue
        schema_measures = schema[cube]["measures"]
        dataset = spec.get("dataset")
        if dataset and not (DATASET_DIR / f"{dataset}.yaml").exists():
            errors.append(f"{cube}: missing dataset contract {dataset}")
        for measure, metric in (spec.get("measures") or {}).items():
            if measure not in schema_measures:
                errors.append(
                    f"{cube}.{measure}: not a schema measure member "
                    "(typo would be silently dropped by the generator)"
                )
            if not metric.get("name") or not metric.get("definition"):
                errors.append(f"{cube}.{measure}: name and definition are required")
            if "rate" in measure.lower() and not metric.get("denominator"):
                errors.append(f"{cube}.{measure}: rate metric requires denominator")

    try:
        deployed = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if deployed != render():
            errors.append(
                "catalog.generated.json drift: run gen_semantic_artifacts.py to regenerate"
            )
    except (OSError, ValueError) as exc:
        errors.append(f"artifact check failed: {exc}")

    if errors:
        print("SEMANTIC_REGISTRY_INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"SEMANTIC_REGISTRY_OK cubes={len(cubes)} schema_cubes={len(schema)} "
          f"version={data.get('version')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
