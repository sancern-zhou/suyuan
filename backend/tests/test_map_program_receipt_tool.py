import asyncio

from app.services.map_program_receipts import map_program_receipt_store
from app.tools.gisctl.map_program_receipt_tool import WaitMapProgramReceiptTool


def test_wait_map_program_receipt_returns_completion_signal_for_rendered_layer():
    map_program_receipt_store.clear()
    try:
        map_program_receipt_store.record(
            "session-a",
            {
                "program_id": "program-a",
                "status": "executed",
                "layers": [
                    {
                        "layer_id": "sim_pollution_sources",
                        "status": "layer_rendered",
                        "feature_count": 10,
                    }
                ],
                "errors": [],
            },
        )

        result = asyncio.run(
            WaitMapProgramReceiptTool().execute(
                session_id="session-a",
                program_id="program-a",
                wait_timeout=0,
            )
        )

        assert result["success"] is True
        assert result["metadata"]["map_control_completed"] is True
        assert result["metadata"]["next_action"] == "answer_user"
        assert result["metadata"]["do_not_repeat_visual_interaction"] is True
        assert result["data"]["map_control_completed"] is True
        assert result["data"]["next_action"] == "answer_user"
        assert result["data"]["do_not_repeat_visual_interaction"] is True
        assert result["data"]["rendered_layers"] == [
            {
                "layer_id": "sim_pollution_sources",
                "status": "layer_rendered",
                "feature_count": 10,
            }
        ]
        assert "请不要再次调用相同 visual_interaction" in result["summary"]
    finally:
        map_program_receipt_store.clear()


def test_wait_map_program_receipt_summary_includes_rendered_layer_data_id():
    map_program_receipt_store.clear()
    try:
        map_program_receipt_store.record(
            "session-a",
            {
                "program_id": "program-a",
                "status": "executed",
                "layers": [
                    {
                        "layer_id": "sanshui_pollution_sources_3km",
                        "status": "layer_rendered",
                        "feature_count": 51,
                        "data_id": "spatial_point_asset:v1:15c312211d3c496bb356f9af9d725605",
                    }
                ],
                "errors": [],
            },
        )

        result = asyncio.run(
            WaitMapProgramReceiptTool().execute(
                session_id="session-a",
                program_id="program-a",
                wait_timeout=0,
            )
        )

        assert result["success"] is True
        assert result["data"]["rendered_layers"] == [
            {
                "layer_id": "sanshui_pollution_sources_3km",
                "status": "layer_rendered",
                "feature_count": 51,
                "data_id": "spatial_point_asset:v1:15c312211d3c496bb356f9af9d725605",
            }
        ]
        assert "data_id=spatial_point_asset:v1:15c312211d3c496bb356f9af9d725605" in result["summary"]
    finally:
        map_program_receipt_store.clear()


def test_wait_map_program_receipt_does_not_complete_for_empty_layer():
    map_program_receipt_store.clear()
    try:
        map_program_receipt_store.record(
            "session-a",
            {
                "program_id": "program-a",
                "status": "executed",
                "layers": [
                    {
                        "layer_id": "sim_pollution_sources",
                        "status": "layer_empty",
                        "feature_count": 0,
                    }
                ],
                "errors": [],
            },
        )

        result = asyncio.run(
            WaitMapProgramReceiptTool().execute(
                session_id="session-a",
                program_id="program-a",
                wait_timeout=0,
            )
        )

        assert result["success"] is True
        assert result["metadata"]["map_control_completed"] is False
        assert result["metadata"]["next_action"] == "inspect_or_fix_map_program"
        assert result["metadata"]["do_not_repeat_visual_interaction"] is False
        assert result["data"]["empty_layers"] == [
            {
                "layer_id": "sim_pollution_sources",
                "status": "layer_empty",
                "feature_count": 0,
            }
        ]
        assert "不要回复已显示成功" in result["summary"]
    finally:
        map_program_receipt_store.clear()
