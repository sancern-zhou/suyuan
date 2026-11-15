"""deferred tools（tool_search 按需注入 schema）共享机制测试。

覆盖四层：
1. 存根构造与豁免（tool_adapter.make_stub_schema / apply_deferred_tool_stubs）；
2. 配置解析（共享表 / 项目清单优先级 / 全局缰绳 / 默认全关零行为变化）；
3. ToolSearchTool 检索（真实注册表、模式隔离、命中/未命中/未启用）；
4. 运行时接线（_run_planner_stream 存根 pass、discovered 升级、调用即升级、
   失败兜底注入完整 schema）。
"""

import json
from types import SimpleNamespace

import pytest

from app.agent.prompts import tool_registry
from app.agent.prompts.tool_registry import (
    DEFERRED_NEVER_STUB_TOOL_NAMES,
    DeferredToolConfig,
    compute_deferred_tool_names,
    get_tools_by_mode,
    resolve_deferred_tool_config,
)
from app.agent.runtime.types import RunState
from app.agent.tool_adapter import (
    DEFERRED_STUB_SCHEMA_CHAR_FLOOR,
    apply_deferred_tool_stubs,
    get_tool_schemas,
    make_stub_schema,
)
from app.tools.agent_tools.tool_search_tool import ToolSearchTool
from config.settings import settings


def _schema_size(schema):
    return len(json.dumps(schema, ensure_ascii=False))


# ========================================
# 1. 存根构造与豁免
# ========================================


def test_make_stub_schema_keeps_routing_drops_params():
    schema = {
        "name": "some_tool",
        "description": "查询站点数据",
        "parameters": {
            "type": "object",
            "properties": {
                "station": {"type": "string", "description": "站点编码", "enum": ["a", "b"]},
                "start_time": {"type": "string", "description": "开始时间"},
            },
            "required": ["station"],
        },
    }
    stub = make_stub_schema(schema)
    assert stub["name"] == "some_tool"
    assert "查询站点数据" in stub["description"]
    assert "tool_search" in stub["description"]
    assert stub["parameters"] == {"type": "object", "properties": {}, "additionalProperties": True}
    assert _schema_size(stub) < _schema_size(schema)


def test_apply_deferred_tool_stubs_exemptions():
    big = {
        "name": "big_tool",
        "description": "x" * 100,
        "parameters": {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(30)}},
    }
    small = {
        "name": "small_tool",
        "description": "小工具",
        "parameters": {"type": "object", "properties": {}},
    }
    schemas = [big, small]
    assert _schema_size(small) <= DEFERRED_STUB_SCHEMA_CHAR_FLOOR

    # 小工具豁免：全 schema 低于下限不值得存根化
    result, stubbed, saved = apply_deferred_tool_stubs(
        schemas, deferred_names={"big_tool", "small_tool"}
    )
    assert stubbed == 1
    assert saved > 0
    by_name = {s["name"]: s for s in result}
    assert by_name["small_tool"] == small
    assert by_name["big_tool"]["parameters"]["properties"] == {}

    # discovered 工具不存根（已升级回全 schema）
    result, stubbed, _ = apply_deferred_tool_stubs(
        schemas, deferred_names={"big_tool"}, discovered_names={"big_tool"}
    )
    assert stubbed == 0
    assert result[0] == big

    # 未启用（空集）原样返回
    result, stubbed, saved = apply_deferred_tool_stubs(schemas, deferred_names=frozenset())
    assert result == schemas
    assert (stubbed, saved) == (0, 0)


# ========================================
# 2. 配置解析
# ========================================


def test_resolver_defaults_off_for_all_modes():
    """共享层默认零 opt-in：任何模式 resolve 均为 None（零行为变化守门）。"""
    for mode in ("query", "expert", "assistant", "office", "report", "unknown_mode_xyz"):
        assert resolve_deferred_tool_config(mode) is None, mode


