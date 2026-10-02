from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.target_mode_contract import target_mode_values
from app.tools.agent_tools.call_sub_agent import _resolve_child_max_iterations


def test_fixed_query_modes_have_separate_domain_tools():
    monitoring = set(get_tools_by_mode("query_monitoring"))
    forecast = set(get_tools_by_mode("query_forecast"))

    assert "execute_crawler_sql_query" in monitoring
    assert "query_xcai_city_history" in monitoring
    assert "get_weather_forecast" not in monitoring
    assert "get_weather_forecast" in forecast
    assert "execute_crawler_sql_query" not in forecast
    assert "execute_python" in monitoring & forecast


def test_fixed_query_modes_are_registered_and_bounded():
    assert "query_monitoring" in target_mode_values()
    assert "query_forecast" in target_mode_values()
    assert _resolve_child_max_iterations("query_monitoring", None) == 4
    assert _resolve_child_max_iterations("query_forecast", None) == 4


def test_monitoring_prompt_describes_runtime_owned_fixed_flow():
    prompt = build_react_system_prompt("query_monitoring")
    assert "固定工作流" in prompt
    assert "同一轮发出多个工具调用" in prompt
    assert "禁止多语句 SQL" in prompt


def test_forecast_prompt_preserves_forecast_provenance_boundary():
    prompt = build_react_system_prompt("query_forecast")
    assert "起报时间" in prompt
    assert "预报时效" in prompt
    assert "不做形势结论" in prompt
