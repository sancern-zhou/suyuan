import pytest

from app.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from app.agent.runtime.event_bus import RuntimeEventBus
from app.agent.runtime.types import PlannerResult, RunState, ToolCall


class FakePlanner:
    def __init__(self, actions=None):
        self.calls = []
        self.actions = list(actions or [])

    async def think_and_action_streaming(self, **kwargs):
        self.calls.append(kwargs)
        action = self.actions.pop(0) if self.actions else {"type": "PLAIN_TEXT_REPLY", "answer": "ok"}
        yield {"type": "action", "data": {"action": action}}


class FakeNonStreamingPlanner:
    def __init__(self):
        self.calls = []

    async def think_and_action(self, **kwargs):
        self.calls.append(kwargs)
        return {"thought": "ok", "action": {"type": "PLAIN_TEXT_REPLY", "answer": "ok"}}


class FakeExecutor:
    tool_registry = {}


class FakeContextDiagnostics:
    def log_report(self, **kwargs):
        return None


class FakeContextBuilder:
    board_context = None


class FakeToolCoordinator:
    loop_guard = None

    @staticmethod
    def tool_calls_from_action(action):
        if action.get("type") == "TOOL_CALL":
            return [ToolCall(action.get("tool", ""), action.get("args") or {})]
        return [
            ToolCall(item.get("tool", ""), item.get("args") or {})
            for item in action.get("tools") or []
        ]


@pytest.mark.asyncio
async def test_chart_mode_sends_image_attachment_as_native_content_blocks(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="chart_session", user_query="照这个图生成", mode="chart")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    user_content = planner.calls[0]["user_content"]
    assert user_content[0] == {"type": "text", "text": "user text"}
    assert user_content[1]["type"] == "image"
    assert user_content[1]["source"]["type"] == "base64"
    assert user_content[1]["source"]["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_social_initial_attachments_are_consumed_after_first_planner_call(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="social_session", user_query="参考这张图", mode="social")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}

    first_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]
    second_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert first_events[-1]["type"] == "_planner_done"
    assert second_events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"] is None
    assert planner.calls[1]["attachments"] == []


@pytest.mark.asyncio
async def test_ppt_reference_survives_reading_until_visual_source_is_created(tmp_path):
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner(actions=[
        {
            "type": "TOOL_CALL",
            "tool": "read_file",
            "args": {"path": "app/tools/office/editable_ppt/references/workflow.md"},
        },
        {
            "type": "TOOL_CALL",
            "tool": "manage_editable_ppt",
            "args": {"operation": "create"},
        },
        {
            "type": "TOOL_CALL",
            "tool": "manage_editable_ppt",
            "args": {"operation": "edit_source"},
        },
        {"type": "PLAIN_TEXT_REPLY", "answer": "ok"},
    ])
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[{
            "type": "image",
            "name": "reference.png",
            "local_path": str(image_path),
            "mime_type": "image/png",
        }],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="ppt-session", user_query="复刻这张图", mode="ppt")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    for _ in range(4):
        events = [
            event
            async for event in runtime._run_planner_stream(
                state, context_result, conversation_history=[]
            )
        ]
        assert events[-1]["type"] == "_planner_done"

    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"][1]["type"] == "image"
    assert planner.calls[2]["user_content"][1]["type"] == "image"
    assert planner.calls[3]["user_content"] is None
    assert state.initial_attachments_consumed is True


@pytest.mark.asyncio
async def test_board_initial_attachments_remain_visible_until_drawio_board_created(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=FakeContextBuilder(),
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="board_session", user_query="复刻这个架构图", mode="board")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}

    first_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]
    second_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]
    runtime._capture_drawio_board_context(
        state,
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_board",
                "title": "系统架构图",
                "xml": "<mxfile><diagram>created</diagram></mxfile>",
            },
            "metadata": {"generator": "create_drawio_board"},
        },
    )
    third_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert first_events[-1]["type"] == "_planner_done"
    assert second_events[-1]["type"] == "_planner_done"
    assert third_events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"][1]["type"] == "image"
    assert planner.calls[2]["user_content"] is None
    assert planner.calls[2]["attachments"] == []


@pytest.mark.asyncio
async def test_board_initial_attachments_survive_non_streaming_fallback_before_drawio_board(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakeNonStreamingPlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=FakeContextBuilder(),
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.events = RuntimeEventBus()

    state = RunState(session_id="board_session", user_query="复刻这个架构图", mode="board")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}

    await runtime._fallback_non_streaming(
        state,
        context_result,
        conversation_history=[],
        tool_schemas=[],
        partial=PlannerResult(),
    )
    await runtime._fallback_non_streaming(
        state,
        context_result,
        conversation_history=[],
        tool_schemas=[],
        partial=PlannerResult(),
    )

    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"][1]["type"] == "image"


