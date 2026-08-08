from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.tool_classification import is_housekeeping_tool
from app.agent.runtime.types import RunState


def test_task_tools_are_not_short_circuited_by_legacy_todowrite_policy():
    runtime = AgentRuntime.__new__(AgentRuntime)
    state = RunState(
        session_id="test-session",
        user_query="continue",
        mode="assistant",
    )
    state.iteration = 3
    state.suppress_tool_names_next_turn.add("TaskUpdate")
    action = {
        "type": "TOOL_CALL",
        "tool": "TaskUpdate",
        "tool_call_id": "call-test",
        "args": {"taskId": "1"},
    }

    observation = runtime._suppressed_housekeeping_observation(state, action)

    assert observation is None


def test_suppressed_current_turn_task_tool_is_short_circuited():
    runtime = AgentRuntime.__new__(AgentRuntime)
    state = RunState(
        session_id="test-session",
        user_query="continue",
        mode="assistant",
    )
    state.iteration = 4
    state.suppress_tool_names_current_turn.add("TaskUpdate")
    action = {
        "type": "TOOL_CALL",
        "tool": "TaskUpdate",
        "tool_call_id": "call-test",
        "args": {"taskId": "1", "status": "completed"},
    }

    observation = runtime._suppressed_housekeeping_observation(state, action)

    assert observation is not None
    assert observation["success"] is False
    assert observation["suppressed_tool_call"] is True
    assert observation["data"]["tool_name"] == "TaskUpdate"
    assert "直接给出最终回答" in observation["summary"]


def test_housekeeping_only_task_turn_suppresses_task_tools_next_turn():
    runtime = AgentRuntime.__new__(AgentRuntime)
    state = RunState(
        session_id="test-session",
        user_query="continue",
        mode="assistant",
    )
    action = {
        "type": "TOOL_CALL",
        "tool": "TaskUpdate",
        "tool_call_id": "call-test",
        "args": {"taskId": "1", "status": "completed"},
    }
    observation = {"status": "success", "success": True}

    runtime._apply_housekeeping_policy(state, action, observation)

    assert state.last_tool_turn_housekeeping_only is True
    assert state.suppress_tool_names_next_turn == {
        "TaskCreate",
        "TaskUpdate",
        "TaskList",
        "TaskGet",
    }


def test_memory_tools_are_not_classified_as_task_housekeeping():
    assert is_housekeeping_tool("remember_fact") is False
    assert is_housekeeping_tool("replace_memory") is False
    assert is_housekeeping_tool("remove_memory") is False
