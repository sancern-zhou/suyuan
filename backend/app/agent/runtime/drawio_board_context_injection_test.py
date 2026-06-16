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


@pytest.mark.asyncio
async def test_drawio_edit_injects_current_xml_from_run_board_context():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="chart-session",
        user_query="把标题改掉",
        mode="chart",
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
        session_id="chart-session",
        user_query="把标题改掉",
        mode="chart",
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
    assert "current_xml" in observation["summary"]
    assert records[0]["is_error"] is True
    assert executor.calls == []


@pytest.mark.asyncio
async def test_drawio_edit_ignores_llm_supplied_current_xml_and_uses_board_context():
    executor = RecordingExecutor()
    coordinator = ToolCoordinator(executor)
    state = RunState(
        session_id="chart-session",
        user_query="把标题改掉",
        mode="chart",
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
        session_id="chart-session",
        user_query="把标题改掉",
        mode="chart",
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
        session_id="chart-session",
        user_query="创建后继续修改",
        mode="chart",
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
        session_id="chart-session",
        user_query="创建后继续修改",
        mode="chart",
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
        session_id="chart-session",
        user_query="创建后继续修改",
        mode="chart",
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
