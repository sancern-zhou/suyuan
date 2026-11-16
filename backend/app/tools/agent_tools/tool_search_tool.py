"""tool_search：deferred tools 机制的检索入口（运行时动态注入）。

模式 opt-in 后（tool_registry.resolve_deferred_tool_config），非 always_on
工具以薄存根常驻（tool_adapter.apply_deferred_tool_stubs），模型经本工具
按需取回完整参数契约。机制对照 ZCode tool_search/deferred_tools 与江西
api_catalog 三件套（project/jiangxi-noise）：目录常驻、契约按需。

检索算法自 ZCode（apps/zcode-cli/packages/core/src/tool/search/search.ts）
移植：词元切分（camelCase/snake）、``+词`` 必含语法、``select:a,b`` 精确
批量、按名/描述打分；未采纳 MCP 拆名/别名/searchHint（本仓库无此概念）。
结果体积守门对照 ZCode resultBudget 先例：超限自动截断并提示分批检索。

设计要点：
- 运行时按模式构造一次并注入 executor.tool_registry（submit_result 同款
  动态注入路径），mode 烘焙进实例、不进全局注册表——非 opt-in 模式零泄漏。
- 命中只回 schema（契约已在工具结果里可见），不触发升级；模型实际调用
  该工具时由 agent_runtime 记入 RunState.discovered_tools 并经会话历史
  派生跨轮次持久（collect_called_deferred_tools），下一轮换回全 schema
  常驻，避免"契约双份占上下文"。
- 检索范围限定本模式存根化候选集（含项目接管/追加后的有效白名单），
  always_on 与永不存根工具已全 schema 可见，无需检索。
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Dict, List, Tuple

from app.tools.base.tool_interface import ToolCategory

_MAX_RESULTS_HARD_CAP = 10

# 结果体积守门（ZCode resultBudget 先例）：命中按打分顺序累计 schema 字符，
# 超限截断并提示分批检索。取 observation 预算（48K）一半，为其余字段留量。
MAX_SEARCH_RESULT_CHARS = 24_000

_CAMEL_SPLIT_RE = re.compile(r"([a-z])([A-Z])")

_NO_MATCH_MESSAGE = (
    "没有命中的存根化工具。已常驻/已升级的工具不参与检索、无需加载。"
    "请检查拼写、换准确工具名或更宽泛的关键词后再下'工具不存在'的结论。"
)


def _tokenize_tool_name(name: str) -> List[str]:
    """工具名切词：camelCase 断开 + snake/点/空白切分（ZCode tokenize 非 MCP 路径）。"""
    spaced = _CAMEL_SPLIT_RE.sub(r"\1 \2", name).replace("_", " ").replace(".", " ")
    return [part for part in spaced.lower().split() if part]


def _term_pattern(term: str) -> re.Pattern:
    """描述匹配模式：ASCII 词用 \\b 词边界（ZCode 原版）；CJK 词退化为包含
    匹配——Python 正则把汉字当 \\w，\\b 在中文串内永不成立，原版语义对
    中文描述会整体失效。"""
    if term.isascii():
        return re.compile(rf"\b{re.escape(term)}\b")
    return re.compile(re.escape(term))


def search_deferred_tools(
    query: str,
    candidates: Dict[str, Dict[str, Any]],
    max_results: int = _MAX_RESULTS_HARD_CAP,
) -> List[str]:
    """在存根化候选集内检索工具名（ZCode searchTools 的 Python 移植）。

    支持三种查询形态：
    - ``select:name1,name2``：精确名批量（部分命中部分忽略）；
    - 精确名整串：直接返回；
    - 关键词：``+词`` 为必含条件（不命中即排除），其余按打分排序
      （名字词元全等 +10 / 词元包含 +5 / 整名包含 +3 / 描述词边界 +2）。
    """
    select = re.match(r"^select:(.+)$", query.strip(), re.IGNORECASE)
    if select:
        resolved = []
        for value in select.group(1).split(","):
            name = value.strip()
            if name and name in candidates and name not in resolved:
                resolved.append(name)
        return resolved

    text = query.strip().lower()
    if not text:
        return []
    if text in candidates:
        return [text]

    terms = [term for term in text.split() if term]
    required = [term[1:] for term in terms if term.startswith("+") and len(term) > 1]
    keywords = required + [term for term in terms if not (term.startswith("+") and len(term) > 1)]
    patterns = {term: _term_pattern(term) for term in keywords}

    scored: List[Tuple[int, str]] = []
    for name, schema in candidates.items():
        parts = _tokenize_tool_name(name)
        full = " ".join(parts)
        description = (schema.get("description") or "").lower()
        if not all(
            any(term in part for part in parts) or patterns[term].search(description)
            for term in required
        ):
            continue
        score = 0
        for term in keywords:
            if term in parts:
                score += 10
            elif any(term in part for part in parts):
                score += 5
            if term in full and score == 0:
                score += 3
            if patterns[term].search(description):
                score += 2
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:max_results]]


def rank_with_fallback(query: str, candidates: Dict[str, Dict[str, Any]]) -> List[str]:
    """词元检索 + 名称近似兜底（拼写偏差，difflib 先例 target_mode_contract）。"""
    ranked = search_deferred_tools(query, candidates)
    if ranked:
        return ranked
    return difflib.get_close_matches(
        query.strip(), list(candidates), n=_MAX_RESULTS_HARD_CAP, cutoff=0.4
    )


class ToolSearchTool:
    """每个 opt-in 运行动态构造一次：持有运行模式并检索其存根化工具。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.name = "tool_search"
        self.description = (
            "检索本模式下参数契约未常驻（存根化）的工具并返回完整参数定义。"
            "当某工具的说明带有「参数契约未常驻」提示时，先调用本工具查询该工具名，"
            "获取字段/类型/枚举/必填/示例后再按契约调用。"
            "支持：工具名或关键词（空格分隔）；``+词`` 必含；``select:工具1,工具2`` 精确批量。"
        )
        self.category = ToolCategory.PLANNING
        self.requires_context = False
        self.version = "1.1.0"
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "工具名或功能关键词；+词=必含；select:a,b=精确批量",
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

    @staticmethod
    def _budgeted_matches(
        ranked: List[str],
        candidates: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[str], bool]:
        """按打分顺序累计 schema 字符，超 MAX_SEARCH_RESULT_CHARS 截断。

        单条超限仍返回第一条（工具 schema 本身受预算测试 10K 上限守门），
        多条累计超限即止并标记 truncated。
        """
        selected: List[str] = []
        total = 0
        for name in ranked:
            size = len(json.dumps(candidates[name], ensure_ascii=False))
            if selected and total + size > MAX_SEARCH_RESULT_CHARS:
                return selected, True
            selected.append(name)
            total += size
        return selected, False

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
                "summary": "query 不能为空：传工具名、功能关键词、+必含词或 select:a,b",
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
        ranked = rank_with_fallback(query, candidates)
        matched, truncated = self._budgeted_matches(ranked[:limit], candidates)
        if not matched:
            return {
                "success": True,
                "data": {
                    "tools": [],
                    "deferred_catalog": sorted(candidates),
                    "hint": _NO_MATCH_MESSAGE,
                },
                "count": 0,
                "summary": f"未命中（可检索工具共 {len(candidates)} 个）",
            }
        data_hint = "按返回的 schema 调用对应工具；参数契约以本结果为准（存根提示可忽略）"
        if truncated:
            data_hint += (
                f"；命中条数因单次结果体积上限（{MAX_SEARCH_RESULT_CHARS} 字符）截断，"
                "需要其余结果请用 select: 按名分批检索"
            )
        return {
            "success": True,
            "data": {
                "tools": [{"name": name, "schema": candidates[name]} for name in matched],
                "deferred_catalog": sorted(candidates),
                "hint": data_hint,
            },
            "count": len(matched),
            "summary": f"命中 {len(matched)} 个工具：{'、'.join(matched)}",
        }

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema
