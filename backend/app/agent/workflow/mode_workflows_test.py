from app.agent.workflow.catalog import workflow_catalog
from app.agent.workflow.mode_workflows import (
    allowed_tools,
    can_complete,
    current_phase,
    get_mode_workflow,
    observe_tool_results,
    render_phase_prompt,
)
from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.types import RunState
from types import SimpleNamespace


def test_query_modes_are_registered_as_fixed_agent_workflows():
    monitoring = get_mode_workflow("query_monitoring")
    forecast = get_mode_workflow("query_forecast")

    assert monitoring is workflow_catalog.get("agent_mode", "query_monitoring")
    assert forecast is workflow_catalog.get("agent_mode", "query_forecast")
    assert monitoring.max_iterations == 4
    assert [phase.name for phase in monitoring.phases] == [
        "acquire",
        "normalize",
        "deliver",
    ]


def test_station_and_city_query_modes_split_by_table_level():
    station = get_mode_workflow("query_monitoring_station")
    city = get_mode_workflow("query_monitoring_city")
    progress = {}

    assert station is not None and city is not None
    assert allowed_tools(station, progress) == {"execute_crawler_sql_query"}
    assert "query_xcai_city_history" in allowed_tools(city, progress)
    assert "xuchang_station_catalog" not in allowed_tools(station, progress)
    assert "resolve_station_geo" not in allowed_tools(city, progress)

    station_acquire = current_phase(station, progress).description
    city_acquire = current_phase(city, progress).description
    # 表契约直接注入 acquire 阶段说明，避免模型猜字段
    assert "StationHour" in station_acquire and "StationDay" in station_acquire
    assert "CityHour" in city_acquire and "CityYearPm25Avg" in city_acquire
    # 城市契约只注入城市表字段；站点独有字段（如 UniqueCode）不出现
    assert "UniqueCode" not in city_acquire
    # 层级拆分是功能聚焦而非硬禁止
    assert "禁止查询" not in station_acquire and "禁止查询" not in city_acquire
    # 会话资源工具不再进入 acquire 阶段
    assert "list_session_resources" not in allowed_tools(station, progress)
    assert "read_session_resource" not in allowed_tools(city, progress)


def test_query_workflow_advances_after_successful_batch():
    definition = get_mode_workflow("query_monitoring")
    progress = {}

    assert current_phase(definition, progress).name == "acquire"
    assert "execute_sql_query" in allowed_tools(definition, progress)
    assert "execute_python" not in allowed_tools(definition, progress)
    assert can_complete(definition, progress) is False

    observe_tool_results(definition, progress, [{
        "tool_name": "execute_sql_query",
        "result": {"success": True, "file_path": "/data/result.json"},
    }])

    assert current_phase(definition, progress).name == "normalize"
    assert "execute_python" in allowed_tools(definition, progress)
    assert "execute_sql_query" not in allowed_tools(definition, progress)
    assert can_complete(definition, progress) is True


def test_session_input_tools_do_not_consume_acquisition_attempts():
    definition = get_mode_workflow("query_monitoring")
    progress = {}

    observe_tool_results(definition, progress, [{
        "tool_name": "read_file",
        "result": {"success": True, "content": "query scope"},
    }])

    assert current_phase(definition, progress).name == "acquire"
    assert progress == {}


def test_acquisition_ignores_support_tool_failures_in_mixed_batch():
    definition = get_mode_workflow("query_monitoring")
    progress = {}

    observe_tool_results(definition, progress, [
        {
            "tool_name": "execute_sql_query",
            "result": {"success": True, "file_path": "/data/result.json"},
        },
        {
            "tool_name": "read_file",
            "result": {"success": False, "error": "missing optional input"},
        },
    ])

    assert current_phase(definition, progress).name == "normalize"


def test_query_workflow_allows_only_one_failed_batch_repair():
    definition = get_mode_workflow("query_forecast")
    progress = {}
    failed = [{
        "tool_name": "get_weather_forecast",
        "result": {"success": False, "error": "temporary"},
    }]

    observe_tool_results(definition, progress, failed)
    assert current_phase(definition, progress).name == "acquire"
    assert progress["phase_attempt"] == 1
    assert progress["last_failed_tools"] == ["get_weather_forecast"]

    observe_tool_results(definition, progress, failed)
    assert current_phase(definition, progress).name == "normalize"
    assert progress["phase_attempt"] == 0


def test_normalization_tool_turn_forces_delivery_without_tools():
    definition = get_mode_workflow("query_monitoring")
    progress = {"phase_index": 1}

    observe_tool_results(definition, progress, [{
        "tool_name": "execute_python",
        "result": {"success": True},
    }])

    assert current_phase(definition, progress).name == "deliver"
    assert allowed_tools(definition, progress) == set()
    assert "停止调用工具" in render_phase_prompt(definition, progress)


def test_agent_runtime_filters_tools_by_fixed_workflow_phase():
    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(extra_tool_names=None)
    state = RunState(session_id="session", user_query="query", mode="query_monitoring")

    acquire_tools = runtime._allowed_tool_names_for_state(state)
    assert "execute_sql_query" in acquire_tools
    assert "execute_python" not in acquire_tools

    state.fixed_workflow_progress = {"phase_index": 1}
    normalize_tools = runtime._allowed_tool_names_for_state(state)
    assert "execute_sql_query" not in normalize_tools
    assert "execute_python" in normalize_tools

    state.fixed_workflow_progress = {"phase_index": 2}
    assert runtime._allowed_tool_names_for_state(state) == []


def test_fixed_workflow_whitelist_keeps_submit_result_visible():
    """submit_result 是交付边界工具：任何阶段不得被阶段白名单过滤或拦截。"""
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(extra_tool_names=None)
    # 模拟 call_sub_agent 给带 result_schema 的子会话注入交付工具
    runtime.executor = SimpleNamespace(
        tool_registry={"submit_result": object(), "execute_sql_query": object()}
    )
    state = RunState(session_id="fw-test", user_query="取数", mode="query_monitoring")
    state.fixed_workflow_progress = {}

    # acquire 阶段：取数工具可见，submit_result 虽不在 phase_tools 但必须保留
    names = runtime._allowed_tool_names_for_state(state)
    assert names is not None
    assert "execute_sql_query" in names
    assert "submit_result" in names
    assert "execute_python" not in names

    # 推进到 deliver 阶段（工具空集）：submit_result 仍然可见
    definition = get_mode_workflow("query_monitoring")
    state.fixed_workflow_progress = {"phase_index": len(definition.phases) - 1}
    names = runtime._allowed_tool_names_for_state(state)
    assert names == ["submit_result"]

    # 阶段拦截观察器同样放行 submit_result
    action = {"type": "TOOL_CALL", "tool": "submit_result", "args": {"result": {}}}
    observation = runtime._fixed_workflow_blocked_observation(state, action)
    assert observation is None

    blocked_action = {"type": "TOOL_CALL", "tool": "execute_sql_query", "args": {"sql": "SELECT 1"}}
    blocked = runtime._fixed_workflow_blocked_observation(state, blocked_action)
    assert blocked is not None
    assert "execute_sql_query" in blocked["data"]["blocked_tools"]
