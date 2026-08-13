import pytest

import app.tools.visualization.create_drawio_board as drawio_tools
from app.boards.quality import BoardRenderFailed
from app.tools.visualization.create_drawio_board.render_tool import RenderDrawioBoardCandidateTool


def test_drawio_tool_package_exports_deferred_render_tool():
    assert hasattr(drawio_tools, "RenderDrawioBoardCandidateTool")


class _QualityService:
    calls = 0

    async def inspect(self, xml, *, board_id, candidate_id):
        self.calls += 1
        assert xml == "<mxfile>candidate</mxfile>"
        assert board_id == "board-db"
        assert candidate_id == "candidate-1"
        return {
            "quality_report": {
                "status": "warning",
                "errors": [],
                "warnings": [{"code": "orphan_node"}],
                "metrics": {"vertex_count": 5, "orphan_count": 1},
            },
            "screenshot_ref": {
                "kind": "drawio_board_screenshot",
                "local_path": "/tmp/candidate.png",
                "mime_type": "image/png",
            },
        }


async def _candidate_loader(**payload):
    assert payload == {
        "session_id": "board-session",
        "board_id": "board-db",
        "candidate_version_id": "candidate-1",
        "agent_run_id": "run-1",
    }
    return {
        "board_id": "board-db",
        "candidate_version_id": "candidate-1",
        "title": "系统画板",
        "xml": "<mxfile>candidate</mxfile>",
        "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/candidate.drawio"},
        "lifecycle_status": "candidate",
        "quality_status": "pending",
        "quality_report": {
            "status": "warning",
            "render_status": "failed",
            "render_error": "previous timeout",
            "routing_status": "partial",
            "routing_issues": [{"edge_id": "edge-1", "blocking": False}],
            "warnings": [
                {"code": "edge_routing_degraded", "edge_id": "edge-1"}
            ],
            "metrics": {
                "vertex_count": 4,
                "routed_edge_count": 3,
                "rerouted_edge_count": 2,
                "edge_vertex_intersection_count": 0,
                "edge_edge_crossing_count": 1,
                "max_route_offset": 80,
            },
        },
        "screenshot_ref": None,
    }


@pytest.mark.asyncio
async def test_render_candidate_returns_visual_review_attachment_and_persists_result():
    persisted = []

    async def persist(**payload):
        persisted.append(payload)
        return {**payload, "lifecycle_status": "candidate"}

    quality_service = _QualityService()
    result = await RenderDrawioBoardCandidateTool(
        quality_service=quality_service,
        candidate_loader=_candidate_loader,
        render_persister=persist,
    ).execute(
        candidate_version_id="candidate-1",
        _session_id="board-session",
        _board_id="board-db",
        _agent_run_id="run-1",
    )

    assert quality_service.calls == 1
    assert result["success"] is True
    assert result["type"] == "multimodal_attachment"
    assert result["data"]["render_status"] == "completed"
    assert result["data"]["quality_status"] == "warning"
    assert result["data"]["candidate_version_id"] == "candidate-1"
    assert result["data"]["requires_visual_review"] is True
    assert result["attachments"][0]["local_path"] == "/tmp/candidate.png"
    assert persisted[0]["quality_report"]["render_status"] == "completed"
    assert "render_error" not in persisted[0]["quality_report"]
    assert persisted[0]["quality_report"]["metrics"] == {
        "vertex_count": 5,
        "orphan_count": 1,
        "routed_edge_count": 3,
        "rerouted_edge_count": 2,
        "edge_vertex_intersection_count": 0,
        "edge_edge_crossing_count": 1,
        "max_route_offset": 80,
    }
    assert persisted[0]["quality_report"]["routing_status"] == "partial"
    assert persisted[0]["quality_report"]["routing_issues"] == [
        {"edge_id": "edge-1", "blocking": False}
    ]
    assert {warning["code"] for warning in persisted[0]["quality_report"]["warnings"]} == {
        "edge_routing_degraded",
        "orphan_node",
    }
    assert persisted[0]["screenshot_ref"]["local_path"] == "/tmp/candidate.png"


@pytest.mark.asyncio
async def test_render_candidate_reuses_existing_screenshot_without_rendering():
    async def load_existing(**payload):
        source = await _candidate_loader(**payload)
        source.update(
            {
                "quality_status": "passed",
                "quality_report": {"status": "passed", "render_status": "completed"},
                "screenshot_ref": {
                    "kind": "drawio_board_screenshot",
                    "local_path": "/tmp/existing.png",
                    "mime_type": "image/png",
                },
            }
        )
        return source

    quality_service = _QualityService()
    result = await RenderDrawioBoardCandidateTool(
        quality_service=quality_service,
        candidate_loader=load_existing,
    ).execute(
        candidate_version_id="candidate-1",
        _session_id="board-session",
        _board_id="board-db",
        _agent_run_id="run-1",
    )

    assert result["success"] is True
    assert result["data"]["render_status"] == "completed"
    assert result["attachments"][0]["local_path"] == "/tmp/existing.png"
    assert quality_service.calls == 0


@pytest.mark.asyncio
async def test_render_failure_is_retryable_and_does_not_reject_candidate():
    class FailedRenderer:
        async def inspect(self, xml, *, board_id, candidate_id):
            raise BoardRenderFailed(
                "renderer timeout",
                report={"status": "warning", "errors": [], "warnings": []},
            )

    persisted = []

    async def persist(**payload):
        persisted.append(payload)
        return {**payload, "lifecycle_status": "candidate"}

    result = await RenderDrawioBoardCandidateTool(
        quality_service=FailedRenderer(),
        candidate_loader=_candidate_loader,
        render_persister=persist,
    ).execute(
        candidate_version_id="candidate-1",
        _session_id="board-session",
        _board_id="board-db",
        _agent_run_id="run-1",
    )

    assert result["success"] is False
    assert result["data"]["error_code"] == "board_render_failed"
    assert result["data"]["render_status"] == "failed"
    assert result["data"]["retryable"] is True
    assert result["data"]["lifecycle_status"] == "candidate"
    assert persisted[0]["screenshot_ref"] is None
    assert persisted[0]["quality_report"]["render_status"] == "failed"


@pytest.mark.asyncio
async def test_render_candidate_requires_runtime_identity():
    result = await RenderDrawioBoardCandidateTool().execute(candidate_version_id="candidate-1")

    assert result["success"] is False
    assert result["data"]["error_code"] == "board_render_context_required"
