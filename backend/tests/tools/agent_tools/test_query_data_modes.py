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


def test_query_submode_whitelists_are_lean_and_disjoint():
    from app.agent.prompts.tool_registry import (
        QUERY_FORECAST_TOOL_NAMES,
        QUERY_MONITORING_TOOL_NAMES,
    )

    monitoring = set(QUERY_MONITORING_TOOL_NAMES)
    forecast = set(QUERY_FORECAST_TOOL_NAMES)

    assert "execute_crawler_sql_query" in monitoring
    assert "query_xcai_city_history" in monitoring
    # 站点目录解析工具不进入问数流程：Station 表 SQL 即可取目录，避免串行轮次
    assert "xuchang_station_catalog" not in monitoring
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

    assert station == {"execute_crawler_sql_query", "execute_python"}
    assert {"query_xcai_city_history", "execute_sql_query", "query_airdata_platform"} <= city
    assert "query_national_city_air_quality" in city
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
    assert _resolve_child_max_iterations("query_monitoring", None) == 4
    assert _resolve_child_max_iterations("query_monitoring_station", None) == 4
    assert _resolve_child_max_iterations("query_monitoring_city", None) == 4
    assert _resolve_child_max_iterations("query_forecast", None) == 4
    assert _resolve_child_max_iterations("query_monitoring", 50) == 50
    assert _resolve_child_max_iterations("query_monitoring", 500) == 120


def test_station_and_city_prompts_declare_table_level_boundary():
    from app.agent.prompts.query_data_prompt import (
        build_query_monitoring_city_prompt,
        build_query_monitoring_station_prompt,
    )

    station = build_query_monitoring_station_prompt(["execute_crawler_sql_query", "execute_python"])
    city = build_query_monitoring_city_prompt(["execute_crawler_sql_query", "execute_python"])

    assert "站点层级" in station and "StationHour/StationDay/Station" in station
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
