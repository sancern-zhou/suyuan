from types import SimpleNamespace

import pytest

from app.boards.service import BoardVersionService


class _ScalarList:
    def all(self):
        return []


class _ExecuteResult:
    def scalars(self):
        return _ScalarList()


class _EmptyFirst:
    def first(self):
        return None


class _ExistingResult:
    def scalars(self):
        return _EmptyFirst()


class _Session:
    flush_count = 0

    async def flush(self):
        self.flush_count += 1

    async def execute(self, statement):
        return _ExecuteResult()


@pytest.mark.asyncio
async def test_complete_candidate_render_updates_evidence_without_rejecting_candidate(monkeypatch):
    session = _Session()
    service = BoardVersionService(session)
    version = SimpleNamespace(
        id="candidate-1",
        board_id="board-1",
        lifecycle_status="candidate",
        agent_run_id="run-1",
        quality_status="pending",
        quality_report={"render_status": "pending"},
        screenshot_ref=None,
    )

    async def get_version(board_id, version_id):
        assert (board_id, version_id) == ("board-1", "candidate-1")
        return version

    monkeypatch.setattr(service, "get_version", get_version)
    updated = await service.complete_candidate_render(
        "board-1",
        candidate_version_id="candidate-1",
        agent_run_id="run-1",
        quality_status="failed",
        quality_report={"status": "failed", "render_status": "failed"},
        screenshot_ref=None,
    )

    assert updated is version
    assert version.lifecycle_status == "candidate"
    assert version.quality_status == "failed"
    assert version.quality_report["render_status"] == "failed"
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_accept_candidate_allows_agent_to_accept_after_failed_or_skipped_render(monkeypatch):
    session = _Session()
    service = BoardVersionService(session)
    board = SimpleNamespace(
        id="board-1",
        revision=0,
        current_version_id=None,
        draft_xml_ref=None,
        draft_sha256=None,
        updated_at=None,
    )
    version = SimpleNamespace(
        id="candidate-1",
        board_id="board-1",
        lifecycle_status="candidate",
        agent_run_id="run-1",
        quality_status="failed",
        accepted_at=None,
    )

    async def get_board(board_id, *, for_update=False):
        return board

    async def get_version(board_id, version_id):
        return version

    monkeypatch.setattr(service, "get_board", get_board)
    monkeypatch.setattr(service, "get_version", get_version)

    accepted = await service.accept_candidate(
        "board-1",
        candidate_version_id="candidate-1",
        expected_board_revision=0,
        agent_run_id="run-1",
    )

    assert accepted is version
    assert version.lifecycle_status == "accepted"
    assert board.current_version_id == "candidate-1"


@pytest.mark.asyncio
async def test_create_candidate_keeps_previous_candidate_as_parent(monkeypatch):
    session = _Session()
    service = BoardVersionService(session)
    board = SimpleNamespace(
        id="board-1",
        revision=2,
        current_version_id="accepted-1",
    )
    parent = SimpleNamespace(id="candidate-1", board_id="board-1")
    created = SimpleNamespace(id="candidate-2")
    captured = {}

    async def execute(statement):
        return _ExistingResult()

    async def get_board(board_id, *, for_update=False):
        return board

    async def get_version(board_id, version_id):
        assert (board_id, version_id) == ("board-1", "candidate-1")
        return parent

    async def create_version(board, **kwargs):
        captured.update(kwargs)
        return created

    monkeypatch.setattr(session, "execute", execute)
    monkeypatch.setattr(service, "get_board", get_board)
    monkeypatch.setattr(service, "get_version", get_version)
    monkeypatch.setattr(service, "_create_version", create_version)

    result = await service.create_candidate(
        "board-1",
        base_revision=2,
        parent_version_id="candidate-1",
        xml="<mxfile />",
        agent_run_id="run-1",
    )

    assert result is created
    assert captured["parent_version_id"] == "candidate-1"
