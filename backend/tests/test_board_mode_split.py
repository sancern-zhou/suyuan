from types import SimpleNamespace

import pytest

from app.agent.prompts.board_prompt import build_board_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import BOARD_TOOL_ORDER, get_tools_by_mode
from app.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.mode_capabilities import supports_native_multimodal
from app.agent.runtime.types import PlannerResult, RunState


class _StreamingPlanner:
    async def think_and_action_streaming(self, **kwargs):
        yield {"type": "streaming_text", "data": {"chunk": "自然回复", "is_complete": False}}
        yield {"type": "streaming_text", "data": {"chunk": "。", "is_complete": True}}
        yield {
            "type": "action",
            "data": {"action": {"type": "PLAIN_TEXT_REPLY", "answer": "自然回复。"}},
        }


class _Executor:
    tool_registry = {}


class _Diagnostics:
    def log_report(self, **kwargs):
        return None


class _Coordinator:
    loop_guard = None


class _Writer:
    def __init__(self):
        self.final_answers = []

    def add_user_message(self, content):
        return None

    def add_iteration(self, thought, action, observation):
        self.final_answers.append(action.get("answer"))


class _ObservationProcessor:
    def capture_last_knowledge_sources(self, state):
        return False


class _Finalizer:
    async def complete(self, state, answer, **kwargs):
        yield {"type": "captured_final", "data": {"answer": answer}}


async def _no_events():
    if False:
        yield None


def test_board_mode_has_minimal_dedicated_tool_whitelist():
    board_tools = get_tools_by_mode("board")
    chart_tools = get_tools_by_mode("chart")

    assert list(board_tools) == [
        "list_session_resources",
        "read_file",
        "create_drawio_board",
        "accept_drawio_board_candidate",
    ]
    assert list(board_tools) == BOARD_TOOL_ORDER
    assert "create_drawio_board" not in chart_tools
    assert "execute_echarts_python" in chart_tools


def test_board_prompt_is_separate_from_chart_workflows():
    prompt = build_board_prompt(
        list(get_tools_by_mode("board")),
        board_context={
            "current_xml": "<mxfile><diagram id=\"board\" /></mxfile>",
            "selected_cells": [{"id": "node-1"}],
            "version": 3,
        },
    )

    assert "画板创作智能体" in prompt
    assert "board_run_contract" not in prompt
    assert "node-1" in prompt
    assert "<mxfile>" in prompt
    assert "ECharts" not in prompt
    assert "execute_sql_query" not in prompt
    assert "空气质量" not in prompt


def test_board_prompt_requires_progressive_design_guide_reading_before_drawing():
    prompt = build_board_prompt(list(get_tools_by_mode("board")))

    base_rules = "先读取基础规范"
    route_rules = "根据绘制需求识别主要图形类型"
    draw_after_reading = "完成必要阅读后，才可调用 `create_drawio_board`"
    assert base_rules in prompt
    assert route_rules in prompt
    assert draw_after_reading in prompt
    assert prompt.index(base_rules) < prompt.index(route_rules) < prompt.index(draw_after_reading)
    assert "最多读取 1 至 2 份最匹配的专项设计文档" in prompt
    assert "禁止一次性读取全部 `drawio_patterns` 文档" in prompt
    assert "仅修改文字、颜色、字号、尺寸或位置" in prompt
    assert "可以跳过专项设计文档" in prompt
    assert "必须实际查看截图" in prompt


def test_prompt_builder_routes_board_mode_to_board_prompt():
    prompt = build_react_system_prompt(
        mode="board",
        board_context={"current_xml": "<mxfile><diagram /></mxfile>"},
    )

    assert "画板创作智能体" in prompt
    assert "ECharts" not in prompt


def test_board_mode_supports_native_multimodal_input():
    assert supports_native_multimodal("board") is True


@pytest.mark.asyncio
async def test_board_mode_streams_plain_text_like_other_modes():
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=_StreamingPlanner(),
        tool_executor=_Executor(),
        context_builder=None,
        attachments=[],
    )
    runtime.planner = runtime.config.planner
    runtime.executor = _Executor()
    runtime.context_diagnostics = _Diagnostics()
    runtime.tool_coordinator = _Coordinator()
    runtime.events = RuntimeEventBus()

    events = [
        event
        async for event in runtime._run_planner_stream(
            RunState(session_id="board-session", user_query="解释一下", mode="board"),
            {"system_prompt": "system", "user_conversation": "user"},
            conversation_history=[],
        )
    ]

    chunks = [event["data"]["chunk"] for event in events if event.get("type") == "streaming_text"]
    assert "".join(chunks) == "自然回复。"


@pytest.mark.asyncio
async def test_board_completion_preserves_model_answer_after_board_tool_result():
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = SimpleNamespace()
    runtime.writer = _Writer()
    runtime.observation_processor = _ObservationProcessor()
    runtime.finalizer = _Finalizer()
    runtime._apply_steering_inputs = lambda state: _no_events()

    state = RunState(session_id="board-session", user_query="修改后解释", mode="board")
    state.last_observation = {
        "success": True,
        "data": {
            "artifact_kind": "drawio_board",
            "changed": True,
            "changed_cells": [],
            "applied_operations": 0,
        },
        "metadata": {"generator": "create_drawio_board"},
    }
    planner_result = PlannerResult(
        action={"type": "PLAIN_TEXT_REPLY", "answer": "已经重新绘制，并细化了数据抓取范围。"}
    )

    events = [
        event
        async for event in runtime._complete_response(
            state,
            planner_result,
            planner_result.action["answer"],
        )
    ]

    assert events[-1]["data"]["answer"] == "已经重新绘制，并细化了数据抓取范围。"
    assert runtime.writer.final_answers[-1] == "已经重新绘制，并细化了数据抓取范围。"
