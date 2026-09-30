"""领域专家子模式（expert_meteorology / expert_analysis）：工具、提示词与契约守卫。"""

import pytest

from app.agent.prompts.expert_prompt import (
    build_expert_analysis_prompt,
    build_expert_meteorology_prompt,
    build_expert_prompt,
)
from app.agent.prompts.tool_registry import (
    AGENT_HIDDEN_TOOL_NAMES,
    get_tools_by_mode,
)
from app.agent.workflow.profiles import get_agent_profile
from app.agent.workflow.target_mode_contract import (
    build_target_mode_contract,
    target_mode_values,
)


# ----------------------------------------
# 工具注册表与 profile
# ----------------------------------------


def test_domain_expert_tool_whitelists_are_disjoint_and_lean():
    from app.agent.prompts.tool_registry import (
        EXPERT_ANALYSIS_TOOL_NAMES,
        EXPERT_METEOROLOGY_TOOL_NAMES,
    )

    meteorology_names = set(EXPERT_METEOROLOGY_TOOL_NAMES)
    analysis_names = set(EXPERT_ANALYSIS_TOOL_NAMES)

    assert "get_observed_meteorology" in meteorology_names
    assert "meteorological_trajectory_analysis" in meteorology_names
    assert "get_vocs_data" not in meteorology_names

    monitoring_only = {
        "query_xcai_city_history",
        "query_national_city_air_quality",
        "create_business_chart",
    }
    weather_only = {
        "get_observed_meteorology",
        "get_weather_forecast",
        "get_current_weather",
        "get_platform_weather_image",
        "meteorological_trajectory_analysis",
        "resolve_station_geo",
    }
    assert meteorology_names.isdisjoint(monitoring_only)
    assert analysis_names.isdisjoint(weather_only)

    assert "query_xcai_city_history" in analysis_names
    assert "create_business_chart" in analysis_names

    for mode in ("expert_meteorology", "expert_analysis"):
        tools = get_tools_by_mode(mode)
        assert tools
        assert len(tools) <= 14
        assert AGENT_HIDDEN_TOOL_NAMES.isdisjoint(tools)
        assert {"run_agent_workflow", "call_sub_agent", "ask_user_question"}.isdisjoint(tools)


def test_domain_expert_profiles_disallow_delegation():
    for mode in ("expert_meteorology", "expert_analysis"):
        profile = get_agent_profile(mode)
        assert profile.allow_delegation is False


# ----------------------------------------
# 提示词变体
# ----------------------------------------


def test_meteorology_prompt_scope_and_efficiency_rules():
    prompt = build_expert_meteorology_prompt(list(get_tools_by_mode("expert_meteorology")))
    assert "气象分析专家" in prompt
    assert "禁止直接断言浓度数值成因" in prompt
    assert "约 15 轮内完成" in prompt
    assert "一个 `execute_python` 脚本完成整段读取、清洗、统计、绘图管线" in prompt
    assert "禁止重新查询" in prompt


def test_analysis_prompt_defers_to_upstream_meteorology():
    prompt = build_expert_analysis_prompt(list(get_tools_by_mode("expert_analysis")))
    assert "环境监测数据分析专家" in prompt
    assert "上游气象节点结论" in prompt
    assert "data_gaps" in prompt
    assert "meteorological_trajectory_analysis" not in prompt


def test_general_expert_prompt_keeps_full_scope_and_gains_efficiency_rules():
    prompt = build_expert_prompt(list(get_tools_by_mode("expert")))
    assert "大气环境专业分析专家" in prompt
    assert "常见机制检查" in prompt
    assert "约 15 轮内完成" in prompt


# ----------------------------------------
# 契约注册
# ----------------------------------------


def test_contract_registers_domain_expert_modes():
    values = target_mode_values()
    assert "expert_meteorology" in values
    assert "expert_analysis" in values
    contract = build_target_mode_contract()
    assert "气象专家 Agent" in contract
    assert "常规分析专家 Agent" in contract
    assert "expert_meteorology" in contract
