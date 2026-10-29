"""报告 DAG 问数子模式（query_monitoring / query_forecast / query_component）：工具、提示词与契约守卫。"""

from app.agent.prompts.query_data_prompt import (
    build_query_component_prompt,
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


def test_query_submode_whitelists_are_lean_and_disjoint():
    from app.agent.prompts.tool_registry import (
        QUERY_FORECAST_TOOL_NAMES,
        QUERY_MONITORING_TOOL_NAMES,
    )

    monitoring = set(QUERY_MONITORING_TOOL_NAMES)
    forecast = set(QUERY_FORECAST_TOOL_NAMES)

    assert "execute_crawler_sql_query" in monitoring
    assert "query_xcai_city_history" in monitoring
    # 目录解析与中台工具成对配置（乡镇站编码链路）；广东站点目录工具不进入
    assert "xuchang_station_catalog" in monitoring
    assert "query_airdata_platform" in monitoring
    assert "resolve_station_geo" not in monitoring
    assert not monitoring & {"get_weather_data", "get_weather_forecast", "get_current_weather"}

    assert "get_weather_forecast" in forecast
    assert "get_weather_data" in forecast
    assert "query_airdata_platform" in forecast
    assert not forecast & {"execute_crawler_sql_query", "query_xcai_city_history"}

    assert len(monitoring) <= 15
    assert len(forecast) <= 15
    assert not monitoring & AGENT_HIDDEN_TOOL_NAMES
    assert not forecast & AGENT_HIDDEN_TOOL_NAMES


def test_query_submodes_resolve_via_get_tools_by_mode():
    for mode in ("query_monitoring", "query_forecast"):
        tools = get_tools_by_mode(mode)
        assert tools, mode
        assert "execute_python" in tools
        assert "call_sub_agent" not in tools


def test_station_and_city_submodes_split_tool_whitelists():
    from app.agent.prompts.tool_registry import (
        QUERY_MONITORING_CITY_TOOL_NAMES,
        QUERY_MONITORING_STATION_TOOL_NAMES,
    )

    station = set(QUERY_MONITORING_STATION_TOOL_NAMES)
    city = set(QUERY_MONITORING_CITY_TOOL_NAMES)

    assert station == {
        "execute_crawler_sql_query",
        "xuchang_station_catalog",
        "query_airdata_platform",
        "execute_python",
    }
    # 乡镇站链路成对配置：城市模式有中台工具但无目录工具（站点任务归站点模式）
    assert "query_airdata_platform" in city
    assert "xuchang_station_catalog" not in city
    assert {"query_xcai_city_history", "execute_sql_query", "query_airdata_platform"} <= city
    # 【暂时下线 2026-10-27】国家城市发布数据查询不对 Agent 暴露
    assert "query_national_city_air_quality" not in city
    assert "get_weather_data" not in station | city

    for mode in ("query_monitoring_station", "query_monitoring_city"):
        tools = get_tools_by_mode(mode)
        assert tools, mode
        assert "execute_crawler_sql_query" in tools
        assert "call_sub_agent" not in tools

    profile_station = get_agent_profile("query_monitoring_station")
    profile_city = get_agent_profile("query_monitoring_city")
    assert profile_station.allow_delegation is False
    assert profile_city.allow_delegation is False


def test_query_submode_profiles_forbid_delegation():
    for mode in ("query_monitoring", "query_forecast"):
        profile = get_agent_profile(mode)
        assert profile.allow_delegation is False


def test_query_submodes_registered_in_contract():
    values = target_mode_values()
    assert "query_monitoring" in values
    assert "query_monitoring_station" in values
    assert "query_monitoring_city" in values
    assert "query_forecast" in values

    contract = build_target_mode_contract()
    assert "query_monitoring_station" in contract
    assert "query_monitoring_city" in contract
    assert "报告" in contract


def test_query_submode_default_iteration_budgets():
    assert _resolve_child_max_iterations("query_monitoring", None) == 20
    assert _resolve_child_max_iterations("query_monitoring_station", None) == 20
    assert _resolve_child_max_iterations("query_monitoring_city", None) == 20
    assert _resolve_child_max_iterations("query_forecast", None) == 20
    assert _resolve_child_max_iterations("query_monitoring", 50) == 50
    assert _resolve_child_max_iterations("query_monitoring", 500) == 120


def test_station_and_city_prompts_declare_table_level_boundary():
    from app.agent.prompts.query_data_prompt import (
        build_query_monitoring_city_prompt,
        build_query_monitoring_station_prompt,
    )

    station = build_query_monitoring_station_prompt(["execute_crawler_sql_query", "execute_python"])
    city = build_query_monitoring_city_prompt(["execute_crawler_sql_query", "execute_python"])

    assert "站点层级" in station and "StationHour/StationDay" in station
    assert "乡镇站" in station
    assert "xuchang_station_catalog" in station and "query_airdata_platform" in station
    assert "query_monitoring_city" in station
    assert "城市层级" in city and "CityHour/CityDay/CityYearPm25Avg" in city
    assert "query_monitoring_station" in city


def test_monitoring_prompt_boundaries():
    prompt = build_query_monitoring_prompt(["execute_sql_query", "execute_python"])
    assert "常规空气质量监测问数" in prompt
    assert "气象数据与预报取数" in prompt
    assert "字段" in prompt


def test_forecast_prompt_requires_lead_time_annotation():
    prompt = build_query_forecast_prompt(["get_weather_forecast", "execute_python"])
    assert "气象与空气质量预报问数" in prompt
    assert "起报时间" in prompt
    assert "静稳或输送研判" in prompt


# ----------------------------------------
# 组分问数子模式（query_component，广东省超级站）
# ----------------------------------------


def test_query_component_whitelist_is_lean():
    from app.agent.prompts.tool_registry import QUERY_COMPONENT_TOOL_NAMES

    component = set(QUERY_COMPONENT_TOOL_NAMES)
    assert {"get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"} <= component
    # 组分二期：物种级/OFP/官方重构/微量元素与四工具同入白名单
    assert {"get_vocs_species", "get_vocs_ofp", "get_ofp_top10",
            "get_pm25_recovery", "get_pm25_trace"} <= component
    assert "execute_python" in component
    # 无目录工具：组分站点名→编码映射内置于查询工具
    assert "xuchang_station_catalog" not in component
    assert "resolve_station_geo" not in component
    # 不携带监测/气象取数工具，也无委派工具
    assert not component & {"query_xcai_city_history", "get_weather_data", "execute_sql_query",
                            "call_sub_agent", "run_agent_workflow", "ask_user_question"}
    assert len(component) <= 20
    assert not component & AGENT_HIDDEN_TOOL_NAMES


def test_query_component_resolves_via_get_tools_by_mode():
    tools = get_tools_by_mode("query_component")
    assert tools
    assert "call_sub_agent" not in tools
    profile = get_agent_profile("query_component")
    assert profile.allow_delegation is False


def test_query_component_registered_in_contract_and_budget():
    assert "query_component" in target_mode_values()
    contract = build_target_mode_contract()
    assert "组分问数 Agent" in contract
    assert "query_component" in contract
    assert _resolve_child_max_iterations("query_component", None) == 20


def test_query_component_workflow_registered():
    from app.agent.workflow.mode_workflows import get_mode_workflow

    definition = get_mode_workflow("query_component")
    assert definition is not None
    phase_tools = {tool for phase in definition.phases for tool in phase.allowed_tools}
    assert {"get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
            "get_vocs_species", "get_vocs_ofp", "get_ofp_top10",
            "get_pm25_recovery", "get_pm25_trace"} <= phase_tools
    assert "query_xcai_city_history" not in phase_tools


def test_query_component_prompt_declares_station_table_and_semantics():
    prompt = build_query_component_prompt(["get_pm25_ionic", "execute_python"])
    assert "组分数据问数 Agent" in prompt
    # 站点清单内嵌（组分站与常规监测站是两套体系）
    assert "鹤山花果山=1001b" in prompt
    assert "不接受城市名" in prompt
    # 组分取数语义：小时数值、审核口径
    assert "小时" in prompt
    assert "审核" in prompt
    # 组分二期九工具语义：物种/OFP/重构/微量元素
    assert "get_vocs_species" in prompt
    assert "get_vocs_ofp" in prompt
    assert "get_ofp_top10" in prompt
    assert "get_pm25_recovery" in prompt
    assert "get_pm25_trace" in prompt
    assert "24 小时" in prompt
    # 边界：常规监测/气象/研判不承接
    assert "query_monitoring_city" in prompt
    assert "query_forecast" in prompt
    assert "expert_component" in prompt
