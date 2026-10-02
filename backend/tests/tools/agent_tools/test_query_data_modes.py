"""报告 DAG 问数子模式（query_monitoring / query_forecast）：工具、提示词与契约守卫。"""

from app.agent.prompts.query_data_prompt import (
    build_query_forecast_prompt,
    build_query_monitoring_prompt,
)
from app.agent.prompts.tool_registry import AGENT_HIDDEN_TOOL_NAMES, get_tools_by_mode
from app.agent.workflow.profiles import get_agent_profile
from app.agent.workflow.target_mode_contract import (
    build_target_mode_contract,
    target_mode_values,
)
from app.tools.agent_tools.call_sub_agent import _resolve_child_max_iterations


# ----------------------------------------
# 工具注册表
# ----------------------------------------


def test_query_submode_whitelists_are_lean_and_disjoint():
    from app.agent.prompts.tool_registry import (
        QUERY_FORECAST_TOOL_NAMES,
        QUERY_MONITORING_TOOL_NAMES,
    )

    monitoring = set(QUERY_MONITORING_TOOL_NAMES)
    forecast = set(QUERY_FORECAST_TOOL_NAMES)

    # 监测问数：监测取数在列，气象/预报工具不出现
    assert "execute_crawler_sql_query" in monitoring
    assert "query_xcai_city_history" in monitoring
    assert "xuchang_station_catalog" in monitoring
    assert not monitoring & {"get_weather_data", "get_weather_forecast", "get_current_weather"}

    # 预报问数：气象/预报取数在列，监测历史统计工具不出现
    assert "get_weather_forecast" in forecast
    assert "get_weather_data" in forecast
    assert "query_airdata_platform" in forecast
    assert not forecast & {"execute_crawler_sql_query", "query_xcai_city_history"}

    # 精简：均不超过 15 个工具（综合 query 为 20+）
    assert len(monitoring) <= 15
    assert len(forecast) <= 15

    # 与隐藏工具集互斥
    assert not monitoring & AGENT_HIDDEN_TOOL_NAMES
    assert not forecast & AGENT_HIDDEN_TOOL_NAMES


def test_query_submodes_resolve_via_get_tools_by_mode():
    for mode in ("query_monitoring", "query_forecast"):
        tools = get_tools_by_mode(mode)
        assert tools, mode
        assert "execute_python" in tools
        assert "call_sub_agent" not in tools


# ----------------------------------------
# profile 与契约注册
# ----------------------------------------


def test_query_submode_profiles_forbid_delegation():
    for mode in ("query_monitoring", "query_forecast"):
        profile = get_agent_profile(mode)
        assert profile.allow_delegation is False


def test_query_submodes_registered_in_contract():
    values = target_mode_values()
    assert "query_monitoring" in values
    assert "query_forecast" in values

    contract = build_target_mode_contract()
    assert "query_monitoring" in contract
    assert "query_forecast" in contract
    # 路由规则明确报告 DAG 禁用综合 query
    assert "报告 DAG 禁止" in contract


# ----------------------------------------
# 默认预算
# ----------------------------------------


def test_query_submode_default_iteration_budgets():
    assert _resolve_child_max_iterations("query_monitoring", None) == 12
    assert _resolve_child_max_iterations("query_forecast", None) == 12
    # 显式请求仍被夹紧
    assert _resolve_child_max_iterations("query_monitoring", 50) == 50
    assert _resolve_child_max_iterations("query_monitoring", 500) == 120


# ----------------------------------------
# 提示词关键句
# ----------------------------------------


def test_monitoring_prompt_boundaries():
    prompt = build_query_monitoring_prompt(["execute_sql_query", "execute_python"])
    assert "常规空气质量监测问数" in prompt
    assert "query_forecast" in prompt  # 边界中指路预报问数
    assert "表字段契约" in prompt or "字段" in prompt  # 契约优先原则出现


def test_forecast_prompt_requires_lead_time_annotation():
    prompt = build_query_forecast_prompt(["get_weather_forecast", "execute_python"])
    assert "气象与空气质量预报问数" in prompt
    assert "起报时间" in prompt
    assert "expert_meteorology" in prompt  # 研判边界
