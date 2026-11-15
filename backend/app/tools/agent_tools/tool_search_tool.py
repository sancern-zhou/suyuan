"""tool_search：deferred tools 机制的检索入口（运行时动态注入）。

模式 opt-in 后（tool_registry.resolve_deferred_tool_config），非 always_on
工具以薄存根常驻（tool_adapter.apply_deferred_tool_stubs），模型经本工具
按需取回完整参数契约。机制对照 ZCode tool_search/deferred_tools 与江西
api_catalog 三件套（project/jiangxi-noise）：目录常驻、契约按需。

设计要点：
- 运行时按模式构造一次并注入 executor.tool_registry（submit_result 同款
  动态注入路径），mode 烘焙进实例、不进全局注册表——非 opt-in 模式零泄漏。
- 命中只回 schema（契约已在工具结果里可见），不触发升级；模型实际调用
  该工具时由 agent_runtime 记入 RunState.discovered_tools，下一轮换回
  全 schema 常驻，避免"契约双份占上下文"。
- 检索范围限定本模式存根化候选集（含项目接管/追加后的有效白名单），
  always_on 与永不存根工具已全 schema 可见，无需检索。
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List

from app.tools.base.tool_interface import ToolCategory

_MAX_RESULTS_HARD_CAP = 10


def _rank_tool_names(query: str, candidates: Dict[str, Dict[str, Any]]) -> List[str]:
    """词元打分（参考江西 api_catalog.score_apis）+ 名称近似兜底（difflib）。"""
    tokens = [token for token in re.split(r"\s+", query.strip().lower()) if token]
    scored: List[tuple[int, str]] = []
    for name, schema in candidates.items():
        description = (schema.get("description") or "").lower()
        lowered_name = name.lower()
        haystack = f"{lowered_name} {description}"
        score = 0
        for token in tokens:
            if token == lowered_name:
                score += 10
            elif token in lowered_name:
                score += 6
            elif token in haystack:
                score += 2
        if score > 0:
            scored.append((score, name))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [name for _, name in scored]
    # 词元无命中时按名称近似匹配兜底（拼写偏差/缩写，仓库先例
    # workflow/target_mode_contract.py 的 get_close_matches 用法）。
    return difflib.get_close_matches(query.strip(), list(candidates), n=_MAX_RESULTS_HARD_CAP, cutoff=0.4)


class ToolSearchTool:
    """每个 opt-in 运行动态构造一次：持有运行模式并检索其存根化工具。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.name = "tool_search"
        self.description = (
            "检索本模式下参数契约未常驻（存根化）的工具并返回完整参数定义。"
            "当某工具的说明带有「参数契约未常驻」提示时，先调用本工具查询该工具名，"
            "获取字段/类型/枚举/必填/示例后再按契约调用。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.0.0"
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "工具名或功能关键词（空格分隔），例如：execute_sql_query 或 站点 排名",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "description": "最多返回条数(1-10)",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        }

    def __call__(self, *args: Any, **kwargs: Any):
        # executor 直接以 await tool_func(...) 调用注册表里的值（submit_result 同款）。
        return self.execute(*args, **kwargs)

    def _deferred_candidates(self) -> Dict[str, Dict[str, Any]]:
        """本模式存根化候选的 {name: 完整 schema}（含该模式的 schema 适配）。"""
        from app.agent.prompts.tool_registry import (
            compute_deferred_tool_names,
            resolve_deferred_tool_config,
        )
        from app.agent.tool_adapter import get_tool_schemas

        config = resolve_deferred_tool_config(self.mode)
        if config is None:
            return {}
        deferred = compute_deferred_tool_names(self.mode, config)
        if not deferred:
            return {}
        schemas = get_tool_schemas(mode=self.mode)
        return {schema["name"]: schema for schema in schemas if schema["name"] in deferred}

    async def execute(
        self,
        query: Any = None,
        max_results: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return {
                "success": False,
                "error": "invalid_query",
                "summary": "query 不能为空：传工具名或功能关键词",
            }
        try:
            limit = 5 if max_results is None else int(max_results)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(_MAX_RESULTS_HARD_CAP, limit))

        candidates = self._deferred_candidates()
        if not candidates:
            return {
                "success": False,
                "error": "deferred_tools_unavailable",
                "summary": "当前模式没有启用工具检索目录（无存根化工具）",
            }
        ranked = _rank_tool_names(query, candidates)
        matched = ranked[:limit]
        if not matched:
            return {
                "success": True,
                "data": {
                    "tools": [],
                    "deferred_catalog": sorted(candidates),
                    "hint": "没有命中；目录列出全部可检索工具名，可换准确名称重试",
                },
                "count": 0,
                "summary": f"未命中（可检索工具共 {len(candidates)} 个）",
            }
        return {
            "success": True,
            "data": {
                "tools": [{"name": name, "schema": candidates[name]} for name in matched],
                "deferred_catalog": sorted(candidates),
                "hint": "按返回的 schema 调用对应工具；参数契约以本结果为准（存根提示可忽略）",
            },
            "count": len(matched),
            "summary": f"命中 {len(matched)} 个工具：{'、'.join(matched)}",
        }

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema
