from app.agent.memory.session_memory import (
    SessionMemory,
    _prepare_tool_input_for_history,
    _prepare_tool_result_for_history,
)


def test_drawio_create_tool_input_history_preserves_xml_until_next_user_turn():
    large_xml = "<mxfile>" + ("x" * 12000) + "</mxfile>"

    history_input = _prepare_tool_input_for_history(
        "create_drawio_board",
        {
            "operation": "create",
            "artifact_id": "architecture_001",
            "title": "系统架构图",
            "xml": large_xml,
        },
    )

    assert history_input["operation"] == "create"
    assert history_input["artifact_id"] == "architecture_001"
    assert history_input["xml"] == large_xml


def test_drawio_edit_tool_input_history_omits_injected_current_xml():
    large_xml = "<mxfile>" + ("x" * 12000) + "</mxfile>"

    history_input = _prepare_tool_input_for_history(
        "create_drawio_board",
        {
            "operation": "edit",
            "artifact_id": "architecture_001",
            "title": "系统架构图",
            "current_xml": large_xml,
            "xml": large_xml,
            "operations": [{"operation": "update_label", "cell_id": "a", "label": "A"}],
            "selected_cells": [{"id": "a", "xml": large_xml}],
        },
    )

    assert history_input["operation"] == "edit"
    assert history_input["artifact_id"] == "architecture_001"
    assert "current_xml" not in history_input
    assert "xml" not in history_input
    assert history_input["operations"] == [{"operation": "update_label", "cell_id": "a", "label": "A"}]
    assert history_input["selected_cells"] == [{"id": "a"}]


def test_drawio_create_tool_result_history_keeps_board_metadata():
    large_xml = "<mxfile>" + ("x" * 12000) + "</mxfile>"

    history_result = _prepare_tool_result_for_history(
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_001",
                "board_id": "architecture_001",
                "title": "系统架构图",
                "xml": large_xml,
                "version": 1,
            },
            "metadata": {"generator": "create_drawio_board"},
            "summary": "交互式画板已生成：系统架构图",
        }
    )

    assert history_result["success"] is True
    assert history_result["data"]["artifact_kind"] == "drawio_board"
    assert history_result["data"]["artifact_id"] == "architecture_001"
    assert "xml" in history_result["data"]


def test_drawio_edit_result_history_keeps_tool_metadata_without_xml():
    history_result = _prepare_tool_result_for_history(
        {
            "status": "success",
            "success": True,
            "data": {
                "artifact_kind": "drawio_board",
                "artifact_id": "architecture_001",
                "board_id": "architecture_001",
                "title": "系统架构图",
                "version": 2,
                "operation": "edit",
                "changed": True,
                "applied_operations": 1,
                "xml_omitted": True,
                "xml_length": 42,
            },
            "metadata": {"generator": "create_drawio_board"},
            "summary": "画板编辑完成：系统架构图。已应用 1 个编辑操作。",
        }
    )

    assert history_result["data"]["operation"] == "edit"
    assert "xml" not in history_result["data"]
    assert history_result["data"]["xml_omitted"] is True


def test_drawio_xml_is_compacted_when_next_user_turn_starts(tmp_path):
    large_xml = "<mxfile>" + ("x" * 12000) + "</mxfile>"
    session = SessionMemory(
        session_id="chart-session",
        base_dir=str(tmp_path),
        use_llm_compression=False,
    )

    session.add_streaming_tool_results([
        {
            "tool_name": "create_drawio_board",
            "tool_use_id": "call_drawio",
            "tool_input": {
                "operation": "create",
                "artifact_id": "architecture_001",
                "title": "系统架构图",
                "xml": large_xml,
            },
            "result": {
                "status": "success",
                "success": True,
                "data": {
                    "artifact_kind": "drawio_board",
                    "artifact_id": "architecture_001",
                    "title": "系统架构图",
                    "xml": large_xml,
                },
                "metadata": {"generator": "create_drawio_board"},
                "summary": "交互式画板已生成：系统架构图",
            },
            "is_error": False,
        }
    ])

    same_turn_messages = session.get_messages_for_llm()
    assert same_turn_messages[0]["content"][0]["input"]["xml"] == large_xml
    assert '"artifact_kind": "drawio_board"' in same_turn_messages[1]["content"][0]["content"]

    session.add_user_message("继续修改画板")

    next_turn_messages = session.get_messages_for_llm()
    assert "xml" not in next_turn_messages[0]["content"][0]["input"]
    assert "xml_omitted" not in next_turn_messages[0]["content"][0]["input"]
    result_payload = next_turn_messages[1]["content"][0]["content"]
    assert large_xml not in result_payload
    assert '"xml_omitted": true' in result_payload
