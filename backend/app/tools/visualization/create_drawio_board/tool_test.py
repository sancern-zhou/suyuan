from pathlib import Path
from types import SimpleNamespace

import pytest

import app.tools.visualization.create_drawio_board.tool as drawio_tool_module
from app.agent.tool_adapter import _standardize_tool_result, convert_openai_to_anthropic_schema
from app.boards.quality import BoardQualityFailed, BoardRenderFailed
from app.tools.visualization.create_drawio_board.tool import CreateDrawioBoardTool


class _ForbiddenQualityService:
    calls = 0

    async def inspect(self, xml, *, board_id, candidate_id):
        self.calls += 1
        raise AssertionError("create_drawio_board must not render screenshots")


async def _candidate_persister(**payload):
    assert payload["session_id"] == "board_session_tool"
    assert payload["base_revision"] == 0
    assert payload["agent_run_id"] == "run-tool"
    assert payload["quality_status"] == "pending"
    assert payload["screenshot_ref"] is None
    assert payload["quality_report"]["render_status"] == "pending"
    return {
        "board_id": "db-board-id",
        "candidate_version_id": "candidate-version-id",
        "version_number": 1,
        "revision": 0,
        "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
    }


class _FailedQualityService:
    async def inspect(self, xml, *, board_id, candidate_id):
        raise BoardQualityFailed({
            "status": "failed",
            "errors": [{"code": "unknown_edge_endpoint"}],
            "warnings": [],
        })


class _FailedRenderService:
    async def inspect(self, xml, *, board_id, candidate_id):
        raise BoardRenderFailed(
            "renderer unavailable",
            report={"status": "warning", "errors": [], "warnings": [{"code": "orphan_node"}]},
        )


def test_create_drawio_board_schema_points_to_required_guides():
    schema = CreateDrawioBoardTool().get_function_schema()
    description = schema["description"]

    assert "app/agent/guides/drawio_board_workflow.md" in description
    assert "app/agent/guides/drawio_xml_rules.md" in description
    assert "app/agent/guides/drawio_edit_policy.md" in description
    assert "app/agent/guides/drawio_design_patterns.md" not in description
    assert "before first use" in description
    # create_diagram_artifact 已废弃，现在使用画板模式
    assert "board" in description.lower() or "drawio" in description.lower()


def test_create_drawio_board_schema_requires_progressive_pattern_guide_reading():
    description = CreateDrawioBoardTool().get_function_schema()["description"]

    assert "classify the requested diagram type" in description
    assert "read only the one or two matching drawio_patterns guides" in description
    assert "never read every pattern guide" in description
    assert "before calling this tool" in description
    assert "Minor text, color, font, size, or position-only edits may skip pattern guides" in description


def test_create_drawio_board_schema_describes_connect_contract():
    schema = CreateDrawioBoardTool().get_function_schema()
    operations_schema = schema["parameters"]["properties"]["operations"]
    operation_variants = operations_schema["items"]["oneOf"]
    connect_schema = next(
        variant
        for variant in operation_variants
        if variant["properties"]["operation"].get("const") == "connect"
    )

    assert set(connect_schema["required"]) == {
        "operation",
        "cell_id",
        "source_cell_id",
        "target_cell_id",
    }
    assert "unique ID for the new edge" in connect_schema["properties"]["cell_id"]["description"]
    assert connect_schema["examples"] == [{
        "operation": "connect",
        "cell_id": "edge_alert_to_monitoring",
        "source_cell_id": "alert_decision",
        "target_cell_id": "fetch_monitoring",
    }]

    anthropic_schema = convert_openai_to_anthropic_schema(schema)
    emitted_items = anthropic_schema["input_schema"]["properties"]["operations"]["items"]
    assert emitted_items["oneOf"] == operation_variants


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


