import base64
import zlib
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.boards.models import Board, BoardVersion
from app.boards.service import BoardVersionConflict, BoardVersionService
from app.db.database import Base


def _compressed_drawio_xml(graph_xml: str) -> str:
    compressor = zlib.compressobj(level=9, wbits=-15)
    payload = compressor.compress(quote(graph_xml, safe="~()*!.'").encode("utf-8")) + compressor.flush()
    encoded = base64.b64encode(payload).decode("ascii")
    return f'<mxfile><diagram id="page-1">{encoded}</diagram></mxfile>'


@pytest.mark.asyncio
async def test_concurrent_first_board_creation_reuses_unique_constraint_winner(tmp_path: Path):
    winner = Board(id="winner", session_id="shared-session", title="Winner")

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Nested:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class RacingSession:
        def __init__(self):
            self.execute_count = 0

        async def execute(self, statement):
            self.execute_count += 1
            return Result(None if self.execute_count == 1 else winner)

        def begin_nested(self):
            return Nested()

        def add(self, board):
            pass

        async def flush(self):
            raise IntegrityError("insert", {}, Exception("duplicate session_id"))

    board = await BoardVersionService(
        RacingSession(), storage_root=tmp_path / "artifacts"
    ).ensure_board("shared-session")

    assert board is winner


