from types import SimpleNamespace

import pytest

from app.api import session_routes
from app.conversations import ConversationSource


class _Catalog:
    async def require_read(self, session_id, user):
        return SimpleNamespace(source=ConversationSource.WEB)


class _Repository:
    def __init__(self):
        self.updated_metadata = None

    async def get_session_metadata(self, session_id):
        return {
            "drawio_board": {
                "board_id": "board-1",
                "title": "候选画板",
                "selected_cells": [],
            }
        }

    async def update_session(self, session_id, *, metadata):
        self.updated_metadata = metadata


@pytest.mark.asyncio
async def test_lazy_restore_exposes_candidate_as_preview_without_marking_it_current(monkeypatch):
    repository = _Repository()
    snapshot = SimpleNamespace(
        board_id="board-1",
        title="候选画板",
        xml="<mxfile>candidate</mxfile>",
        version_number=1,
        revision=0,
        version_id="candidate-1",
        current_version_id=None,
        lifecycle_status="candidate",
        xml_sha256="sha256",
        quality_status="warning",
        quality_report={"status": "warning"},
        screenshot_ref=None,
        updated_at="2026-07-19T09:00:00",
    )

    monkeypatch.setattr(
        "app.db.session_repository.get_session_repository",
        lambda: repository,
    )
    monkeypatch.setattr(
        session_routes,
        "BoardApplicationService",
        lambda session_factory: SimpleNamespace(
            load_session_board=lambda *args, **kwargs: _async_value(snapshot)
        ),
    )

    response = await session_routes.get_session_drawio_board(
        "board-session",
        user=SimpleNamespace(),
        catalog=_Catalog(),
    )

    board = response["drawio_board"]
    assert response["has_drawio_board"] is True
    assert board["lifecycle_status"] == "candidate"
    assert board["preview_candidate"] is True
    assert board["candidate_version_id"] == "candidate-1"
    assert board["current_version_id"] is None


async def _async_value(value):
    return value
