from types import SimpleNamespace

import pytest

from app.boards.application import BoardApplicationService


class _Context:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Session:
    def begin(self):
        return _Context(None)


class _Domain:
    def __init__(self, board, version):
        self.board = board
        self.version = version
        self.completed = None

    async def get_board(self, board_id, *, for_update=False):
        return self.board

    async def get_version(self, board_id, version_id):
        return self.version

    async def complete_candidate_render(self, board_id, **payload):
        self.completed = {"board_id": board_id, **payload}
        self.version.quality_status = payload["quality_status"]
        self.version.quality_report = payload["quality_report"]
        self.version.screenshot_ref = payload["screenshot_ref"]
        return self.version


class _Application(BoardApplicationService):
    def __init__(self, domain):
        super().__init__(lambda: _Context(_Session()))
        self.domain = domain

    def _domain(self, session):
        return self.domain


@pytest.mark.asyncio
async def test_application_loads_authorized_candidate_xml_for_render(tmp_path):
    xml_path = tmp_path / "candidate.drawio"
    xml_path.write_text("<mxfile>candidate</mxfile>", encoding="utf-8")
    board = SimpleNamespace(id="board-1", session_id="board-session", title="系统画板")
    version = SimpleNamespace(
        id="candidate-1",
        agent_run_id="run-1",
        lifecycle_status="candidate",
        xml_ref={"local_path": str(xml_path)},
        screenshot_ref=None,
        quality_status="pending",
        quality_report={"render_status": "pending"},
    )

    receipt = await _Application(_Domain(board, version)).load_candidate_for_render(
        session_id="board-session",
        board_id="board-1",
        candidate_version_id="candidate-1",
        agent_run_id="run-1",
    )

    assert receipt.xml == "<mxfile>candidate</mxfile>"
    assert receipt.title == "系统画板"
    assert receipt.candidate_version_id == "candidate-1"
    assert receipt.quality_report["render_status"] == "pending"


@pytest.mark.asyncio
async def test_application_persists_render_result_without_lifecycle_transition(tmp_path):
    board = SimpleNamespace(id="board-1", session_id="board-session", title="系统画板")
    version = SimpleNamespace(
        id="candidate-1",
        agent_run_id="run-1",
        lifecycle_status="candidate",
        xml_ref={"local_path": str(tmp_path / "candidate.drawio")},
        screenshot_ref=None,
        quality_status="pending",
        quality_report={},
    )
    domain = _Domain(board, version)

    receipt = await _Application(domain).complete_candidate_render(
        session_id="board-session",
        board_id="board-1",
        candidate_version_id="candidate-1",
        agent_run_id="run-1",
        quality_status="passed",
        quality_report={"status": "passed", "render_status": "completed"},
        screenshot_ref={"local_path": "/tmp/candidate.png"},
    )

    assert receipt.lifecycle_status == "candidate"
    assert receipt.quality_status == "passed"
    assert receipt.screenshot_ref["local_path"] == "/tmp/candidate.png"
    assert domain.completed["candidate_version_id"] == "candidate-1"
