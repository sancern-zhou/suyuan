from datetime import datetime

import pytest

from app.api.session_routes import _attach_drawio_board_summary
from app.boards.models import Board


class FakeSession:
    def __init__(self, board):
        self.board = board

    async def scalar(self, _statement):
        return self.board


@pytest.mark.asyncio
async def test_restore_hydrates_authoritative_board_and_saved_draft_state():
    board = Board(
        id="79f78cb5-4364-4ce7-9419-3d5907ef4bc8",
        session_id="board-session",
        title="Architecture",
        current_version_id="accepted-version",
        revision=3,
        draft_revision=4,
        draft_xml_ref={"path": "/private/draft.drawio"},
        updated_at=datetime(2026, 8, 24, 2, 0, 0),
    )

    restored = await _attach_drawio_board_summary(
        {"metadata": {}},
        session_id="board-session",
        db=FakeSession(board),
    )

    summary = restored["metadata"]["drawio_board"]
    assert summary["board_id"] == board.id
    assert summary["current_version_id"] == "accepted-version"
    assert summary["draft_revision"] == 4
    assert summary["has_draft"] is True
    assert "/private/" not in str(summary)