def test_drawio_guides_keep_routing_degradation_non_blocking():
    backend_root = Path(__file__).resolve().parents[4]
    workflow = (backend_root / "app/agent/guides/drawio_board_workflow.md").read_text(encoding="utf-8")
    xml_rules = (backend_root / "app/agent/guides/drawio_xml_rules.md").read_text(encoding="utf-8")

    assert "routing_status=partial" in workflow
    assert "仍可继续生成和预览" in workflow
    assert "不构成系统级阻断" in workflow
    assert "无法避让的连线会保留原始路径" in xml_rules
    assert "明确 warning" in xml_rules


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
async def test_create_drawio_board_returns_pending_candidate_without_rendering():
    quality_service = _ForbiddenQualityService()
    tool = CreateDrawioBoardTool(
        quality_service=quality_service,
        candidate_persister=_candidate_persister,
    )

    result = await tool.execute(
        artifact_id="board_a",
        title="系统画板",
        operation="create",
        xml='<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>',
        _session_id="board_session_tool",
        _base_revision=0,
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert quality_service.calls == 0
    assert "type" not in result
    assert "attachments" not in result
    assert result["data"]["board_id"] == "db-board-id"
    assert result["data"]["candidate_version_id"] == "candidate-version-id"
    assert result["data"]["requires_visual_review"] is True
    assert result["data"]["preview_candidate"] is True
    assert result["data"]["render_status"] == "pending"
    assert result["data"]["quality_status"] == "pending"
    assert result["data"]["quality_report"]["render_status"] == "pending"
    assert "建议调用 render_drawio_board_candidate" in result["summary"]


@pytest.mark.asyncio
async def test_ai_candidate_routes_edge_around_intermediate_node_before_persisting():
    captured = {}

    async def capture_candidate(**payload):
        captured.update(payload)
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "candidate-version-id",
            "version_number": 1,
            "revision": 0,
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        }

    result = await CreateDrawioBoardTool(candidate_persister=capture_candidate).execute(
        artifact_id="board_with_obstacle",
        title="自动避让画板",
        operation="create",
        xml="""
        <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="blocker" value="中间节点" vertex="1" parent="1"><mxGeometry x="150" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="c" value="C" vertex="1" parent="1"><mxGeometry x="300" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="edge_a_c" value="" edge="1" parent="1" source="a" target="c" style="edgeStyle=orthogonalEdgeStyle;html=1;"><mxGeometry relative="1" as="geometry"/></mxCell>
        """,
        _session_id="board_session_tool",
        _base_revision=0,
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert "edgeStyle=segmentEdgeStyle" in captured["xml"]
    assert '<Array as="points">' in captured["xml"]
    assert captured["quality_report"]["metrics"]["rerouted_edge_count"] == 1
    assert captured["quality_report"]["metrics"]["edge_vertex_intersection_count"] == 0


@pytest.mark.asyncio
async def test_ai_candidate_keeps_excessive_edge_crossings_as_warning(monkeypatch):
    xml = '<mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>'
    monkeypatch.setattr(
        drawio_tool_module,
        "route_drawio_candidate",
        lambda _xml: SimpleNamespace(
            xml=_xml,
            metrics={
                "edge_count": 4,
                "degraded_edge_count": 0,
                "edge_edge_crossing_count": 4,
                "remaining_intersection_count": 0,
            },
            status="applied",
            issues=(),
        ),
    )

    async def capture_candidate(**_payload):
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "candidate-version-id",
            "version_number": 1,
            "revision": 0,
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        }

    result = await CreateDrawioBoardTool(candidate_persister=capture_candidate).execute(
        artifact_id="crowded_board",
        title="拥挤画板",
        operation="create",
        xml=xml,
        _session_id="board_session_tool",
        _base_revision=0,
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert result["data"]["routing_metrics"]["edge_edge_crossing_count"] == 4
    assert result["data"]["quality_report"]["status"] == "warning"


@pytest.mark.asyncio
async def test_non_candidate_create_does_not_apply_automatic_routing():
    result = await CreateDrawioBoardTool().execute(
        artifact_id="manual_compatible_board",
        title="非候选画板",
        operation="create",
        xml="""
        <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="blocker" value="中间节点" vertex="1" parent="1"><mxGeometry x="150" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="c" value="C" vertex="1" parent="1"><mxGeometry x="300" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="edge_a_c" edge="1" parent="1" source="a" target="c" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
        """,
    )

    stored_xml = Path(result["data"]["xml_ref"]["local_path"]).read_text(encoding="utf-8")
    assert "edgeStyle=orthogonalEdgeStyle" in stored_xml
    assert "edgeStyle=segmentEdgeStyle" not in stored_xml
    assert '<Array as="points">' not in stored_xml


@pytest.mark.asyncio
async def test_unroutable_ai_candidate_is_persisted_with_routing_warning():
    persisted = {}

    async def capture_candidate(**payload):
        persisted.update(payload)
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "candidate-version-id",
            "version_number": 1,
            "revision": 0,
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        }

    result = await CreateDrawioBoardTool(candidate_persister=capture_candidate).execute(
        artifact_id="blocked_board",
        title="无法避让画板",
        operation="create",
        xml="""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="right_wall" value="右墙" vertex="1" parent="1"><mxGeometry x="85" y="-200" width="100" height="440" as="geometry"/></mxCell>
        <mxCell id="left_wall" value="左墙" vertex="1" parent="1"><mxGeometry x="-105" y="-200" width="100" height="440" as="geometry"/></mxCell>
        <mxCell id="top_wall" value="上墙" vertex="1" parent="1"><mxGeometry x="-200" y="-105" width="480" height="100" as="geometry"/></mxCell>
        <mxCell id="bottom_wall" value="下墙" vertex="1" parent="1"><mxGeometry x="-200" y="45" width="480" height="100" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
        """,
        _session_id="board_session_tool",
        _agent_run_id="run-tool",
    )

    assert persisted["xml"]
    assert result["success"] is True
    assert result["data"]["routing_status"] == "partial"
    assert result["data"]["routing_metrics"]["degraded_edge_count"] == 1
    assert result["data"]["quality_report"]["status"] == "warning"


