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
from app.tools.agent_tools.call_sub_agent import _resolve_child_max_iterations


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
    assert "create_business_chart" in meteorology_names

    for mode in ("expert_meteorology", "expert_analysis"):
        tools = get_tools_by_mode(mode)
        assert tools
        assert len(tools) <= 15
        assert AGENT_HIDDEN_TOOL_NAMES.isdisjoint(tools)
        assert {"run_agent_workflow", "call_sub_agent", "ask_user_question"}.isdisjoint(tools)
        assert {"write_file", "publish_session_file"}.issubset(tools)
        assert {"edit_file", "create_report_package"}.isdisjoint(tools)


def test_domain_expert_profiles_disallow_delegation():
    for mode in ("expert_meteorology", "expert_analysis"):
        profile = get_agent_profile(mode)
        assert profile.allow_delegation is False


def test_child_agents_have_no_memory_edit_tools():
    """子 Agent 不配置记忆编辑工具：中途写记忆每次烧一整轮，沉淀交给记忆整合器。"""
    from app.agent.workflow.capabilities import (
        MEMORY_EDIT_TOOL_NAMES,
        build_child_capability_policy,
    )

    for mode in ("expert_meteorology", "expert_analysis", "query", "expert"):
        policy = build_child_capability_policy(
            target_mode=mode,
            allowed_tools=list(get_tools_by_mode(mode)) + sorted(MEMORY_EDIT_TOOL_NAMES),
        )
        filtered = policy.filter_registry({name: object() for name in sorted(MEMORY_EDIT_TOOL_NAMES)})
        assert set(filtered) == set(), f"{mode} 子 Agent 不应持有记忆编辑工具: {sorted(filtered)}"
    assert "remember_fact" in policy.denied_tools

    # 记忆整合器本身不受限
    consolidator = build_child_capability_policy(
        target_mode="memory_consolidator",
        allowed_tools=["remember_fact"],
    )
    assert "remember_fact" not in consolidator.denied_tools


def test_domain_expert_iteration_defaults_are_bounded():
    # 计算密集型专家任务的默认轮数已放宽（分箱/相关性 15-20 轮收不完），
    # 工作流重试还会在此基础上按 50% 自动扩容（见 coordinator）。
    assert _resolve_child_max_iterations("expert_meteorology", None) == 20
    assert _resolve_child_max_iterations("expert_analysis", None) == 28
    assert _resolve_child_max_iterations("expert", None) == 40
    assert _resolve_child_max_iterations("expert_analysis", 12) == 12
    assert _resolve_child_max_iterations("expert_analysis", 999) == 120


# ----------------------------------------
# 提示词变体
# ----------------------------------------


def test_meteorology_prompt_scope_and_efficiency_rules():
    prompt = build_expert_meteorology_prompt(list(get_tools_by_mode("expert_meteorology")))
    assert "气象分析专家" in prompt
    assert "具体浓度成因由监测或组分专家综合确认" in prompt
    assert "约 15 轮内完成" in prompt
    assert "使用一个 `execute_python` 脚本完成整段读取、清洗、统计和绘图管线" in prompt
    assert "上游结果作为同源数据的首选依据" in prompt
    assert "Markdown 分析备忘录" in prompt
    assert "正式报告包与其他节点文件由主报告 Agent 统一维护" in prompt
    assert "已支持的专用业务图型统一使用 `create_business_chart`" in prompt
    assert "## 面向场景" in prompt
    assert "环境管理、监测研判、值班会商" in prompt
    assert "## 表达方式" in prompt
    assert "先结论后证据的金字塔结构" in prompt
    assert "status 根据结果完整度选择" in prompt


def test_analysis_prompt_defers_to_upstream_meteorology():
    prompt = build_expert_analysis_prompt(list(get_tools_by_mode("expert_analysis")))
    assert "常规空气质量监测数据分析专家" in prompt
    assert "六参数浓度、AQI、首要污染物" in prompt
    assert "上游气象节点结论" in prompt
    assert "data_gaps" in prompt
    assert "meteorological_trajectory_analysis" not in prompt
    assert "离子、碳组分、地壳元素和 VOCs/OFP 等组分分析由后续独立组分分析专家承担" in prompt
    assert "水溶性离子" not in prompt
    assert "VOCs/OFP 信号" not in prompt
    assert "业务影响和补证建议" in prompt
    assert "findings 中每条记录聚焦一个可独立引用的判断" in prompt
    assert "关键数值同时说明时间范围、空间范围、指标口径和单位" in prompt
    assert "判断依据、适用条件" in prompt
    assert "置信度" not in prompt
    for negative_marker in ("NEVER", "禁止", "不得", "不要", "不负责"):
        assert negative_marker not in prompt


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
