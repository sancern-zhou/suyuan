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
