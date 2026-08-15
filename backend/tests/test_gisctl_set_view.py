from __future__ import annotations

from app.tools.gisctl.tool import execute_gisctl


def test_set_view_accepts_target_without_name():
    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "set-view",
            "target": "广州",
            "zoom": 12,
        }
    )

    assert result["success"] is True
    assert result["data"]["map_program"]["intent"] == "Set map view to 广州"
    assert result["data"]["map_program"]["state"]["view"] == {
        "center": [113.2644, 23.1291],
        "zoom": 12,
    }
