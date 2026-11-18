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


# 探测用大 schema 工具：不同部署会按项目下线部分工具（如广东下线
# run_agent_workflow），用例不硬编码单一名称，取白名单里第一个存在的。
PROBE_TOOL_CANDIDATES = ("run_agent_workflow", "call_sub_agent", "execute_python")


def _probe_tool_name(mode: str = "query") -> str:
    mode_names = set(get_tools_by_mode(mode).keys())
    for name in PROBE_TOOL_CANDIDATES:
        if name in mode_names:
            return name
    raise AssertionError(f"query 模式白名单缺少探测工具候选：{sorted(mode_names)}")


def _isolate_project_declaration(monkeypatch) -> None:
    """隔离项目清单声明：部分项目（如 jiangxi）已在 project.yaml 真实 opt-in，
    项目声明优先于共享表，会让本文件的共享表语义测试误红或语义漂移。
    统一替换为"空声明项目上下文"——resolve 走共享表分支，其余调用点
    （模式白名单等）不受影响。"""
    from app.project_config.models import BackendManifest

    monkeypatch.setattr(
        tool_registry,
        "_load_project_context",
        lambda: SimpleNamespace(manifest=SimpleNamespace(backend=BackendManifest())),
    )


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


def test_resolver_defaults_off_for_all_modes(monkeypatch):
    """共享表默认零 opt-in：无项目声明时任何模式 resolve 均为 None（零行为变化守门）。"""
    _isolate_project_declaration(monkeypatch)
    for mode in ("query", "expert", "assistant", "office", "report", "unknown_mode_xyz"):
        assert resolve_deferred_tool_config(mode) is None, mode


def test_resolver_shared_table_and_never_stub(monkeypatch):
    _isolate_project_declaration(monkeypatch)
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
    assert _probe_tool_name("query") in deferred


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
    # 无论哪个项目检出运行，本 fixture 统一以共享表 opt-in。
    _isolate_project_declaration(monkeypatch)
    monkeypatch.setitem(tool_registry.DEFERRED_TOOL_MODES, "query", [])


async def test_tool_search_returns_full_schema(query_mode_deferred):
    probe = _probe_tool_name("query")
    tool = ToolSearchTool(mode="query")
    result = await tool.execute(query=probe)
    assert result["success"] is True
    assert result["count"] >= 1
    entry = result["data"]["tools"][0]
    assert entry["name"] == probe
    # 返回的是完整契约：parameters 非空（存根处被替换的主体）
    assert entry["schema"]["parameters"].get("properties")


async def test_tool_search_no_hit_returns_catalog(query_mode_deferred):
    probe = _probe_tool_name("query")
    tool = ToolSearchTool(mode="query")
    result = await tool.execute(query="完全不存在的功能词zzz")
    assert result["success"] is True
    assert result["count"] == 0
    assert result["data"]["tools"] == []
    assert probe in result["data"]["deferred_catalog"]


async def test_tool_search_unavailable_without_optin(monkeypatch):
    # 隔离项目清单声明：jiangxi 已对 query 真实 opt-in，未隔离时本工具可用。
    _isolate_project_declaration(monkeypatch)
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
# 3b. 检索算法（ZCode search.ts 移植）
# ========================================


def _fake_candidates():
    return {
        "execute_sql_query": {"description": "执行 SQL 查询，白名单校验"},
        "execute_python": {"description": "运行 python 数值计算"},
        "get_weather_data": {"description": "获取站点气象数据"},
        "get_weather_forecast": {"description": "获取气象预报"},
        "createBusinessChart": {"description": "绘制业务图表"},
    }


def test_search_tokenizes_snake_and_camel_names():
    from app.tools.agent_tools.tool_search_tool import search_deferred_tools

    candidates = _fake_candidates()
    # snake 切词：词元全等命中
    assert search_deferred_tools("sql query", candidates) == ["execute_sql_query"]
    # camelCase 切词
    assert search_deferred_tools("business chart", candidates) == ["createBusinessChart"]
    # 词元包含：weather 同时命中两个，按名排序稳定
    assert search_deferred_tools("weather", candidates) == [
        "get_weather_data",
        "get_weather_forecast",
    ]


def test_search_exact_name_and_select_syntax():
    from app.tools.agent_tools.tool_search_tool import search_deferred_tools

    candidates = _fake_candidates()
    assert search_deferred_tools("execute_python", candidates) == ["execute_python"]
    assert search_deferred_tools("execute_python".upper(), candidates) == ["execute_python"]
    # select: 批量精确（未知名忽略、去重）
    assert search_deferred_tools(
        "select:execute_python, get_weather_data, no_such_tool, execute_python",
        candidates,
    ) == ["execute_python", "get_weather_data"]


def test_search_required_term_filters_out():
    from app.tools.agent_tools.tool_search_tool import search_deferred_tools

    candidates = _fake_candidates()
    # +必含词未命中任何候选 → 空结果
    assert search_deferred_tools("chart +vocs", candidates) == []
    # +必含词命中描述词边界 → 只剩该工具
    assert search_deferred_tools("chart +预报", candidates) == ["get_weather_forecast"]


def test_search_description_word_boundary_scoring():
    from app.tools.agent_tools.tool_search_tool import search_deferred_tools

    candidates = _fake_candidates()
    # 描述词边界命中（+2）弱于名字命中
    assert search_deferred_tools("白名单", candidates) == ["execute_sql_query"]


async def test_tool_search_result_budget_truncates(monkeypatch, query_mode_deferred):
    """累计 schema 超体积上限时截断并提示分批检索（ZCode resultBudget 先例）。"""
    import app.agent.tool_adapter as tool_adapter_module
    from app.tools.agent_tools import tool_search_tool as tst

    big_a = {"name": "big_a", "description": "工具A", "parameters": {"properties": {f"p{i}": {"type": "string", "description": "x" * 60} for i in range(60)}}}
    big_b = {"name": "big_b", "description": "工具B", "parameters": {"properties": {f"q{i}": {"type": "string", "description": "y" * 60} for i in range(60)}}}

    def fake_get_tool_schemas(mode=None, allowed_tool_names=None):
        return [big_a, big_b]

    monkeypatch.setattr(tool_adapter_module, "get_tool_schemas", fake_get_tool_schemas)
    # 让 deferred 候选集与 fake schema 名单对齐（否则交为空走 unavailable 分支）
    monkeypatch.setattr(
        tool_registry, "compute_deferred_tool_names", lambda mode, config: frozenset({"big_a", "big_b"})
    )

    tool = tst.ToolSearchTool(mode="query")
    each = len(json.dumps(big_a, ensure_ascii=False))
    # 两条合计超上限但单条未超：第一条返回、第二条截断
    monkeypatch.setattr(tst, "MAX_SEARCH_RESULT_CHARS", each + 100, raising=False)
    result = await tool.execute(query="select:big_a,big_b")
    assert result["count"] == 1
    assert result["data"]["tools"][0]["name"] == "big_a"
    assert "截断" in result["data"]["hint"]
    assert "select:" in result["data"]["hint"]


# ========================================
# 4b. 发现状态历史派生（ZCode collectToolSearchHistory 派生思想）
# ========================================


def test_collect_called_deferred_tools_from_history():
    from app.agent.tool_adapter import collect_called_deferred_tools

    deferred = frozenset({"run_agent_workflow", "execute_sql_query"})
    history = [
        {"role": "user", "content": "查一下"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "调用工具"},
                {"type": "tool_use", "id": "tu_1", "name": "run_agent_workflow", "input": {}},
                {"type": "tool_use", "id": "tu_2", "name": "read_file", "input": {}},
            ],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}]},
        # 非列表 content（纯文本 assistant）与无效块忽略
        {"role": "assistant", "content": "纯文本回复"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_3", "name": "execute_sql_query", "input": {}}],
        },
    ]
    discovered = collect_called_deferred_tools(history, deferred)
    assert discovered == {"run_agent_workflow", "execute_sql_query"}
    # 空 deferred / 空历史安全
    assert collect_called_deferred_tools(history, frozenset()) == set()
    assert collect_called_deferred_tools([], deferred) == set()


async def test_planner_stream_upgrades_tool_called_in_earlier_turn():
    """跨 run 持久：历史里调用过的 deferred 工具，本轮直接以全 schema 常驻。"""
    allowed = ["run_agent_workflow", "tool_search"]
    runtime, captured = _make_stub_runtime(allowed, registry={"tool_search": ToolSearchTool(mode="query")})
    state = RunState(session_id="s-history", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({"run_agent_workflow"})
    # 上一条用户消息的会话历史：模型曾调用过 run_agent_workflow
    history = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_prev", "name": "run_agent_workflow", "input": {}}],
        }
    ]

    await _drive_planner_stream(runtime, state, conversation_history=history)

    tools = {t["name"]: t for t in captured["tools"]}
    assert tools["run_agent_workflow"]["parameters"].get("properties")


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


async def _drive_planner_stream(runtime, state, conversation_history=None):
    from app.agent.runtime.agent_runtime import AgentRuntime
    from app.agent.runtime import agent_runtime as runtime_module

    # 与 test_context_usage_events 同款：屏蔽多模态分支
    original = runtime_module.supports_native_multimodal
    runtime_module.supports_native_multimodal = lambda mode: False
    try:
        events = []
        async for event in AgentRuntime._run_planner_stream(
            runtime,
            state,
            {"tokens": {"total": 100}, "system_prompt": "sp", "user_conversation": []},
            conversation_history or [],
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
    probe = _probe_tool_name("query")
    state = RunState(session_id="s-fallback", user_query="q", mode="query")
    state.deferred_tool_names = frozenset({probe})

    observation = {"success": False, "error": "参数错误: 缺少必填参数"}
    coordinator._inject_deferred_schema_if_failed(probe, observation, state)

    assert "schema_injection" in observation
    assert probe in observation["schema_injection"]
    assert observation["schema_injection_notice"]

    # 成功结果 / 非 deferred 工具 / 已升级工具不注入
    ok_observation = {"success": True}
    coordinator._inject_deferred_schema_if_failed(probe, ok_observation, state)
    assert "schema_injection" not in ok_observation

    other = {"success": False}
    coordinator._inject_deferred_schema_if_failed("read_file", other, state)
    assert "schema_injection" not in other

    state.discovered_tools = {probe}
    discovered_observation = {"success": False}
    coordinator._inject_deferred_schema_if_failed(probe, discovered_observation, state)
    assert "schema_injection" not in discovered_observation


def test_run_state_defaults_keep_mechanism_off():
    state = RunState(session_id="s", user_query="q", mode="expert")
    assert state.deferred_tool_names == frozenset()
    assert state.discovered_tools == set()