@pytest.mark.asyncio
async def test_ai_candidate_edit_reports_edge_changed_by_automatic_routing():
    captured = {}

    async def capture_candidate(**payload):
        captured.update(payload)
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "candidate-version-id",
            "version_number": 2,
            "revision": 1,
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        }

    current_xml = """
    <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
    <mxCell id="blocker" value="中间节点" vertex="1" parent="1"><mxGeometry x="150" y="0" width="100" height="60" as="geometry"/></mxCell>
    <mxCell id="c" value="C" vertex="1" parent="1"><mxGeometry x="300" y="0" width="100" height="60" as="geometry"/></mxCell>
    <mxCell id="edge_a_c" edge="1" parent="1" source="a" target="c" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """
    result = await CreateDrawioBoardTool(candidate_persister=capture_candidate).execute(
        artifact_id="edited_board",
        title="编辑候选",
        operation="edit",
        current_xml=current_xml,
        operations=[{"operation": "update_label", "cell_id": "a", "label": "A"}],
        _session_id="board_session_tool",
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert result["data"]["changed"] is True
    assert "edge_a_c" in result["data"]["changed_cells"]
    assert "edgeStyle=segmentEdgeStyle" in captured["xml"]


@pytest.mark.asyncio
async def test_unexpected_candidate_routing_error_falls_back_and_persists(monkeypatch):
    def fail_routing(xml):
        raise RuntimeError("unexpected router failure")

    captured = {}

    async def capture_candidate(**payload):
        captured.update(payload)
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "candidate-version-id",
            "version_number": 1,
            "revision": 0,
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        }

    monkeypatch.setattr(drawio_tool_module, "route_drawio_candidate", fail_routing)
    result = await CreateDrawioBoardTool(candidate_persister=capture_candidate).execute(
        artifact_id="router_failure",
        title="路由失败",
        operation="create",
        xml='''
        <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="b" value="B" vertex="1" parent="1"><mxGeometry x="240" y="0" width="100" height="60" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="a" target="b"><mxGeometry relative="1" as="geometry"/></mxCell>
        ''',
        _session_id="board_session_tool",
        _agent_run_id="run-tool",
    )

    assert captured["xml"].startswith("<mxfile")
    assert result["success"] is True
    assert result["data"]["routing_status"] == "fallback"
    assert result["data"]["routing_metrics"] == {}
    assert result["data"]["routing_issue"]["cause"] == "router_internal_error"
    assert result["data"]["routing_issue"]["preserved_original_edge"] is True
    assert result["data"]["routing_issue"]["blocking"] is False
    assert result["data"]["routing_issue"]["retry_required"] is False
    assert captured["quality_report"]["status"] == "warning"
    assert "自动路由器整体异常" in result["summary"]
    assert "路由前的规范化 XML" in result["summary"]


@pytest.mark.asyncio
async def test_idempotent_retry_of_accepted_version_does_not_request_review_again():
    async def accepted_persister(**payload):
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "accepted-version-id",
            "version_number": 1,
            "revision": 1,
            "lifecycle_status": "accepted",
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/accepted.drawio"},
        }

    result = await CreateDrawioBoardTool(
        quality_service=_ForbiddenQualityService(),
        candidate_persister=accepted_persister,
    ).execute(
        artifact_id="board_a",
        title="系统画板",
        operation="create",
        xml='<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>',
        _session_id="board_session_tool",
        _base_revision=0,
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert result["data"]["lifecycle_status"] == "accepted"
    assert result["data"]["requires_visual_review"] is False


@pytest.mark.asyncio
async def test_accepted_retry_does_not_render_again():
    async def accepted_persister(**payload):
        return {
            "board_id": "db-board-id",
            "candidate_version_id": "accepted-version-id",
            "version_number": 1,
            "revision": 1,
            "lifecycle_status": "accepted",
            "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/accepted.drawio"},
        }

    quality_service = _ForbiddenQualityService()
    result = await CreateDrawioBoardTool(
        quality_service=quality_service,
        candidate_persister=accepted_persister,
    ).execute(
        artifact_id="board_a",
        title="系统画板",
        operation="create",
        xml='<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>',
        _session_id="board_session_tool",
        _base_revision=0,
        _agent_run_id="run-tool",
    )

    assert result["success"] is True
    assert quality_service.calls == 0
    assert result["data"]["lifecycle_status"] == "accepted"
    assert result["data"]["requires_visual_review"] is False


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


