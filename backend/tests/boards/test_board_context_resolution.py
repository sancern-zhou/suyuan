from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.boards.context import resolve_board_context_reference
from app.boards.service import BoardVersionConflict, BoardVersionService
from app.db.database import Base


@pytest.mark.asyncio
async def test_compact_board_reference_resolves_authoritative_xml(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = BoardVersionService(session, storage_root=tmp_path / "artifacts")
        board = await service.ensure_board("board_session_context", title="上下文画板")
        version = await service.commit_manual(board.id, base_revision=0, xml="<mxfile>authoritative</mxfile>")
        resolved = await resolve_board_context_reference(
            session,
            {
                "board_id": board.id,
                "version_id": version.id,
                "revision": 1,
                "current_xml": "<mxfile>stale-client-copy</mxfile>",
                "selected_cells": [{"id": "node-1"}],
            },
            expected_session_id="board_session_context",
        )

    assert resolved["current_xml"] == "<mxfile>authoritative</mxfile>"
    assert resolved["board_id"] == board.id
    assert resolved["current_version_id"] == version.id
    assert resolved["selected_cells"] == [{"id": "node-1"}]
    await engine.dispose()


@pytest.mark.asyncio
async def test_compact_board_reference_rejects_stale_revision(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'conflict.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = BoardVersionService(session, storage_root=tmp_path / "artifacts")
        board = await service.ensure_board("board_session_stale", title="冲突画板")
        version = await service.commit_manual(board.id, base_revision=0, xml="<mxfile>v1</mxfile>")
        with pytest.raises(BoardVersionConflict):
            await resolve_board_context_reference(
                session,
                {"board_id": board.id, "version_id": version.id, "revision": 0},
                expected_session_id="board_session_stale",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_compact_candidate_reference_is_valid_continuation_context(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'candidate-context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = BoardVersionService(session, storage_root=tmp_path / "artifacts")
        board = await service.ensure_board("board_session_candidate", title="候选画板")
        accepted = await service.commit_manual(
            board.id, base_revision=0, xml="<mxfile>accepted</mxfile>"
        )
        candidate = await service.create_candidate(
            board.id,
            base_revision=1,
            xml="<mxfile>candidate</mxfile>",
            agent_run_id="run-candidate",
        )
        resolved = await resolve_board_context_reference(
            session,
            {
                "board_id": board.id,
                "version_id": candidate.id,
                "revision": 1,
            },
            expected_session_id="board_session_candidate",
        )

    assert accepted.id != candidate.id
    assert resolved["current_xml"] == "<mxfile>candidate</mxfile>"
    assert resolved["current_version_id"] == candidate.id
    assert resolved["lifecycle_status"] == "candidate"
    await engine.dispose()
