from pathlib import Path

import pytest

from app.tools.visualization.create_drawio_board.render_tool import _merge_quality_reports
from app.tools.visualization.create_drawio_board.tool import CreateDrawioBoardTool


def test_drawio_tool_schema_exposes_structured_design_spec():
    schema = CreateDrawioBoardTool().get_function_schema()
    design_spec = schema["parameters"]["properties"]["design_spec"]

    assert "architecture" in design_spec["properties"]["diagram_type"]["enum"]
    assert design_spec["properties"]["audience"]["enum"] == ["engineer", "executive", "mixed"]
    assert design_spec["properties"]["detail_level"]["enum"] == [
        "balanced",
        "faithful",
        "simplified",
    ]
    assert "drawio_design_system.md" in schema["description"]


def test_drawio_workflow_routes_new_shared_pattern_guides():
    backend_root = Path(__file__).resolve().parents[4]
    workflow = (backend_root / "app/agent/guides/drawio_board_workflow.md").read_text(
        encoding="utf-8"
    )

    for name in ("sequence", "swimlane", "org_tree", "state_machine", "er_model"):
        relative_path = f"app/agent/guides/drawio_patterns/{name}.md"
        assert relative_path in workflow
        assert (backend_root / relative_path).is_file()


def test_render_report_keeps_design_contract_and_static_taste_warnings():
    report = _merge_quality_reports(
        {
            "status": "warning",
            "design_spec": {"diagram_type": "sequence", "detail_level": "faithful"},
            "theme_tokens": {"accent": "#123ABC"},
            "structural_digest": {"metrics": {"node_count": 6}},
            "warnings": [{"code": "complexity_budget_exceeded"}],
            "metrics": {"accent_node_count": 1},
        },
        {
            "status": "passed",
            "warnings": [],
            "metrics": {"vertex_count": 6},
        },
    )

    assert report["status"] == "warning"
    assert report["design_spec"]["diagram_type"] == "sequence"
    assert report["theme_tokens"]["accent"] == "#123ABC"
    assert report["structural_digest"]["metrics"]["node_count"] == 6
    assert report["warnings"] == [{"code": "complexity_budget_exceeded"}]
    assert report["metrics"] == {"accent_node_count": 1, "vertex_count": 6}


@pytest.mark.asyncio
async def test_drawio_tool_returns_normalized_design_contract_and_digest():
    result = await CreateDrawioBoardTool().execute(
        artifact_id="design_board",
        title="设计规格画板",
        operation="create",
        design_spec={
            "diagram_type": "architecture",
            "story": "展示入口到服务的主链路",
            "audience": "engineer",
            "detail_level": "balanced",
            "canvas_preset": "board-wide",
            "focus_cell_ids": ["api"],
        },
        xml=(
            '<mxCell id="api" value="API" vertex="1" parent="1" '
            'style="rounded=1;fillColor=#EAF2FF;strokeColor=#1677FF">'
            '<mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>'
        ),
    )

    assert result["success"] is True
    assert result["data"]["design_spec"]["diagram_type"] == "architecture"
    assert result["data"]["design_spec"]["focus_cell_ids"] == ["api"]
    assert result["data"]["theme_tokens"]["accent"] == "#1677FF"
    assert result["data"]["structural_digest"]["metrics"]["node_count"] == 1