def test_resolver_shared_table_and_never_stub(monkeypatch):
    monkeypatch.setitem(
        tool_registry.DEFERRED_TOOL_MODES, "query", ["execute_sql_query", "read_file"]
    )
    config = resolve_deferred_tool_config("query")
    assert isinstance(config, DeferredToolConfig)
    assert config.always_on == frozenset({"execute_sql_query", "read_file"})

    deferred = compute_deferred_tool_names("query", config)
    mode_names = set(get_tools_by_mode("query").keys())
    assert deferred <= mode_names
    # always_on 与永不存根集合（含交互/交付工具）被排除
    assert "execute_sql_query" not in deferred
    assert "read_file" not in deferred
    assert not (deferred & DEFERRED_NEVER_STUB_TOOL_NAMES)
    assert "ask_user_question" not in deferred
    # 大 schema 工具保留在候选集
    assert "run_agent_workflow" in deferred


def test_resolver_kill_switch(monkeypatch):
    monkeypatch.setitem(tool_registry.DEFERRED_TOOL_MODES, "query", [])
    monkeypatch.setattr(settings, "agent_deferred_tools_enabled", False)
    assert resolve_deferred_tool_config("query") is None


def test_resolver_project_declaration_wins_over_shared_table(monkeypatch):
    from app.project_config.models import BackendManifest

    fake_context = SimpleNamespace(
        manifest=SimpleNamespace(
            backend=BackendManifest(agent_mode_deferred_tools={"query": ["grep"]})
        )
    )
    monkeypatch.setattr(tool_registry, "_load_project_context", lambda: fake_context)
    monkeypatch.setitem(tool_registry.DEFERRED_TOOL_MODES, "query", ["read_file"])

    config = resolve_deferred_tool_config("query")
    assert config is not None
    # 项目声明优先：always_on 取 manifest 值而非共享表
    assert config.always_on == frozenset({"grep"})
    assert "read_file" in compute_deferred_tool_names("query", config)


def test_manifest_accepts_new_field():
    from app.project_config.models import BackendManifest

    manifest = BackendManifest(agent_mode_deferred_tools={"custom_qa": ["read_file"]})
    assert manifest.agent_mode_deferred_tools == {"custom_qa": ["read_file"]}
    assert BackendManifest().agent_mode_deferred_tools == {}


# ========================================
# 3. ToolSearchTool 检索
# ========================================


@pytest.fixture
def query_mode_deferred(monkeypatch):
    monkeypatch.setitem(tool_registry.DEFERRED_TOOL_MODES, "query", [])


async def test_tool_search_returns_full_schema(query_mode_deferred):
    tool = ToolSearchTool(mode="query")
    result = await tool.execute(query="run_agent_workflow")
    assert result["success"] is True
    assert result["count"] >= 1
    entry = result["data"]["tools"][0]
    assert entry["name"] == "run_agent_workflow"
    # 返回的是完整契约：parameters 非空（存根处被替换的主体）
    assert entry["schema"]["parameters"].get("properties")


async def test_tool_search_no_hit_returns_catalog(query_mode_deferred):
    tool = ToolSearchTool(mode="query")
    result = await tool.execute(query="完全不存在的功能词zzz")
    assert result["success"] is True
    assert result["count"] == 0
    assert result["data"]["tools"] == []
    assert "run_agent_workflow" in result["data"]["deferred_catalog"]


async def test_tool_search_unavailable_without_optin():
    tool = ToolSearchTool(mode="query")
    result = await tool.execute(query="anything")
    assert result["success"] is False
    assert result["error"] == "deferred_tools_unavailable"


async def test_tool_search_validates_query_and_clamps_limit(query_mode_deferred):
    tool = ToolSearchTool(mode="query")
    empty = await tool.execute(query="  ")
    assert empty["success"] is False

    result = await tool.execute(query="file write", max_results=99)
    assert result["success"] is True
    assert result["count"] <= 10


async def test_tool_search_schema_compact():
    """tool_search 自身 schema 必须 ≤1000 字符（预算守门，参考值 ~700）。"""
    schema = ToolSearchTool(mode="query").get_function_schema()
    assert _schema_size(schema) <= 1000


# ========================================
# 4. 运行时接线
# ========================================


def _make_stub_runtime(allowed_names, registry=None):
    captured = {}

    async def planner_stream(**kwargs):
        captured["tools"] = kwargs.get("tools")
        yield {
            "type": "action",
            "data": {
                "thought": None,
                "action": {"type": "PLAIN_TEXT_REPLY", "answer": "好"},
                "raw_thinking_blocks": None,
                "yielded_tool_use_count": 0,
            },
        }

    async def _noop_persist(*args, **kwargs):
        return True

    return (
        SimpleNamespace(
            planner=SimpleNamespace(think_and_action_streaming=planner_stream),
            events=SimpleNamespace(
                assistant_delta=lambda *a, **k: {"type": "assistant_delta"},
                thought=lambda *a, **k: {"type": "thought"},
                thinking_content=lambda *a, **k: {"type": "thinking_content"},
                tool_use=lambda *a, **k: {"type": "tool_use"},
            ),
            executor=SimpleNamespace(tool_registry=registry or {}, runtime_metadata={}),
            tool_coordinator=SimpleNamespace(
                loop_guard=None,
                prepare_tool_input_for_state=lambda name, inp, state: (inp, None),
            ),
            context_diagnostics=SimpleNamespace(log_report=lambda **kw: None),
            config=SimpleNamespace(
                llm_provider=None, llm_model="test-model", is_interruption=None, auto_profile=None
            ),
            _raise_if_cancelled=lambda: None,
            _allowed_tool_names_for_state=lambda state: allowed_names,
            _tool_names_to_suppress=lambda state: [],
            _fixed_workflow_blocked_observation=lambda *a, **k: None,
            _suppressed_housekeeping_observation=lambda *a, **k: None,
            _effective_attachments=lambda state: [],
            _record_visual_context=lambda *a, **k: None,
            _persist_context_usage=_noop_persist,
        ),
        captured,
    )


async def _drive_planner_stream(runtime, state):
    from app.agent.runtime.agent_runtime import AgentRuntime
    from app.agent.runtime import agent_runtime as runtime_module

    # 与 test_context_usage_events 同款：屏蔽多模态分支
    original = runtime_module.supports_native_multimodal
    runtime_module.supports_native_multimodal = lambda mode: False
    try:
        events = []
        async for event in AgentRuntime._run_planner_stream(
            runtime, state, {"tokens": {"total": 100}, "system_prompt": "sp", "user_conversation": []}, []
        ):
            events.append(event)
        return events
    finally:
        runtime_module.supports_native_multimodal = original


