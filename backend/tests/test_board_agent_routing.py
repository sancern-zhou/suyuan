from types import SimpleNamespace

from app.api.agent import (
    board_agent_instance,
    data_viz_agent_instance,
    ppt_agent_instance,
    merge_board_execution_context,
    select_agent_instance,
)


def test_ppt_mode_uses_its_own_agent_instance():
    ppt_agent = select_agent_instance(SimpleNamespace(mode="ppt", assistant_mode=None))

    assert ppt_agent is ppt_agent_instance
    assert ppt_agent is not data_viz_agent_instance
    assert ppt_agent is not board_agent_instance


def test_failed_board_execution_is_preserved_for_the_next_turn():
    context = {"current_xml": "<mxfile/>", "version": 3}
    result = {
        "success": False,
        "data": {
            "error_code": "operation_cell_id_required",
            "operation_index": 1,
            "field": "cell_id",
            "retryable": True,
        },
        "metadata": {"tool_name": "create_drawio_board"},
    }

    merged = merge_board_execution_context(
        context,
        result,
    )

    assert merged["current_xml"] == "<mxfile/>"
    assert merged["last_execution"]["success"] is False
    assert merged["last_execution"]["error_code"] == "operation_cell_id_required"
    assert merged["last_execution"]["operation_index"] == 1
    assert "last_run_contract" not in merged
