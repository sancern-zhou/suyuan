import pytest

from app.agent.runtime.agent_runtime import AgentRuntime
from app.agent.runtime.tool_coordinator import ToolCoordinator
from app.agent.runtime.types import RunState


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    async def execute_tool_with_retry(self, tool_name, tool_args, tool_call_id, iteration=0):
        self.calls.append({
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_call_id": tool_call_id,
            "iteration": iteration,
        })
        return {"success": True, "summary": "ok"}


class ParallelFailureExecutor(RecordingExecutor):
    async def execute_tools_parallel(self, tools, iteration=0):
        self.calls.extend(tools)
        return {
            "success": False,
            "partial_success": False,
            "tool_results": [],
            "failed_tools": [{
                "tool": "create_drawio_board",
                "args": tools[0]["args"],
                "result": {"success": False, "error": "runtime_failure", "summary": "failed"},
            }],
            "summary": "failed",
            "success_count": 0,
            "total_count": 1,
        }


@pytest.mark.asyncio
async def test_drawio_edit_injects_current_xml_from_run_board_context():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="board-session",
        user_query="把标题改掉",
        mode="board",
        board_context={
            "current_xml": "<mxfile><diagram><mxGraphModel><root /></mxGraphModel></diagram></mxfile>",
            "selected_cells": [{"id": "title"}],
        },
    )

    observation, records, _ = await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALL",
            "tool": "create_drawio_board",
            "tool_call_id": "call-edit",
            "args": {
                "operation": "edit",
                "artifact_id": "system_architecture",
                "title": "系统架构图",
                "operations": [{"operation": "update_label", "cell_id": "title", "label": "新标题"}],
            },
        },
    )

    assert observation["success"] is True
    assert executor.calls[0]["tool_args"]["current_xml"].startswith("<mxfile>")
    assert executor.calls[0]["tool_args"]["selected_cells"] == [{"id": "title"}]
    assert records[0]["tool_input"]["current_xml"].startswith("<mxfile>")


@pytest.mark.asyncio
async def test_drawio_edit_without_current_xml_returns_clear_error():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="board-session",
        user_query="把标题改掉",
        mode="board",
        board_context={},
    )

    observation, records, _ = await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALL",
            "tool": "create_drawio_board",
            "tool_call_id": "call-edit",
            "args": {
                "operation": "edit",
                "artifact_id": "system_architecture",
                "title": "系统架构图",
                "operations": [{"operation": "update_label", "cell_id": "title", "label": "新标题"}],
            },
        },
    )

    assert observation["success"] is False
    assert observation["error"] == "missing_current_xml_for_edit"
    assert observation["metadata"]["tool_name"] == "create_drawio_board"
    assert "current_xml" in observation["summary"]
    assert records[0]["is_error"] is True
    assert executor.calls == []

@pytest.mark.asyncio
async def test_board_runtime_rejects_tool_outside_mode_whitelist():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(session_id="board-session", user_query="执行命令", mode="board")

    observation, records, _ = await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALL",
            "tool": "bash",
            "tool_call_id": "call-bash",
            "args": {"command": "echo forbidden"},
        },
    )

    assert observation["success"] is False
    assert observation["data"]["error_code"] == "tool_not_allowed_for_mode"
    assert records[0]["is_error"] is True
    assert executor.calls == []


@pytest.mark.asyncio
async def test_parallel_board_failure_preserves_tool_identity():
    executor = ParallelFailureExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(session_id="board-session", user_query="创建画板", mode="board")

    observation, _, _ = await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALLS",
            "tools": [{
                "tool": "create_drawio_board",
                "tool_call_id": "call-board",
                "args": {"operation": "create", "artifact_id": "board", "title": "Board", "xml": "<mxCell/>"},
            }],
        },
    )

    result = observation["tool_results"][0]["result"]
    assert result["metadata"]["tool_name"] == "create_drawio_board"


