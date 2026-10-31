# -*- coding: utf-8 -*-
"""Generate the backend-facing semantic catalog artifact (catalog.generated.json).

单一来源约定（2026-10-31 起取代"四方手工同步"中的 backend CATALOG 一环）：
  - 查询成员（measures/dimensions）唯一来自 cube/schema/*.js —— Cube 执行真相，
    成员不进 schema 查询必失败，因此成员清单必须镜像 schema；
  - 业务语义（name/definition/numerator/denominator/null_policy/time_basis/
    limitations）唯一来自 registry.yaml（人工精选维护，允许只登记关键指标）；
  - 本脚本把两者 join 成 catalog.generated.json 写入 backend 工具目录，
    guangdong_query_metrics 运行时 fail-closed 加载（缺失/损坏拒绝启动）。

合并规则：
  - 成员集 = schema 成员集（registry 多出的成员视为 typo，validate_registry 拦截）；
  - registry 已登记的 measure：registry 字段全量并入，title 取 schema title；
  - 未登记的 measure：name/definition 回退为 schema title（与旧 CATALOG 兜底一致）。

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/semantic/gen_semantic_artifacts.py            # 生成并写入
  PYTHONPATH=backend python projects/guangdong/data-ops/semantic/gen_semantic_artifacts.py --check    # 漂移检测（dq_check 每日调用）

退出码: --check 不一致时返回 1。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from app.utils.path_config import resolve_agent_path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry.yaml"
SCHEMA_DIR = HERE.parent / "cube" / "schema"
TARGET = resolve_agent_path(
    "backend/app/tools/query/guangdong_cube_metrics/catalog.generated.json"
)

sys.path.insert(0, str(HERE))
from cube_schema import parse_schema_dir  # noqa: E402


def build() -> dict[str, Any]:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    registered = registry.get("cubes") or {}
    schema = parse_schema_dir(SCHEMA_DIR)
    cubes: dict[str, Any] = {}
    for cube in sorted(schema):
        members = schema[cube]
        semantic = registered.get(cube) or {}
        registry_measures = semantic.get("measures") or {}
        measures: dict[str, Any] = {}
        for name, spec in members["measures"].items():
            entry: dict[str, Any] = {"title": spec.get("title") or name}
            registered_spec = dict(registry_measures.get(name) or {})
            if registered_spec:
                entry.update(registered_spec)
            else:
                entry["name"] = entry["title"]
                entry["definition"] = entry["title"]
            measures[name] = entry
        dimensions = {
            name: {"title": spec.get("title") or name}
            for name, spec in members["dimensions"].items()
        }
        cubes[cube] = {
            "dataset": semantic.get("dataset"),
            "grain": semantic.get("grain"),
            "applicability": semantic.get("applicability"),
            "source_window": semantic.get("source_window"),
            "freshness_slo": semantic.get("freshness_slo"),
            "limitations": semantic.get("limitations", []),
            "measures": measures,
            "dimensions": dimensions,
        }
    return {
        "version": registry.get("version", 0),
        "project": registry.get("project", "guangdong"),
        "generated_from": ["cube/schema/*.js", "semantic/registry.yaml"],
        "cubes": cubes,
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print(f"SEMANTIC_ARTIFACT_DRIFT: regenerate {TARGET}")
            return 1
        print("SEMANTIC_ARTIFACT_OK")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print(f"written: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
