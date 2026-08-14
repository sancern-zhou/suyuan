from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import AGENT_HIDDEN_TOOL_NAMES
from app.agent import tool_adapter
from app.agent.react_agent import create_react_agent
from app.agent.runtime.agent_runtime import AgentRuntime, CustomAgentTerminalError
from app.agent.runtime.types import RunState
import pytest
from types import SimpleNamespace


class FakeTool:
    def __init__(self, name):
        self.name = name

    def is_available(self):
        return True

    def get_function_schema(self):
        return {"name": self.name, "description": self.name, "parameters": {"type": "object"}}


class FakeRegistry:
    def __init__(self):
        self.tools = [FakeTool("alpha"), FakeTool("beta"), FakeTool("gamma")]

    def get_all_tools(self):
        return [{"tool": tool} for tool in self.tools]


def test_custom_prompt_is_minimal_and_uses_no_business_role_prompt():
    prompt = build_react_system_prompt("custom", available_tools=["alpha"])

    assert "按用户任务执行" in prompt
    assert "只能调用运行时提供的工具" in prompt
    assert "空气质量" not in prompt
    assert "社交" not in prompt
    assert len(prompt) < 500


def test_custom_tool_schemas_are_exact_and_keep_user_order(monkeypatch):
    monkeypatch.setattr(tool_adapter, "global_tool_registry", FakeRegistry())

    schemas = tool_adapter.get_tool_schemas(
        mode="custom",
        allowed_tool_names=["gamma", "alpha"],
    )

    assert [schema["name"] for schema in schemas] == ["gamma", "alpha"]


def test_custom_tool_schemas_exclude_agent_hidden_tools(monkeypatch):
    hidden_tool = next(iter(AGENT_HIDDEN_TOOL_NAMES))
    registry = FakeRegistry()
    registry.tools.append(FakeTool(hidden_tool))
    monkeypatch.setattr(tool_adapter, "global_tool_registry", registry)

    schemas = tool_adapter.get_tool_schemas(
        mode="custom",
        allowed_tool_names=[hidden_tool, "alpha"],
    )

    assert [schema["name"] for schema in schemas] == ["alpha"]


def test_react_agent_factory_accepts_an_explicit_registry(monkeypatch):
    explicit_registry = {"alpha": lambda: None}

    class FakeAgent:
        def __init__(self, tool_registry, **kwargs):
            self.tool_registry = tool_registry
            self.kwargs = kwargs

    monkeypatch.setattr("app.agent.react_agent.ReActAgent", FakeAgent)

    agent = create_react_agent(tool_registry=explicit_registry, enable_memory=False)

    assert agent.tool_registry is explicit_registry
    assert agent.kwargs["enable_memory"] is False


def test_custom_loop_guard_terminates_on_second_identical_block():
    state = RunState(session_id="s", user_query="run", mode="custom")
    action = {"type": "TOOL_CALL", "tool": "alpha", "args": {"value": 1}}
    records = [{
        "tool_name": "alpha",
        "tool_input": {"value": 1},
        "result": {"loop_guard": True, "severity": "block"},
    }]

    AgentRuntime._enforce_custom_tool_terminal_rules(state, action, records)
    with pytest.raises(CustomAgentTerminalError, match="工具循环已终止"):
        AgentRuntime._enforce_custom_tool_terminal_rules(state, action, records)


def test_custom_runtime_stops_if_a_selected_tool_becomes_unavailable():
    state = RunState(session_id="s", user_query="run", mode="custom")
    records = [{
        "tool_name": "alpha",
        "tool_input": {},
        "result": {"success": False, "error": "工具不可用: alpha"},
    }]

    with pytest.raises(CustomAgentTerminalError, match="工具状态已变化"):
        AgentRuntime._enforce_custom_tool_terminal_rules(state, {}, records)


@pytest.mark.parametrize("message", [
    "HTTP 400 Bad Request",
    "status code: 400 invalid request",
    "Error code: 400 - invalid tool schema",
    "HTTP 401 Unauthorized",
    "HTTP 403 Forbidden",
])
def test_deterministic_model_errors_are_recognized(message):
    assert AgentRuntime._is_deterministic_model_error(RuntimeError(message)) is True


@pytest.mark.parametrize("message", [
    "已达到 Token Plan 用量上限：请升级 Token Plan 套餐或购买积分补充用量。 (2056)",
    "insufficient_quota: billing limit reached",
    "HTTP 402 Payment Required",
])
def test_exhausted_quota_errors_are_terminal(message):
    assert AgentRuntime._is_terminal_quota_error(RuntimeError(message)) is True


