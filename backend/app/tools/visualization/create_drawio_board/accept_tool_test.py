import pytest

from .accept_tool import AcceptDrawioBoardCandidateTool


def test_accept_tool_describes_visual_review_as_agent_guidance_not_a_gate():
    schema = AcceptDrawioBoardCandidateTool().get_function_schema()

    assert "recommended" in schema["description"].lower()
    assert "must" not in schema["description"].lower()
    assert "do not call" not in schema["description"].lower()


async def _accepter(**payload):
    assert payload == {
        "board_id": "board-db",
        "candidate_version_id": "candidate-1",
        "expected_board_revision": 3,
        "agent_run_id": "run-1",
    }
    return {
        "board_id": "board-db",
        "version_id": "candidate-1",
        "version_number": 4,
        "revision": 4,
        "title": "系统画板",
        "xml_ref": {"kind": "drawio_board_xml", "local_path": "/tmp/accepted.drawio"},
        "screenshot_ref": {"kind": "drawio_board_screenshot", "local_path": "/tmp/accepted.png"},
        "quality_status": "passed",
        "quality_report": {"status": "passed"},
    }


@pytest.mark.asyncio
async def test_accept_candidate_returns_current_version_payload():
    tool = AcceptDrawioBoardCandidateTool(candidate_accepter=_accepter)

    result = await tool.execute(
        candidate_version_id="candidate-1",
        _board_id="board-db",
        _expected_board_revision=3,
        _agent_run_id="run-1",
    )

    assert result["success"] is True
    assert result["data"]["artifact_kind"] == "drawio_board"
    assert result["data"]["candidate_accepted"] is True
    assert result["data"]["current_version_id"] == "candidate-1"
    assert result["data"]["revision"] == 4
    assert result["data"]["requires_visual_review"] is False
    assert "已正式提交" in result["summary"]
    assert "已通过视觉复核" not in result["summary"]
