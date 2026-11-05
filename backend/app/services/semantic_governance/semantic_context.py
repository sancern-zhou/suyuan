# -*- coding: utf-8 -*-
"""semantic_context 规范形状组装器。

指标工具返回结果必须携带的解释元数据（粤苏两分支 execute 里手工拼装的
同一段 dict 的共享化）。按"最小充分结果结构"原则：可选键只在有值时出现。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .quality_policy import quality_guidance


def build_semantic_context(
    version: int,
    entry: Dict[str, Any],
    metric_definitions: Dict[str, Any],
    *,
    data_as_of: Optional[str] = None,
    include_data_as_of: bool = False,
    quality_status: Optional[str] = None,
    quality_checks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """由目录产物 cube 条目组装 semantic_context。

    version       产物/registry 版本号（registry_version 字段）
    entry         catalog_store.cube_entry 的产物条目
    metric_definitions 本次返回涉及的指标定义子集（或全量，按场景）
    include_data_as_of    metric_query 场景必开（契约要求键存在，允许 None 值）
    quality_status        提供时附 quality_guidance 决策边界
    quality_checks        提供时附最新一轮 DQ 明细
    """
    context: Dict[str, Any] = {
        "registry_version": version,
        "dataset": entry.get("dataset"),
        "grain": entry.get("grain"),
        "applicability": entry.get("applicability"),
        "source_window": entry.get("source_window"),
        "freshness_slo": entry.get("freshness_slo"),
        "limitations": entry.get("limitations", []),
        "metric_definitions": metric_definitions,
    }
    if include_data_as_of:
        context["data_as_of"] = data_as_of
    if quality_checks:
        context["quality_checks"] = quality_checks
    if quality_status is not None:
        context["quality_guidance"] = quality_guidance(quality_status)
    return context
