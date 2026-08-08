from types import SimpleNamespace

from app.routers.agent import (
    board_agent_instance,
    data_viz_agent_instance,
    ppt_agent_instance,
    is_incompatible_chart_board_session,
    merge_board_execution_context,
    select_agent_instance,
)


def test_chart_and_board_modes_use_distinct_agent_instances():
    chart_agent = select_agent_instance(SimpleNamespace(mode="chart", assistant_mode=None))
    board_agent = select_agent_instance(SimpleNamespace(mode="board", assistant_mode=None))

    assert chart_agent is data_viz_agent_instance
    assert board_agent is board_agent_instance
    assert board_agent is not chart_agent


def test_ppt_mode_uses_its_own_agent_instance():
    ppt_agent = select_agent_instance(SimpleNamespace(mode="ppt", assistant_mode=None))

    assert ppt_agent is ppt_agent_instance
    assert ppt_agent is not data_viz_agent_instance
    assert ppt_agent is not board_agent_instance


def test_chart_and_board_sessions_cannot_be_cross_restored():
    assert is_incompatible_chart_board_session("chart", "board") is True
    assert is_incompatible_chart_board_session("board", "chart") is True
    assert is_incompatible_chart_board_session("board", "board") is False
    assert is_incompatible_chart_board_session("assistant", "board") is False


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