def test_board_tools_receive_authoritative_internal_version_context():
    coordinator = ToolCoordinator(tool_executor=RecordingExecutor())
    state = RunState(
        session_id="board-session-versioned",
        user_query="创建并检查画板",
        mode="board",
        board_context={
            "board_id": "board-db",
            "revision": 7,
            "candidate_version_id": "candidate-7",
        },
    )

    create_args, create_error = coordinator.prepare_tool_input_for_state(
        "create_drawio_board",
        {"operation": "create", "artifact_id": "logical", "title": "Board", "xml": "<mxCell />"},
        state,
    )
    accept_args, accept_error = coordinator.prepare_tool_input_for_state(
        "accept_drawio_board_candidate",
        {"candidate_version_id": "candidate-7"},
        state,
    )
    render_args, render_error = coordinator.prepare_tool_input_for_state(
        "render_drawio_board_candidate",
        {"candidate_version_id": "candidate-7"},
        state,
    )

    assert create_error is None
    assert create_args["_session_id"] == state.session_id
    assert create_args["_agent_run_id"] == state.run_id
    assert create_args["_board_id"] == "board-db"
    assert create_args["_base_revision"] == 7
    assert accept_error is None
    assert accept_args["_board_id"] == "board-db"
    assert accept_args["_expected_board_revision"] == 7
    assert accept_args["_agent_run_id"] == state.run_id
    assert render_error is None
    assert render_args["_session_id"] == state.session_id
    assert render_args["_board_id"] == "board-db"
    assert render_args["_agent_run_id"] == state.run_id


def test_runtime_tracks_pending_visual_review_until_candidate_is_accepted(tmp_path):
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = type("Config", (), {"attachments": None, "context_builder": None})()
    state = RunState(session_id="board-review", user_query="创建画板", mode="board")
    xml_path = tmp_path / "candidate.drawio"
    xml_path.write_text("<mxfile>candidate</mxfile>", encoding="utf-8")

    runtime._capture_drawio_board_context(state, {
        "success": True,
        "data": {
            "artifact_kind": "drawio_board",
            "board_id": "board-db",
            "candidate_version_id": "candidate-1",
            "revision": 0,
            "requires_visual_review": True,
            "quality_status": "warning",
            "xml_ref": {"local_path": str(xml_path)},
        },
        "metadata": {"tool_name": "create_drawio_board"},
    })

    assert state.pending_board_candidate_id == "candidate-1"
    assert state.board_quality_repair_count == 0
    assert state.board_context["candidate_version_id"] == "candidate-1"

    runtime._capture_drawio_board_context(state, {
        "success": True,
        "data": {
            "artifact_kind": "drawio_board",
            "board_id": "board-db",
            "current_version_id": "candidate-1",
            "revision": 1,
            "candidate_accepted": True,
            "requires_visual_review": False,
            "xml_ref": {"local_path": str(xml_path)},
        },
        "metadata": {"tool_name": "accept_drawio_board_candidate"},
    })

    assert state.pending_board_candidate_id is None
    assert state.board_context["current_version_id"] == "candidate-1"
    assert state.board_context["revision"] == 1


def test_runtime_does_not_force_visual_review_or_quality_repair_before_final_answer():
    runtime = AgentRuntime.__new__(AgentRuntime)
    pending = RunState(session_id="board-pending", user_query="创建", mode="board")
    pending.pending_board_candidate_id = "candidate-1"
    accepted = RunState(session_id="board-accepted", user_query="创建", mode="board")
    rejected = RunState(
        session_id="board-rejected",
        user_query="创建",
        mode="board",
        board_context={"lifecycle_status": "rejected", "candidate_version_id": "candidate-bad"},
    )

    assert runtime._board_completion_block_reason(pending) is None
    assert runtime._board_completion_block_reason(rejected) is None
    assert runtime._board_completion_block_reason(accepted) is None


def test_runtime_does_not_enforce_a_visual_quality_repair_limit(tmp_path):
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = type("Config", (), {"attachments": None, "context_builder": None})()
    state = RunState(session_id="board-review", user_query="创建画板", mode="board")

    for index in range(3):
        xml_path = tmp_path / f"candidate-{index}.drawio"
        xml_path.write_text(f"<mxfile>candidate-{index}</mxfile>", encoding="utf-8")
        runtime._capture_drawio_board_context(state, {
            "success": False,
            "data": {
                "artifact_kind": "drawio_board",
                "board_id": "board-db",
                "candidate_version_id": f"candidate-{index}",
                "lifecycle_status": "rejected",
                "xml_ref": {"local_path": str(xml_path)},
            },
        })

    assert state.pending_board_candidate_id is None
    assert state.board_quality_repair_count == 2

    _, error = ToolCoordinator(RecordingExecutor()).prepare_tool_input_for_state(
        "create_drawio_board",
        {"operation": "edit", "artifact_id": "board-db"},
        state,
    )
    assert error is None


