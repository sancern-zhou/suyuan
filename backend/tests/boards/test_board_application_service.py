from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.boards.application import BoardApplicationService, BoardCandidateReceipt
from app.boards.models import BoardVersion
from app.boards.service import BoardNotFound
from app.db.database import Base


@pytest.fixture
async def application(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'application.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=True)
    yield BoardApplicationService(factory, storage_root=tmp_path / "artifacts"), factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_candidate_command_returns_detached_receipt_after_commit(application):
    service, _ = application

    receipt = await service.create_candidate(
        session_id="board-application-session",
        board_id=None,
        title="应用服务画板",
        base_revision=0,
        agent_run_id="run-1",
        xml="<mxfile>candidate</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref={"path": "/tmp/candidate.png"},
        summary="candidate",
    )

    assert isinstance(receipt, BoardCandidateReceipt)
    assert receipt.board_id
    assert receipt.version_number == 1
    assert receipt.lifecycle_status == "candidate"
    assert receipt.xml_ref["sha256"]


@pytest.mark.asyncio
async def test_identical_candidate_retry_in_same_run_is_idempotent(application):
    service, factory = application
    payload = dict(
        session_id="board-idempotent-session",
        board_id=None,
        title="幂等画板",
        base_revision=0,
        agent_run_id="run-idempotent",
        xml="<mxfile>same</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref={"path": "/tmp/same.png"},
        summary="same",
    )

    first = await service.create_candidate(**payload)
    second = await service.create_candidate(**{**payload, "board_id": first.board_id})

    assert second.candidate_version_id == first.candidate_version_id
    async with factory() as session:
        versions = (
            await session.execute(
                select(BoardVersion).where(BoardVersion.board_id == first.board_id)
            )
        ).scalars().all()
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_rejected_candidate_retry_returns_same_version(application):
    service, factory = application
    payload = dict(
        session_id="board-rejected-retry",
        board_id=None,
        title="失败重试",
        base_revision=0,
        agent_run_id="run-rejected-retry",
        xml="<mxfile>rejected</mxfile>",
        quality_status="failed",
        quality_report={"status": "failed"},
        screenshot_ref=None,
        summary="rejected",
        lifecycle_status="rejected",
    )

    first = await service.create_candidate(**payload)
    second = await service.create_candidate(**{**payload, "board_id": first.board_id})

    assert first.lifecycle_status == "rejected"
    assert second.candidate_version_id == first.candidate_version_id
    assert second.lifecycle_status == "rejected"
    async with factory() as session:
        versions = (
            await session.execute(
                select(BoardVersion).where(BoardVersion.board_id == first.board_id)
            )
        ).scalars().all()
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_accept_command_returns_detached_current_board_receipt(application):
    service, _ = application
    candidate = await service.create_candidate(
        session_id="board-accept-session",
        board_id=None,
        title="接受画板",
        base_revision=0,
        agent_run_id="run-accept",
        xml="<mxfile>accepted</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref=None,
        summary="accepted",
    )

    accepted = await service.accept_candidate(
        board_id=candidate.board_id,
        candidate_version_id=candidate.candidate_version_id,
        expected_board_revision=0,
        agent_run_id="run-accept",
    )

    assert accepted.version_id == candidate.candidate_version_id
    assert accepted.revision == 1
    assert accepted.lifecycle_status == "accepted"

    retry = await service.create_candidate(
        session_id="board-accept-session",
        board_id=candidate.board_id,
        title="接受画板",
        base_revision=0,
        agent_run_id="run-accept",
        xml="<mxfile>accepted</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref=None,
        summary="accepted retry",
    )
    assert retry.candidate_version_id == accepted.version_id
    assert retry.lifecycle_status == "accepted"


@pytest.mark.asyncio
async def test_session_restore_imports_legacy_board_and_returns_detached_snapshot(application):
    service, _ = application

    imported = await service.load_session_board(
        "board-legacy-application",
        legacy_title="旧画板",
        legacy_xml="<mxfile>legacy</mxfile>",
    )
    restored = await service.load_session_board("board-legacy-application")

    assert imported is not None
    assert restored is not None
    assert restored.board_id == imported.board_id
    assert restored.version_id == imported.version_id
    assert restored.xml == "<mxfile>legacy</mxfile>"
    assert restored.revision == 1


@pytest.mark.asyncio
async def test_session_restore_returns_unaccepted_candidate_for_preview(application):
    service, _ = application
    candidate = await service.create_candidate(
        session_id="board-candidate-restore",
        board_id=None,
        title="待确认画板",
        base_revision=0,
        agent_run_id="run-candidate-restore",
        xml="<mxfile>candidate preview</mxfile>",
        quality_status="warning",
        quality_report={"status": "warning", "render_status": "completed"},
        screenshot_ref={"path": "/tmp/candidate-preview.png"},
        summary="candidate preview",
    )

    restored = await service.load_session_board("board-candidate-restore")

    assert restored is not None
    assert restored.board_id == candidate.board_id
    assert restored.version_id == candidate.candidate_version_id
    assert restored.lifecycle_status == "candidate"
    assert restored.xml == "<mxfile>candidate preview</mxfile>"
    assert restored.revision == 0


@pytest.mark.asyncio
async def test_session_restore_prefers_newer_candidate_over_current_accepted_version(application):
    service, _ = application
    first = await service.create_candidate(
        session_id="board-candidate-after-accepted",
        board_id=None,
        title="持续编辑画板",
        base_revision=0,
        agent_run_id="run-accepted",
        xml="<mxfile>accepted</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref=None,
        summary="accepted",
    )
    await service.accept_candidate(
        board_id=first.board_id,
        candidate_version_id=first.candidate_version_id,
        expected_board_revision=0,
        agent_run_id="run-accepted",
    )
    second = await service.create_candidate(
        session_id="board-candidate-after-accepted",
        board_id=first.board_id,
        title="持续编辑画板",
        base_revision=1,
        agent_run_id="run-preview",
        xml="<mxfile>newer candidate</mxfile>",
        quality_status="pending",
        quality_report={"render_status": "pending"},
        screenshot_ref=None,
        summary="newer candidate",
    )

    restored = await service.load_session_board("board-candidate-after-accepted")

    assert restored is not None
    assert restored.version_id == second.candidate_version_id
    assert restored.lifecycle_status == "candidate"
    assert restored.xml == "<mxfile>newer candidate</mxfile>"
    assert restored.revision == 1


@pytest.mark.asyncio
async def test_compact_context_reference_is_resolved_inside_application_transaction(application):
    service, _ = application
    candidate = await service.create_candidate(
        session_id="board-context-session",
        board_id=None,
        title="上下文画板",
        base_revision=0,
        agent_run_id="run-context",
        xml="<mxfile>context</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref=None,
        summary="context",
    )
    accepted = await service.accept_candidate(
        board_id=candidate.board_id,
        candidate_version_id=candidate.candidate_version_id,
        expected_board_revision=0,
        agent_run_id="run-context",
    )

    resolved = await service.resolve_context_reference(
        {
            "board_id": accepted.board_id,
            "version_id": accepted.version_id,
            "revision": accepted.revision,
            "dirty": False,
        },
        expected_session_id="board-context-session",
    )

    assert resolved["current_xml"] == "<mxfile>context</mxfile>"
    assert resolved["version_id"] == accepted.version_id
    assert resolved["revision"] == 1
    assert resolved["dirty"] is False


@pytest.mark.asyncio
async def test_compact_context_reference_requires_session_binding(application):
    service, _ = application
    candidate = await service.create_candidate(
        session_id="foreign-session",
        board_id=None,
        title="外部画板",
        base_revision=0,
        agent_run_id="foreign-run",
        xml="<mxfile>private</mxfile>",
        quality_status="passed",
        quality_report={"status": "passed"},
        screenshot_ref=None,
        summary="private",
    )
    accepted = await service.accept_candidate(
        board_id=candidate.board_id,
        candidate_version_id=candidate.candidate_version_id,
        expected_board_revision=0,
        agent_run_id="foreign-run",
    )

    with pytest.raises(BoardNotFound):
        await service.resolve_context_reference(
            {
                "board_id": accepted.board_id,
                "version_id": accepted.version_id,
                "revision": accepted.revision,
            },
            expected_session_id=None,
        )
