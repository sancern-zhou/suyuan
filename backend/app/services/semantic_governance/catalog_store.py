# -*- coding: utf-8 -*-
"""加载生成语义目录产物（catalog.generated.json），fail-closed。

产物由各项目 data-ops 的 gen_semantic_artifacts.py 生成（成员唯一源 =
cube/schema/*.js，业务语义源 = registry.yaml），是指标工具运行时的
成员白名单与语义来源。与 result_contract 的 fail-open 相反，这里缺失/
损坏必须抛 CatalogUnavailable：成员白名单治理不可降级——没有白名单就
没有口径约束，宁可工具不可用。

每次调用直读文件（不缓存）：产物是白名单治理数据，必须即时反映磁盘上的
最新生成物；25KB 级 JSON 解析耗时可忽略。registry/contract 之类的
fail-open 解释数据才做进程内缓存。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

import structlog

logger = structlog.get_logger()


class CatalogUnavailable(RuntimeError):
    """目录产物缺失/损坏/形态非法——调用方应让工具初始化失败。"""


def _validate_shape(catalog: Any, source: str) -> dict:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("cubes"), dict):
        raise CatalogUnavailable(f"{source}: catalog must be an object with a 'cubes' mapping")
    for cube, entry in catalog["cubes"].items():
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("measures"), dict)
                or not isinstance(entry.get("dimensions"), dict)):
            raise CatalogUnavailable(
                f"{source}: cube '{cube}' must carry measures/dimensions mappings")
    return catalog


def load_catalog(path: Union[str, Path]) -> dict:
    """加载并校验目录产物；缺失/损坏/形态非法抛 CatalogUnavailable。"""
    resolved = Path(path)
    try:
        catalog = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogUnavailable(f"{resolved}: semantic catalog unreadable ({exc})") from exc
    return _validate_shape(catalog, str(resolved))


def cube_names(catalog: dict) -> list[str]:
    """全部 cube 名（保持产物书写顺序）。"""
    return list(catalog.get("cubes", {}))


def cube_entry(catalog: dict, cube: str) -> Any:
    """单个 cube 的产物条目（dataset/grain/measures/dimensions/...），不存在返回 None。"""
    return catalog.get("cubes", {}).get(cube)


def has_member(catalog: dict, cube: str, kind: str, name: str) -> bool:
    """成员白名单判断；kind ∈ {'measures', 'dimensions'}。"""
    entry = cube_entry(catalog, cube)
    if not isinstance(entry, dict):
        return False
    return name in (entry.get(kind) or {})