@pytest.mark.asyncio
async def test_pending_tool_attachments_are_consumed_after_one_planner_call(tmp_path):
    image_path = tmp_path / "tool-output.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="social_session", user_query="继续", mode="social")
    state.pending_attachments.append(
        {"type": "image", "name": "tool-output.png", "local_path": str(image_path), "mime_type": "image/png"}
    )
    context_result = {"system_prompt": "system", "user_conversation": "user text"}

    first_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]
    second_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert first_events[-1]["type"] == "_planner_done"
    assert second_events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"] is None
    assert planner.calls[1]["attachments"] == []
    assert state.pending_attachments == []


@pytest.mark.asyncio
async def test_explicit_tool_image_read_can_reopen_a_consumed_reference(tmp_path):
    image_path = tmp_path / "tool-output.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    attachment = {
        "type": "image",
        "name": "tool-output.png",
        "local_path": str(image_path),
        "mime_type": "image/png",
    }
    planner = FakePlanner(actions=[
        {"type": "TOOL_CALL", "tool": "create_report_chart", "args": {}},
        {"type": "TOOL_CALL", "tool": "create_report_chart", "args": {}},
    ])
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="chart_session", user_query="继续", mode="chart")
    observation = {
        "type": "multimodal_attachment",
        "attachments": [attachment],
    }
    context_result = {"system_prompt": "system", "user_conversation": "user text"}

    runtime._capture_multimodal_attachments(state, observation)
    first_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]
    runtime._capture_multimodal_attachments(state, observation)
    second_events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert first_events[-1]["type"] == "_planner_done"
    assert second_events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["user_content"][1]["type"] == "image"
    assert planner.calls[1]["attachments"][0]["local_path"] == str(image_path)
    assert state.pending_attachments == []


@pytest.mark.asyncio
async def test_assistant_mode_sends_image_attachment_as_native_blocks(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=None,
        attachments=[{"type": "image", "name": "ref.png", "local_path": str(image_path), "mime_type": "image/png"}],
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="assistant_session", user_query="看图", mode="assistant")
    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][0] == {"type": "text", "text": "user text"}
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[0]["user_content"][1]["source"]["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_board_mode_stops_resending_initial_image_after_drawio_board_updates(tmp_path):
    image_path = tmp_path / "stale-board.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=FakeContextBuilder(),
        attachments=[{"type": "image", "name": "stale-board.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(session_id="board_session", user_query="把外部接入改成XX数据接口", mode="board")
    runtime._capture_drawio_board_context(
        state,
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_board",
                "title": "系统架构图",
                "xml": "<mxfile><diagram><mxCell id=\"device_group3\" value=\"XX数据接口\" /></diagram></mxfile>",
            },
            "metadata": {"generator": "create_drawio_board"},
        },
    )

    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"] is None
    assert planner.calls[0]["attachments"] == []


@pytest.mark.asyncio
async def test_chart_mode_does_not_suppress_explicit_image_when_legacy_board_context_exists(tmp_path):
    image_path = tmp_path / "stale-board.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=FakeContextBuilder(),
        attachments=[{"type": "image", "name": "stale-board.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(
        session_id="chart_session",
        user_query="继续调整这个画板",
        mode="chart",
        board_context={
            "artifact_kind": "drawio_board",
            "current_xml": "<mxfile><diagram><mxCell id=\"device_group3\" value=\"XX数据接口\" /></diagram></mxfile>",
        },
    )

    context_result = {"system_prompt": "system", "user_conversation": "user text"}
    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            context_result,
            conversation_history=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"][1]["type"] == "image"
    assert planner.calls[0]["attachments"][0]["name"] == "stale-board.png"


@pytest.mark.asyncio
async def test_board_mode_keeps_current_turn_image_when_board_context_exists(tmp_path):
    image_path = tmp_path / "current-board.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    planner = FakePlanner()
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = AgentRuntimeConfig(
        memory_manager=None,
        planner=planner,
        tool_executor=FakeExecutor(),
        context_builder=FakeContextBuilder(),
        attachments=[{"type": "image", "name": "current-board.png", "local_path": str(image_path), "mime_type": "image/png"}],
        auto_profile="multimodal",
    )
    runtime.planner = planner
    runtime.executor = FakeExecutor()
    runtime.context_diagnostics = FakeContextDiagnostics()
    runtime.tool_coordinator = FakeToolCoordinator()

    state = RunState(
        session_id="board_session",
        user_query="根据截图优化当前画板",
        mode="board",
        board_context={
            "artifact_kind": "drawio_board",
            "current_xml": "<mxfile><diagram><mxCell id=\"node-1\" /></diagram></mxfile>",
        },
    )

    events = [
        event
        async for event in runtime._run_planner_stream(
            state,
            {"system_prompt": "system", "user_conversation": "user text"},
            conversation_history=[],
        )
    ]

    assert events[-1]["type"] == "_planner_done"
    assert planner.calls[0]["user_content"] is not None
    assert planner.calls[0]["attachments"][0]["name"] == "current-board.png"