@pytest.mark.asyncio
async def test_ppt_runtime_stops_immediately_when_token_plan_is_exhausted():
    calls = 0

    class FakeFinalizer:
        async def fatal_error(self, state, error):
            yield {"type": "fatal_error", "data": {"error": str(error)}}

    async def no_events(state):
        if False:
            yield None

    async def close_steering(state):
        return None

    async def failing_iteration(state):
        nonlocal calls
        calls += 1
        raise RuntimeError("Error code: 429 - 已达到 Token Plan 用量上限")
        yield

    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(agent_logger=None, max_iterations=80, is_interruption=False)
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = SimpleNamespace(
        start=lambda state: {"type": "start"},
        error=lambda state, error: {"type": "error", "data": {"error": str(error)}},
    )
    runtime.finalizer = FakeFinalizer()
    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None
    runtime._close_steering = close_steering
    runtime._apply_steering_inputs = no_events
    runtime._run_iteration = failing_iteration
    state = RunState(session_id="s", user_query="run", mode="ppt")

    events = [event async for event in runtime._run_locked(state, None)]

    assert calls == 1
    assert events[-1]["type"] == "fatal_error"
    assert "额度" in events[-1]["data"]["error"]


@pytest.mark.asyncio
async def test_ppt_runtime_breaks_after_two_deterministic_model_failures():
    calls = 0

    class FakeFinalizer:
        async def fatal_error(self, state, error):
            yield {"type": "fatal_error", "data": {"error": str(error)}}

    async def no_events(state):
        if False:
            yield None

    async def close_steering(state):
        return None

    async def failing_iteration(state):
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 400 Bad Request")
        yield

    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(agent_logger=None, max_iterations=80, is_interruption=False)
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = SimpleNamespace(
        start=lambda state: {"type": "start"},
        error=lambda state, error: {"type": "error", "data": {"error": str(error)}},
    )
    runtime.finalizer = FakeFinalizer()
    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None
    runtime._close_steering = close_steering
    runtime._apply_steering_inputs = no_events
    runtime._run_iteration = failing_iteration
    state = RunState(session_id="s", user_query="run", mode="ppt")

    events = [event async for event in runtime._run_locked(state, None)]

    assert calls == 2
    assert events[-1]["type"] == "fatal_error"
    assert "已熔断" in events[-1]["data"]["error"]


@pytest.mark.asyncio
async def test_custom_iteration_limit_emits_fatal_failure_not_continue_prompt():
    class FakeFinalizer:
        async def fatal_error(self, state, error):
            yield {"type": "fatal_error", "data": {"error": str(error)}}

        async def timeout(self, state):
            yield {"type": "complete", "data": {"answer": "是否继续？"}}

    async def no_events(state):
        if False:
            yield None

    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(agent_logger=None, max_iterations=1, is_interruption=False)
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = SimpleNamespace(start=lambda state: {"type": "start"})
    runtime.finalizer = FakeFinalizer()
    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None
    runtime._apply_steering_inputs = no_events
    runtime._run_iteration = no_events
    state = RunState(session_id="s", user_query="run", mode="custom")

    events = [event async for event in runtime._run_locked(state, None)]

    assert events[-1]["type"] == "fatal_error"
    assert "未形成成功或失败终态" in events[-1]["data"]["error"]


@pytest.mark.asyncio
async def test_custom_runtime_breaks_after_two_deterministic_model_failures():
    calls = 0

    class FakeFinalizer:
        async def fatal_error(self, state, error):
            yield {"type": "fatal_error", "data": {"error": str(error)}}

    async def no_events(state):
        if False:
            yield None

    async def failing_iteration(state):
        nonlocal calls
        calls += 1
        raise RuntimeError("Error code: 400 - invalid request body")
        yield

    runtime = object.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(agent_logger=None, max_iterations=120, is_interruption=False)
    runtime.planner = SimpleNamespace(is_interruption=False)
    runtime.writer = SimpleNamespace(load_initial_history_if_needed=lambda messages: None)
    runtime.events = SimpleNamespace(
        start=lambda state: {"type": "start"},
        error=lambda state, error: {"type": "error", "data": {"error": str(error)}},
    )
    runtime.finalizer = FakeFinalizer()
    runtime._raise_if_cancelled = lambda: None
    runtime._ensure_user_message_written = lambda state: None
    runtime._apply_steering_inputs = no_events
    runtime._run_iteration = failing_iteration
    state = RunState(session_id="s", user_query="run", mode="custom")

    events = [event async for event in runtime._run_locked(state, None)]

    assert calls == 2
    assert events[-1]["type"] == "fatal_error"
    assert "已熔断" in events[-1]["data"]["error"]
