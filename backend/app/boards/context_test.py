from types import SimpleNamespace

import pytest

from app.boards.context import resolve_board_context_reference
from app.boards.service import BoardVersionConflict, BoardVersionService


class _Session:
    pass


@pytest.mark.asyncio
async def test_resolve_context_allows_candidate_as_continuous_working_version(monkeypatch, tmp_path):
    xml_path = tmp_path / "candidate.drawio"
    xml_path.write_text("<mxfile>candidate</mxfile>", encoding="utf-8")
    board = SimpleNamespace(
        id="board-1",
        session_id="session-1",
        title="画板",
        revision=3,
        current_version_id="accepted-3",
    )
    candidate = SimpleNamespace(
        id="candidate-4",
        board_id="board-1",
        version_number=4,
        lifecycle_status="candidate",
        xml_ref={"local_path": str(xml_path)},
        xml_sha256="candidate-sha",
    )

    async def get_board(self, board_id):
        assert board_id == "board-1"
        return board

    async def get_version(self, board_id, version_id):
        assert (board_id, version_id) == ("board-1", "candidate-4")
        return candidate

    monkeypatch.setattr(BoardVersionService, "get_board", get_board)
    monkeypatch.setattr(BoardVersionService, "get_version", get_version)

    resolved = await resolve_board_context_reference(
        _Session(),
        {
            "board_id": "board-1",
            "current_version_id": "candidate-4",
            "revision": 3,
        },
        expected_session_id="session-1",
    )

    assert resolved["current_xml"] == "<mxfile>candidate</mxfile>"
    assert resolved["working_version_id"] == "candidate-4"
    assert resolved["accepted_version_id"] == "accepted-3"
    assert resolved["candidate_version_id"] == "candidate-4"
    assert resolved["lifecycle_status"] == "candidate"


@pytest.mark.asyncio
async def test_resolve_context_rejects_non_current_non_candidate(monkeypatch):
    board = SimpleNamespace(
        id="board-1",
        session_id="session-1",
        title="画板",
        revision=3,
        current_version_id="accepted-3",
    )
    rejected = SimpleNamespace(
        id="rejected-2",
        board_id="board-1",
        lifecycle_status="rejected",
        xml_ref={"local_path": "/tmp/rejected.drawio"},
    )

    async def get_board(self, board_id):
        return board

    async def get_version(self, board_id, version_id):
        return rejected

    monkeypatch.setattr(BoardVersionService, "get_board", get_board)
    monkeypatch.setattr(BoardVersionService, "get_version", get_version)

    with pytest.raises(BoardVersionConflict):
        await resolve_board_context_reference(
            _Session(),
            {
                "board_id": "board-1",
                "current_version_id": "rejected-2",
                "revision": 3,
            },
            expected_session_id="session-1",
        )