async def test_planner_stream_applies_stubs_and_backfills_tool_search():
    allowed = ["run_agent_workflow", "read_file", "tool_search"]
    runtime, captured = _make_stub_runtime(allowed, registry={"tool_search": ToolSearchTool(mode="query")})
    state = RunState(session_id="s", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({"run_agent_workflow"})

    await _drive_planner_stream(runtime, state)

    tools = {t["name"]: t for t in captured["tools"]}
    # 存根化：参数契约替换为宽松对象，描述带召回提示
    stub = tools["run_agent_workflow"]
    assert stub["parameters"]["properties"] == {}
    assert stub["parameters"]["additionalProperties"] is True
    assert "tool_search" in stub["description"]
    # 非 deferred 工具保持全 schema
    assert tools["read_file"]["parameters"].get("properties")
    # tool_search 从 executor 注册表回填进请求
    assert "tool_search" in tools
    # token 估算反映存根后的真实请求体
    assert state.context_breakdown["tools"] > 0


async def test_planner_stream_upgrades_discovered_tool_to_full_schema():
    allowed = ["run_agent_workflow", "tool_search"]
    runtime, captured = _make_stub_runtime(allowed, registry={"tool_search": ToolSearchTool(mode="query")})
    state = RunState(session_id="s", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({"run_agent_workflow"})
    state.discovered_tools = {"run_agent_workflow"}

    await _drive_planner_stream(runtime, state)

    tools = {t["name"]: t for t in captured["tools"]}
    assert tools["run_agent_workflow"]["parameters"].get("properties")


async def test_planner_stream_without_optin_is_unchanged():
    allowed = ["run_agent_workflow", "read_file"]
    runtime, captured = _make_stub_runtime(allowed)
    state = RunState(session_id="s", user_query="q", mode="query")

    await _drive_planner_stream(runtime, state)

    tools = captured["tools"]
    assert {t["name"] for t in tools} == {"run_agent_workflow", "read_file"}
    assert all("tool_search" not in (t.get("description") or "") for t in tools)
    assert "tool_search" not in {t["name"] for t in tools}


async def test_tool_use_upgrades_deferred_tool_on_call():
    """模型对存根工具发起调用即升级（无论执行成败），下一轮换回全 schema。"""

    async def planner_stream(**kwargs):
        yield {
            "type": "tool_use",
            "data": {"tool_use_id": "tu_1", "tool_name": "ghost_tool", "input": {"x": 1}},
        }
        yield {
            "type": "action",
            "data": {
                "thought": None,
                "action": {"type": "PLAIN_TEXT_REPLY", "answer": "好"},
                "raw_thinking_blocks": None,
                "yielded_tool_use_count": 0,
            },
        }

    async def execute_tool_with_retry(**kwargs):
        return {"success": False, "error": "工具不存在: ghost_tool"}

    async def _noop_persist(*args, **kwargs):
        return True

    runtime = SimpleNamespace(
        planner=SimpleNamespace(think_and_action_streaming=planner_stream),
        events=SimpleNamespace(
            assistant_delta=lambda *a, **k: {"type": "assistant_delta"},
            thought=lambda *a, **k: {"type": "thought"},
            thinking_content=lambda *a, **k: {"type": "thinking_content"},
            tool_use=lambda *a, **k: {"type": "tool_use"},
        ),
        executor=SimpleNamespace(
            tool_registry={},
            runtime_metadata={},
            execute_tool_with_retry=execute_tool_with_retry,
        ),
        tool_coordinator=SimpleNamespace(
            loop_guard=None,
            prepare_tool_input_for_state=lambda name, inp, state: (inp, None),
        ),
        context_diagnostics=SimpleNamespace(log_report=lambda **kw: None),
        config=SimpleNamespace(
            llm_provider=None, llm_model="test-model", is_interruption=None, auto_profile=None
        ),
        _raise_if_cancelled=lambda: None,
        _allowed_tool_names_for_state=lambda state: None,
        _tool_names_to_suppress=lambda state: [],
        _fixed_workflow_blocked_observation=lambda *a, **k: None,
        _suppressed_housekeeping_observation=lambda *a, **k: None,
        _effective_attachments=lambda state: [],
        _record_visual_context=lambda *a, **k: None,
        _persist_context_usage=_noop_persist,
    )
    state = RunState(session_id="s-upgrade", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({"ghost_tool"})

    events = await _drive_planner_stream(runtime, state)
    # 排干流式执行 task，避免悬挂告警
    done = [e for e in events if e.get("type") == "_planner_done"]
    for executor_event in done:
        streaming_executor = executor_event["streaming_tool_executor"]
        for execution in streaming_executor._executions:
            if execution.task is not None:
                await execution.task

    assert "ghost_tool" in state.discovered_tools


async def test_coordinator_injects_schema_when_stub_call_fails():
    """存根工具盲调失败：observation 附完整 schema（错误信息即召回钩子）。"""
    from app.agent.runtime.tool_coordinator import ToolCoordinator

    coordinator = ToolCoordinator(
        SimpleNamespace(tool_registry={}),
        knowledge_base_ids=None,
        schema_injector=None,
    )
    state = RunState(session_id="s-fallback", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({"run_agent_workflow"})

    observation = {"success": False, "error": "参数错误: 缺少必填参数"}
    coordinator._inject_deferred_schema_if_failed("run_agent_workflow", observation, state)

    assert "schema_injection" in observation
    assert "run_agent_workflow" in observation["schema_injection"]
    assert observation["schema_injection_notice"]

    # 成功结果 / 非 deferred 工具 / 已升级工具不注入
    ok_observation = {"success": True}
    coordinator._inject_deferred_schema_if_failed("run_agent_workflow", ok_observation, state)
    assert "schema_injection" not in ok_observation

    other = {"success": False}
    coordinator._inject_deferred_schema_if_failed("read_file", other, state)
    assert "schema_injection" not in other

    state.discovered_tools = {"run_agent_workflow"}
    discovered_observation = {"success": False}
    coordinator._inject_deferred_schema_if_failed("run_agent_workflow", discovered_observation, state)
    assert "schema_injection" not in discovered_observation


def test_run_state_defaults_keep_mechanism_off():
    state = RunState(session_id="s", user_query="q", mode="expert")
    assert state.deferred_tool_names == frozenset()
    assert state.discovered_tools == set()