@pytest.fixture
async def board_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'boards.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, tmp_path / "artifacts"
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_versions_are_immutable_and_deduplicated_by_hash(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_1", title="系统架构图")

    first = await service.commit_manual(
        board.id,
        base_revision=0,
        xml="<mxfile><diagram><mxGraphModel><root /></mxGraphModel></diagram></mxfile>",
    )
    duplicate = await service.commit_manual(
        board.id,
        base_revision=1,
        xml="<mxfile><diagram><mxGraphModel><root /></mxGraphModel></diagram></mxfile>",
    )

    assert first.id == duplicate.id
    assert first.source == "manual"
    assert first.lifecycle_status == "accepted"
    assert first.version_number == 1
    assert board.revision == 1
    assert board.current_version_id == first.id
    assert Path(first.xml_ref["local_path"]).read_text(encoding="utf-8").startswith("<mxfile>")
    assert len(await service.list_versions(board.id)) == 1


@pytest.mark.asyncio
async def test_manual_commit_ignores_drawio_viewport_only_changes(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_viewport", title="流程图")
    original = '<mxfile><diagram><mxGraphModel dx="528" dy="674"><root><mxCell id="0" /></root></mxGraphModel></diagram></mxfile>'
    viewport_changed = '<mxfile><diagram><mxGraphModel dx="641" dy="542"><root><mxCell id="0" /></root></mxGraphModel></diagram></mxfile>'

    first = await service.commit_manual(board.id, base_revision=0, xml=original)
    duplicate = await service.commit_manual(board.id, base_revision=1, xml=viewport_changed)

    assert duplicate.id == first.id
    assert board.current_version_id == first.id
    assert board.revision == 1
    assert len(await service.list_versions(board.id)) == 1


@pytest.mark.asyncio
async def test_manual_commit_keeps_nondefault_graph_settings_as_real_changes(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_graph_settings", title="流程图")
    original = '<mxfile><diagram><mxGraphModel grid="1"><root><mxCell id="0" /></root></mxGraphModel></diagram></mxfile>'
    grid_hidden = '<mxfile><diagram><mxGraphModel grid="0"><root><mxCell id="0" /></root></mxGraphModel></diagram></mxfile>'

    first = await service.commit_manual(board.id, base_revision=0, xml=original)
    changed = await service.commit_manual(board.id, base_revision=1, xml=grid_hidden)

    assert changed.id != first.id
    assert changed.version_number == 2
    assert board.current_version_id == changed.id


@pytest.mark.asyncio
async def test_manual_commit_deduplicates_compressed_drawio_viewport_changes(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_compressed", title="流程图")
    original = _compressed_drawio_xml('<mxGraphModel dx="10" dy="20"><root><mxCell id="0" /></root></mxGraphModel>')
    viewport_changed = _compressed_drawio_xml('<mxGraphModel dx="30" dy="40"><root><mxCell id="0" /></root></mxGraphModel>')

    first = await service.commit_manual(board.id, base_revision=0, xml=original)
    duplicate = await service.commit_manual(board.id, base_revision=1, xml=viewport_changed)

    assert duplicate.id == first.id
    assert board.revision == 1
    assert len(await service.list_versions(board.id)) == 1


@pytest.mark.asyncio
async def test_manual_commit_reactivates_matching_historical_version_without_copying_it(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_reactivate", title="流程图")
    v1_xml = '<mxfile host="suyuan"><diagram><mxGraphModel><root><mxCell id="0" value="V1" /></root></mxGraphModel></diagram></mxfile>'
    v2_xml = '<mxfile><diagram><mxGraphModel dx="300" dy="400"><root><mxCell id="0" value="V2" /></root></mxGraphModel></diagram></mxfile>'
    exported_v1 = '''<mxfile host="embed.diagrams.net">
      <diagram><mxGraphModel dx="900" dy="800" grid="1" page="1">
        <root><mxCell value="V1" id="0" /></root>
      </mxGraphModel></diagram>
    </mxfile>'''

    v1 = await service.commit_manual(board.id, base_revision=0, xml=v1_xml)
    await service.commit_manual(board.id, base_revision=1, xml=v2_xml)
    restored = await service.commit_manual(
        board.id,
        base_revision=2,
        xml=exported_v1,
        source_version_id=v1.id,
    )

    assert restored.id == v1.id
    assert board.current_version_id == v1.id
    assert board.revision == 3
    assert len(await service.list_versions(board.id)) == 2


@pytest.mark.asyncio
async def test_manual_edit_from_historical_version_creates_child_of_selected_source(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_branch", title="流程图")
    v1 = await service.commit_manual(board.id, base_revision=0, xml='<mxfile><diagram><mxGraphModel><root><mxCell id="0" value="V1" /></root></mxGraphModel></diagram></mxfile>')
    await service.commit_manual(board.id, base_revision=1, xml='<mxfile><diagram><mxGraphModel><root><mxCell id="0" value="V2" /></root></mxGraphModel></diagram></mxfile>')

    edited = await service.commit_manual(
        board.id,
        base_revision=2,
        xml='<mxfile><diagram><mxGraphModel><root><mxCell id="0" value="V1 edited" /></root></mxGraphModel></diagram></mxfile>',
        source_version_id=v1.id,
    )

    assert edited.id != v1.id
    assert edited.parent_version_id == v1.id
    assert edited.version_number == 3
    assert board.current_version_id == edited.id


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_without_overwriting_current_version(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_2", title="流程图")
    current = await service.commit_manual(board.id, base_revision=0, xml="<mxfile>A</mxfile>")

    with pytest.raises(BoardVersionConflict) as exc_info:
        await service.commit_manual(board.id, base_revision=0, xml="<mxfile>B</mxfile>")

    assert exc_info.value.current_revision == 1
    assert board.current_version_id == current.id
    assert len(await service.list_versions(board.id)) == 1


@pytest.mark.asyncio
async def test_candidate_requires_explicit_acceptance_before_becoming_current(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)
    board = await service.ensure_board("board_session_4", title="能力地图")

    candidate = await service.create_candidate(
        board.id,
        base_revision=0,
        xml="<mxfile>candidate</mxfile>",
        agent_run_id="run-1",
        quality_status="passed",
        quality_report={"status": "passed"},
    )

    assert candidate.lifecycle_status == "candidate"
    assert board.current_version_id is None
    assert board.revision == 0

    accepted = await service.accept_candidate(
        board.id,
        candidate_version_id=candidate.id,
        expected_board_revision=0,
        agent_run_id="run-1",
    )

    assert accepted.lifecycle_status == "accepted"
    assert board.current_version_id == candidate.id
    assert board.revision == 1


@pytest.mark.asyncio
async def test_legacy_import_is_idempotent(board_session):
    session, storage_root = board_session
    service = BoardVersionService(session, storage_root=storage_root)

    first = await service.import_legacy(
        "board_session_legacy",
        title="旧画板",
        xml="<mxfile>legacy</mxfile>",
    )
    second = await service.import_legacy(
        "board_session_legacy",
        title="旧画板",
        xml="<mxfile>legacy</mxfile>",
    )

    assert first.id == second.id
    assert first.revision == 1
    versions = await service.list_versions(first.id)
    assert len(versions) == 1
    assert versions[0].source == "legacy_import"
