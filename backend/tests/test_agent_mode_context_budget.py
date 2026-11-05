"""模式上下文预算守门：防止工具 schema / 系统提示词回归式膨胀。

背景（2026-10-31 上下文瘦身）：execute_guangdong_mart_sql 曾把 42+156 张表的
字段契约整体注入工具描述（单工具 ~20K 字符），run_agent_workflow 曾把编排手册
与 target_mode 契约双份内联（单工具 ~20K），call_sub_agent 曾注入全量四段
子模式契约（~9K）。此类膨胀是静默发生的——每次请求都计费，只有测量可见。

本文件三层防线：
1. estimate_token_count 公式正确性（CJK 感知，替代失真的 len/1.5）；
2. 已知历史膨胀点单工具上限（回归即红）；
3. 全模式扫描的通用上限（单工具 schema、模式工具总量、系统提示词）。

超限时的正确做法不是调大阈值，而是把内容按需化（describe_table / view_skill /
错误信息召回钩子）后缩减注入；三通道选型策略见 AGENTS.md
「上下文注入选型策略（工具描述 / skill / describe_table）」。
"""
import json
import math
from typing import Dict

import pytest

from app.agent.prompts.prompt_builder import (
    AgentMode,
    build_react_system_prompt,
    estimate_token_count,
)
from app.agent.tool_adapter import get_tool_schemas
from app.agent.prompts.tool_registry import get_tools_by_mode

import typing


# ---- 历史膨胀点上限（单位：字符；按 2026-10-31 瘦身后实测值 + 少量余量） ----
PER_TOOL_SCHEMA_CAPS: Dict[str, int] = {
    "execute_guangdong_mart_sql": 2_500,   # 实测 ~1.3K；契约走 describe_table
    "guangdong_query_metrics": 2_500,      # 实测 ~1.9K；语义目录走 describe_cube + 生成产物
    "run_agent_workflow": 11_000,          # 实测 ~9.6K；细则走 view_skill
    "call_sub_agent": 7_500,               # 实测 ~6.0K；子模式契约一行制
}

# ---- 全模式通用上限 ----
SINGLE_TOOL_SCHEMA_CAP = 10_000      # 当前最大 run_agent_workflow ~9.6K
MODE_TOOL_TOTAL_CAP = 65_000         # 当前最大 query ~62.7K
MODE_SYSTEM_PROMPT_CAP = 12_000      # 当前最大 report ~7.7K


def _all_modes():
    shared = [m for m in typing.get_args(AgentMode) if m != "custom"]
    modes = list(shared)
    try:
        from app.project_config import load_project_context
        from config.settings import settings

        project_modes = sorted(
            (load_project_context(settings.project_id).manifest.backend.agent_mode_tools or {}).keys()
        )
    except Exception:  # noqa: BLE001 — 无项目清单时只测共享模式
        project_modes = []
    return list(dict.fromkeys(modes + project_modes))


def test_estimate_token_count_cjk_aware():
    assert estimate_token_count("") == 0
    # 纯中文：每字 2 当量，3 当量 = 1 token
    assert estimate_token_count("一二三四五六") == 4
    # 纯 ASCII：1 字符 1 当量
    assert estimate_token_count("ab" * 3) == 2
    # 混合：20 中文 + 30 ASCII => ceil((40+30)/3) = 24
    mixed = "空气质量" * 5 + "a" * 30
    assert estimate_token_count(mixed) == math.ceil((20 * 2 + 30) / 3) == 24


@pytest.mark.parametrize("tool_name,cap", sorted(PER_TOOL_SCHEMA_CAPS.items()))
def test_known_bloat_prone_tools_stay_within_cap(tool_name, cap):
    """历史上膨胀过的工具单独盯防；判断依据见模块 docstring。"""
    violations = []
    seen = False
    for mode in _all_modes():
        try:
            tools = get_tools_by_mode(mode)
        except ValueError:
            continue
        if tool_name not in tools:
            continue
        for schema in get_tool_schemas(mode=mode):
            if schema.get("name") == tool_name:
                seen = True
                size = len(json.dumps(schema, ensure_ascii=False))
                if size > cap:
                    violations.append(f"{mode}: {size} > {cap}")
    if not seen:
        from config.settings import settings

        if settings.project_id == "guangdong":
            pytest.fail(
                f"{tool_name} 未在任何模式注册——确认工具是否改名，并同步更新 PER_TOOL_SCHEMA_CAPS"
            )
        pytest.skip(f"{tool_name} 未在当前部署（{settings.project_id}）注册")
    assert not violations, (
        f"{tool_name} schema 超限（历史膨胀回归）：{violations}。"
        "请按需化内容（describe_table/view_skill/错误召回）而不是调大阈值。"
    )


def test_all_mode_context_budgets():
    """全模式扫描：单工具 schema、模式工具总量、系统提示词三个上限。"""
    violations = []
    for mode in _all_modes():
        try:
            prompt = build_react_system_prompt(mode)
            schemas = get_tool_schemas(mode=mode)
        except ValueError:
            # 未在该部署注册的模式（如共享模式缺项目清单）跳过
            continue
        if len(prompt) > MODE_SYSTEM_PROMPT_CAP:
            violations.append(f"{mode}: system {len(prompt)} > {MODE_SYSTEM_PROMPT_CAP}")
        total = 0
        for schema in schemas:
            size = len(json.dumps(schema, ensure_ascii=False))
            total += size
            name = schema.get("name") or "?"
            if size > SINGLE_TOOL_SCHEMA_CAP:
                violations.append(f"{mode}/{name}: schema {size} > {SINGLE_TOOL_SCHEMA_CAP}")
        if total > MODE_TOOL_TOTAL_CAP:
            violations.append(f"{mode}: tools total {total} > {MODE_TOOL_TOTAL_CAP}")
    assert not violations, "上下文预算超限：\n" + "\n".join(violations)
