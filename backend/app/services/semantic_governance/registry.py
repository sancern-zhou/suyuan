# -*- coding: utf-8 -*-
"""业务语义注册中心（registry.yaml）加载与元数据组装，fail-open。

registry 是人工精选维护的业务语义源（允许只登记关键指标）；产物类消费走
catalog_store（fail-closed），本模块面向"需要解释元数据但允许语义缺失"的
场景（如 SQL 证据侧的 dataset_metadata）。文件缺失/损坏时返回空注册中心并
告警，不得把已成功的查询变成失败。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Union

import structlog
import yaml

logger = structlog.get_logger()

_EMPTY_REGISTRY = {"version": 0, "project": "", "cubes": {}}


@lru_cache(maxsize=8)
def _load_cached(path_str: str, mtime_ns: int, log_event: str) -> dict:
    path = Path(path_str)
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(log_event, path=str(path), error=str(exc))
        return dict(_EMPTY_REGISTRY)
    if not isinstance(value.get("cubes"), dict):
        value["cubes"] = {}
    return value


def load_registry(path: Union[str, Path], *, log_event: str = "semantic_registry_unavailable") -> dict:
    """加载注册中心；fail-open（缺失/损坏 → 空 registry + 告警日志）。"""
    resolved = Path(path)
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        logger.warning(log_event, path=str(resolved), error="registry file missing")
        return dict(_EMPTY_REGISTRY)
    return _load_cached(str(resolved), mtime, log_event)


def cube_metadata(registry: dict, cube: str, catalog: dict) -> dict:
    """解释元数据：registry 条目优先，产物成员 title 兜底。

    catalog 为 catalog_store.load_catalog 的产物（cubes.<cube>.measures 为
    {成员名: {title, name?, definition?, ...}} 字典形态）。registry 未登记的
    成员用产物 title 顶 name/definition，保证 describe 输出可读。
    """
    entry = dict((registry.get("cubes") or {}).get(cube) or {})
    measures = entry.get("measures") if isinstance(entry.get("measures"), dict) else {}
    for name, spec in ((catalog.get("cubes") or {}).get(cube, {}).get("measures") or {}).items():
        if name not in measures:
            title = (spec or {}).get("title") or name
            measures[name] = {"name": title, "definition": title}
    entry["measures"] = {name: dict(spec) for name, spec in measures.items()}
    entry["registry_version"] = registry.get("version", 0)
    return entry


def dataset_metadata(registry: dict, dataset: str) -> dict:
    """宽表 dataset 级解释元数据（SQL 证据侧使用）。"""
    version = registry.get("version", 0)
    for cube, spec in (registry.get("cubes") or {}).items():
        if spec.get("dataset") == dataset:
            return {
                "cube": cube,
                "dataset": dataset,
                "grain": spec.get("grain"),
                "applicability": spec.get("applicability"),
                "source_window": spec.get("source_window"),
                "freshness_slo": spec.get("freshness_slo"),
                "limitations": spec.get("limitations", []),
                "registry_version": version,
            }
    return {"dataset": dataset, "registry_version": version}