@pytest.mark.asyncio
async def test_drawio_edit_ignores_llm_supplied_current_xml_and_uses_board_context():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="board-session",
        user_query="把标题改掉",
        mode="board",
        board_context={
            "current_xml": "<mxfile><diagram>authoritative</diagram></mxfile>",
        },
    )

    await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALL",
            "tool": "create_drawio_board",
            "tool_call_id": "call-edit",
            "args": {
                "operation": "edit",
                "artifact_id": "system_architecture",
                "title": "系统架构图",
                "current_xml": "<mxfile><diagram>llm supplied stale xml</diagram></mxfile>",
                "operations": [{"operation": "update_label", "cell_id": "title", "label": "新标题"}],
            },
        },
    )

    assert executor.calls[0]["tool_args"]["current_xml"] == "<mxfile><diagram>authoritative</diagram></mxfile>"


@pytest.mark.asyncio
async def test_drawio_edit_rejects_llm_supplied_current_xml_without_board_context():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="board-session",
        user_query="把标题改掉",
        mode="board",
        board_context=None,
    )

    observation, _, _ = await coordinator.execute_legacy_action(
        state,
        {
            "type": "TOOL_CALL",
            "tool": "create_drawio_board",
            "tool_call_id": "call-edit",
            "args": {
                "operation": "edit",
                "artifact_id": "system_architecture",
                "title": "系统架构图",
                "current_xml": "<mxfile><diagram>llm supplied xml</diagram></mxfile>",
                "operations": [{"operation": "update_label", "cell_id": "title", "label": "新标题"}],
            },
        },
    )

    assert observation["success"] is False
    assert observation["error"] == "missing_current_xml_for_edit"
    assert executor.calls == []


def test_runtime_captures_drawio_result_as_same_run_board_context(tmp_path):
    runtime = AgentRuntime.__new__(AgentRuntime)
    state = RunState(
        session_id="board-session",
        user_query="创建后继续修改",
        mode="board",
        board_context=None,
    )
    stored_xml_path = tmp_path / "created.drawio"
    stored_xml_path.write_text("<mxfile><diagram>created</diagram></mxfile>", encoding="utf-8")

    runtime._capture_drawio_board_context(
        state,
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_diagram",
                "title": "系统架构图",
                "xml_ref": {"local_path": str(stored_xml_path)},
            },
            "metadata": {"tool_name": "create_drawio_board"},
        },
    )

    assert state.board_context["current_xml"] == "<mxfile><diagram>created</diagram></mxfile>"
    assert state.board_context["artifact_id"] == "architecture_diagram"
    assert state.board_context["title"] == "系统架构图"


def test_runtime_captures_drawio_result_into_context_builder_for_next_iteration(tmp_path):
    class ContextBuilder:
        board_context = None

    class Config:
        context_builder = ContextBuilder()

    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = Config()
    state = RunState(
        session_id="board-session",
        user_query="创建后继续修改",
        mode="board",
        board_context=None,
    )
    stored_xml_path = tmp_path / "edited.drawio"
    stored_xml_path.write_text("<mxfile><diagram>edited</diagram></mxfile>", encoding="utf-8")

    runtime._capture_drawio_board_context(
        state,
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_diagram",
                "title": "系统架构图",
                "xml_ref": {"local_path": str(stored_xml_path)},
            },
            "metadata": {"tool_name": "create_drawio_board"},
        },
    )

    assert runtime.config.context_builder.board_context == state.board_context
    assert runtime.config.context_builder.board_context["current_xml"] == "<mxfile><diagram>edited</diagram></mxfile>"


def test_drawio_edit_can_use_xml_captured_from_previous_same_run_create_result(tmp_path):
    runtime = AgentRuntime.__new__(AgentRuntime)
    state = RunState(
        session_id="board-session",
        user_query="创建后继续修改",
        mode="board",
        board_context=None,
    )
    stored_xml_path = tmp_path / "created.drawio"
    stored_xml_path.write_text("<mxfile><diagram>created</diagram></mxfile>", encoding="utf-8")

    runtime._capture_drawio_board_context(
        state,
        {
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_diagram",
                "xml_ref": {"local_path": str(stored_xml_path)},
            },
        },
    )

    coordinator = ToolCoordinator(RecordingExecutor())
    tool_input, preparation_error = coordinator.prepare_tool_input_for_state(
        "create_drawio_board",
        {
            "operation": "edit",
            "artifact_id": "architecture_diagram",
            "operations": [{"operation": "update_label", "cell_id": "title", "label": "新标题"}],
        },
        state,
    )

    assert preparation_error is None
    assert tool_input["current_xml"] == "<mxfile><diagram>created</diagram></mxfile>"
