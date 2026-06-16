from pathlib import Path

import pytest

from app.tools.visualization.create_drawio_board.tool import CreateDrawioBoardTool
from app.agent.tool_adapter import _standardize_tool_result


def test_create_drawio_board_schema_points_to_required_guides():
    schema = CreateDrawioBoardTool().get_function_schema()
    description = schema["description"]

    assert "app/agent/guides/drawio_board_workflow.md" in description
    assert "app/agent/guides/drawio_xml_rules.md" in description
    assert "app/agent/guides/drawio_edit_policy.md" in description
    assert "app/agent/guides/drawio_design_patterns.md" not in description
    assert "before first use" in description
    assert "create_diagram_artifact" in description


def test_drawio_workflow_routes_to_specialized_design_guides():
    backend_root = Path(__file__).resolve().parents[4]
    workflow_text = (backend_root / "app/agent/guides/drawio_board_workflow.md").read_text(encoding="utf-8")

    expected_guides = [
        "app/agent/guides/drawio_patterns/architecture.md",
        "app/agent/guides/drawio_patterns/process_flow.md",
        "app/agent/guides/drawio_patterns/data_flow.md",
        "app/agent/guides/drawio_patterns/decision_tree.md",
        "app/agent/guides/drawio_patterns/layered_system.md",
        "app/agent/guides/drawio_patterns/timeline.md",
        "app/agent/guides/drawio_patterns/comparison_matrix.md",
    ]
    for guide_path in expected_guides:
        assert guide_path in workflow_text
        assert (backend_root / guide_path).exists()


def test_specialized_design_guides_define_professional_constraints():
    backend_root = Path(__file__).resolve().parents[4]
    architecture = (backend_root / "app/agent/guides/drawio_patterns/architecture.md").read_text(encoding="utf-8")
    process_flow = (backend_root / "app/agent/guides/drawio_patterns/process_flow.md").read_text(encoding="utf-8")
    data_flow = (backend_root / "app/agent/guides/drawio_patterns/data_flow.md").read_text(encoding="utf-8")

    assert "C4" in architecture
    assert "层级" in architecture
    assert "同一层" in architecture
    assert "shape" in architecture
    assert "判断节点" in process_flow
    assert "异常路径" in process_flow
    assert "数据源" in data_flow
    assert "批处理" in data_flow


@pytest.mark.asyncio
async def test_create_drawio_board_returns_editable_board_payload():
    tool = CreateDrawioBoardTool()

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="create",
        xml='<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>',
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["data"]["artifact_kind"] == "drawio_board"
    assert result["data"]["artifact_id"] == "board_a"
    assert result["data"]["board_id"] == "board_a"
    assert result["data"]["title"] == "系统画板"
    assert result["data"]["version"] == 1
    assert "xml" not in result["data"]
    assert result["data"]["xml_length"] > 0
    assert result["data"]["xml_ref"]["local_path"]
    assert result["data"]["xml_ref"]["read_url"].startswith("/api/file/")
    stored_xml = Path(result["data"]["xml_ref"]["local_path"]).read_text(encoding="utf-8")
    assert "<mxfile" in stored_xml
    assert result["metadata"]["generator"] == "create_drawio_board"
    assert "无需再次加载参考图片" in result["summary"]
    assert result["metadata"]["schema_version"] == "v1.0"
    assert result["metadata"]["panel"] == "board"
    assert result["metadata"]["editable"] is True
    assert "visuals" not in result


@pytest.mark.asyncio
async def test_create_drawio_board_standardization_preserves_externalized_xml_ref():
    tool = CreateDrawioBoardTool()

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="create",
        xml='<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>',
    )

    standardized = _standardize_tool_result("create_drawio_board", result, 0.01)

    assert standardized["success"] is True
    assert standardized["data"]["artifact_kind"] == "drawio_board"
    assert standardized["data"]["board_id"] == "board_a"
    assert "xml" not in standardized["data"]
    assert standardized["data"]["xml_ref"]["local_path"]
    assert standardized["refs"]["artifacts"][0]["local_path"] == standardized["data"]["xml_ref"]["local_path"]
    assert standardized["metadata"]["generator"] == "create_drawio_board"


@pytest.mark.asyncio
async def test_create_drawio_board_edit_applies_operations_to_current_xml():
    tool = CreateDrawioBoardTool()
    current_xml = """
    <mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    """

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="edit",
        current_xml=current_xml,
        operations=[
            {
                "operation": "update",
                "cell_id": "2",
                "new_xml": '<mxCell id="2" value="Auth API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="140" height="60" as="geometry"/></mxCell>',
            }
        ],
    )

    assert result["success"] is True
    assert "xml" not in result["data"]
    stored_xml = Path(result["data"]["xml_ref"]["local_path"]).read_text(encoding="utf-8")
    assert "Auth API" in stored_xml
    assert result["data"]["operation"] == "edit"
    assert result["data"]["changed"] is True
    assert result["data"]["changed_cells"] == ["2"]
    assert "已应用 1 个编辑操作" in result["summary"]
    assert "2" in result["summary"]


@pytest.mark.asyncio
async def test_create_drawio_board_edit_reports_noop_when_labels_already_match():
    tool = CreateDrawioBoardTool()
    current_xml = """
    <mxCell id="2" value="Auth API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    """

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="edit",
        current_xml=current_xml,
        operations=[
            {"operation": "update_label", "cell_id": "2", "label": "Auth API"},
        ],
    )

    assert result["success"] is True
    assert result["data"]["operation"] == "edit"
    assert result["data"]["changed"] is False
    assert result["data"]["changed_cells"] == []
    assert "未产生实际变更" in result["summary"]


@pytest.mark.asyncio
async def test_create_drawio_board_edit_can_target_selected_cells():
    tool = CreateDrawioBoardTool()
    current_xml = """
    <mxCell id="svc_api" value="API" style="rounded=1;fillColor=#dae8fc;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    """

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="edit",
        current_xml=current_xml,
        selected_cells=[{"id": "svc_api"}],
        operations=[
            {"operation": "update_label", "target": "selected", "label": "认证服务"},
            {"operation": "move_resize", "target": "selected", "geometry": {"width": 180, "height": 80}},
        ],
    )

    assert result["success"] is True
    assert "xml" not in result["data"]
    stored_xml = Path(result["data"]["xml_ref"]["local_path"]).read_text(encoding="utf-8")
    assert "认证服务" in stored_xml
    assert 'width="180"' in stored_xml