@pytest.mark.asyncio
async def test_create_drawio_board_edit_infers_add_cell_id_from_new_xml():
    tool = CreateDrawioBoardTool()
    current_xml = '<mxCell id="existing" parent="1" value="Existing" vertex="1"><mxGeometry as="geometry"/></mxCell>'

    result = await tool.execute(
        operation="edit",
        artifact_id="infer-id",
        title="Infer ID",
        current_xml=current_xml,
        operations=[{
            "operation": "add",
            "new_xml": '<mxCell id="added" parent="1" value="Added" vertex="1"><mxGeometry as="geometry"/></mxCell>',
        }],
    )

    assert result["success"] is True
    assert result["data"]["changed_cells"] == ["added"]


@pytest.mark.asyncio
async def test_create_drawio_board_returns_structured_operation_error():
    tool = CreateDrawioBoardTool()

    result = await tool.execute(
        operation="edit",
        artifact_id="bad-operation",
        title="Bad Operation",
        current_xml='<mxCell id="existing" parent="1" vertex="1"><mxGeometry as="geometry"/></mxCell>',
        operations=[{"operation": "update_label", "label": "Missing target"}],
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "operation_cell_id_required"
    assert result["data"]["operation_index"] == 0
    assert result["metadata"]["tool_name"] == "create_drawio_board"
    assert result["data"]["retryable"] is True


@pytest.mark.asyncio
async def test_edit_receipt_counts_only_operations_that_change_xml():
    tool = CreateDrawioBoardTool()
    current_xml = '<mxCell id="2" value="Old" vertex="1" parent="1"><mxGeometry as="geometry"/></mxCell>'

    result = await tool.execute(
        operation="edit",
        artifact_id="actual-effects",
        title="Actual Effects",
        current_xml=current_xml,
        operations=[
            {"operation": "update_label", "cell_id": "2", "label": "Old"},
            {"operation": "update_label", "cell_id": "2", "label": "New"},
        ],
    )

    assert result["success"] is True
    assert result["data"]["applied_operations"] == 1
    assert result["data"]["changed_cells"] == ["2"]


@pytest.mark.asyncio
async def test_edit_rejects_empty_operations_and_missing_delete_target():
    tool = CreateDrawioBoardTool()
    current_xml = '<mxCell id="2" value="Old" vertex="1" parent="1"><mxGeometry as="geometry"/></mxCell>'

    empty = await tool.execute(
        operation="edit",
        artifact_id="empty-edit",
        title="Empty Edit",
        current_xml=current_xml,
        operations=[],
    )
    missing = await tool.execute(
        operation="edit",
        artifact_id="missing-delete",
        title="Missing Delete",
        current_xml=current_xml,
        operations=[{"operation": "delete", "cell_id": "missing"}],
    )

    assert empty["success"] is False
    assert empty["data"]["error_code"] == "operations_required"
    assert missing["success"] is False
    assert missing["data"]["operation_index"] == 0


@pytest.mark.asyncio
async def test_cascade_delete_receipt_lists_target_children_and_edges():
    tool = CreateDrawioBoardTool()
    current_xml = """
    <mxCell id="parent" value="Parent" vertex="1" parent="1"><mxGeometry as="geometry"/></mxCell>
    <mxCell id="child" value="Child" vertex="1" parent="parent"><mxGeometry as="geometry"/></mxCell>
    <mxCell id="peer" value="Peer" vertex="1" parent="1"><mxGeometry as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="child" target="peer"><mxGeometry relative="1" as="geometry"/></mxCell>
    """

    result = await tool.execute(
        operation="edit",
        artifact_id="cascade-delete",
        title="Cascade Delete",
        current_xml=current_xml,
        operations=[{"operation": "delete_with_edges", "cell_id": "parent"}],
    )

    assert result["success"] is True
    assert result["data"]["applied_operations"] == 1
    assert result["data"]["changed_cells"] == ["parent", "child", "edge"]
