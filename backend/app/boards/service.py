from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.path_config import get_data_registry

from .models import Board, BoardVersion


class BoardVersionError(RuntimeError):
    code = "board_version_error"


class BoardNotFound(BoardVersionError):
    code = "board_not_found"


class BoardVersionNotFound(BoardVersionError):
    code = "board_version_not_found"


class BoardVersionConflict(BoardVersionError):
    code = "board_version_conflict"

    def __init__(self, current_revision: int):
        super().__init__(self.code)
        self.current_revision = current_revision


class InvalidBoardCandidate(BoardVersionError):
    code = "invalid_board_candidate"


class BoardVersionService:
    def __init__(self, session: AsyncSession, *, storage_root: Path | str | None = None) -> None:
        self.session = session
        self.storage_root = Path(storage_root or (get_data_registry() / "drawio_boards"))

    async def ensure_board(self, session_id: str, *, title: str = "Draw.io Board") -> Board:
        result = await self.session.execute(select(Board).where(Board.session_id == session_id))
        board = result.scalar_one_or_none()
        if board is not None:
            return board
        board = Board(session_id=session_id, title=title or "Draw.io Board")
        try:
            async with self.session.begin_nested():
                self.session.add(board)
                await self.session.flush()
            return board
        except IntegrityError:
            # A concurrent first request may have created the one board allowed
            # for this session while this transaction was waiting on the unique key.
            result = await self.session.execute(select(Board).where(Board.session_id == session_id))
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return existing

    async def get_board(self, board_id: str, *, for_update: bool = False) -> Board:
        statement = select(Board).where(Board.id == board_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        board = result.scalar_one_or_none()
        if board is None:
            raise BoardNotFound(board_id)
        return board

    async def get_board_for_session(self, session_id: str) -> Board | None:
        result = await self.session.execute(select(Board).where(Board.session_id == session_id))
        return result.scalar_one_or_none()

    async def get_version(self, board_id: str, version_id: str) -> BoardVersion:
        result = await self.session.execute(
            select(BoardVersion).where(
                BoardVersion.id == version_id,
                BoardVersion.board_id == board_id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise BoardVersionNotFound(version_id)
        return version

    async def list_versions(self, board_id: str) -> list[BoardVersion]:
        result = await self.session.execute(
            select(BoardVersion)
            .where(BoardVersion.board_id == board_id)
            .order_by(BoardVersion.version_number)
        )
        return list(result.scalars().all())

    async def get_latest_restorable_version(self, board: Board) -> BoardVersion | None:
        """Return the latest visible state without promoting a candidate."""
        restorable = [BoardVersion.lifecycle_status == "candidate"]
        if board.current_version_id:
            restorable.append(BoardVersion.id == board.current_version_id)
        result = await self.session.execute(
            select(BoardVersion)
            .where(
                BoardVersion.board_id == board.id,
                or_(*restorable),
            )
            .order_by(BoardVersion.version_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_draft(self, board_id: str, *, xml: str) -> Board:
        board = await self.get_board(board_id, for_update=True)
        xml_ref, digest = self._store_xml(board.id, xml, prefix="draft")
        board.draft_xml_ref = xml_ref
        board.draft_sha256 = digest
        board.draft_revision += 1
        board.updated_at = datetime.utcnow()
        await self.session.flush()
        return board

    async def commit_manual(self, board_id: str, *, base_revision: int, xml: str) -> BoardVersion:
        board = await self.get_board(board_id, for_update=True)
        self._require_revision(board, base_revision)
        digest = self._sha256(xml)
        current = await self._current_version(board)
        if current is not None and current.xml_sha256 == digest:
            return current
        version = await self._create_version(
            board,
            source="manual",
            lifecycle_status="accepted",
            xml=xml,
            quality_status="passed",
            quality_report={"status": "passed", "source": "manual"},
            accepted_at=datetime.utcnow(),
        )
        self._advance_board(board, version)
        await self.session.flush()
        return version

    async def create_candidate(
        self,
        board_id: str,
        *,
        base_revision: int,
        xml: str,
        agent_run_id: str,
        quality_status: str = "pending",
        quality_report: dict[str, Any] | None = None,
        screenshot_ref: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> BoardVersion:
        board = await self.get_board(board_id, for_update=True)
        digest = self._sha256(xml)
        existing_result = await self.session.execute(
            select(BoardVersion)
            .where(
                BoardVersion.board_id == board_id,
                BoardVersion.agent_run_id == agent_run_id,
                BoardVersion.xml_sha256 == digest,
                BoardVersion.source == "agent",
            )
            .order_by(BoardVersion.version_number)
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            return existing
        self._require_revision(board, base_revision)
        version = await self._create_version(
            board,
            source="agent",
            lifecycle_status="candidate",
            xml=xml,
            quality_status=quality_status,
            quality_report=quality_report or {},
            screenshot_ref=screenshot_ref,
            agent_run_id=agent_run_id,
            summary=summary,
        )
        await self.session.flush()
        return version

    async def reject_candidate(
        self,
        board_id: str,
        *,
        candidate_version_id: str,
        quality_status: str = "failed",
        quality_report: dict[str, Any] | None = None,
    ) -> BoardVersion:
        version = await self.get_version(board_id, candidate_version_id)
        if version.lifecycle_status != "candidate":
            raise InvalidBoardCandidate(candidate_version_id)
        version.lifecycle_status = "rejected"
        version.quality_status = quality_status
        if quality_report is not None:
            version.quality_report = quality_report
        await self.session.flush()
        return version

    async def complete_candidate_render(
        self,
        board_id: str,
        *,
        candidate_version_id: str,
        agent_run_id: str,
        quality_status: str,
        quality_report: dict[str, Any],
        screenshot_ref: dict[str, Any] | None,
    ) -> BoardVersion:
        version = await self.get_version(board_id, candidate_version_id)
        if (
            version.lifecycle_status not in {"candidate", "accepted"}
            or version.agent_run_id != agent_run_id
        ):
            raise InvalidBoardCandidate(candidate_version_id)
        version.quality_status = quality_status
        version.quality_report = quality_report
        version.screenshot_ref = screenshot_ref
        await self.session.flush()
        return version

    async def accept_candidate(
        self,
        board_id: str,
        *,
        candidate_version_id: str,
        expected_board_revision: int,
        agent_run_id: str,
    ) -> BoardVersion:
        board = await self.get_board(board_id, for_update=True)
        self._require_revision(board, expected_board_revision)
        version = await self.get_version(board_id, candidate_version_id)
        if (
            version.lifecycle_status != "candidate"
            or version.agent_run_id != agent_run_id
        ):
            raise InvalidBoardCandidate(candidate_version_id)
        pending = await self.session.execute(
            select(BoardVersion).where(
                BoardVersion.board_id == board_id,
                BoardVersion.agent_run_id == agent_run_id,
                BoardVersion.lifecycle_status == "candidate",
                BoardVersion.id != candidate_version_id,
            )
        )
        for older in pending.scalars().all():
            older.lifecycle_status = "rejected"
        version.lifecycle_status = "accepted"
        version.accepted_at = datetime.utcnow()
        self._advance_board(board, version)
        await self.session.flush()
        return version

    async def restore(self, board_id: str, *, version_id: str, base_revision: int) -> BoardVersion:
        board = await self.get_board(board_id, for_update=True)
        self._require_revision(board, base_revision)
        source = await self.get_version(board_id, version_id)
        current_id = board.current_version_id
        restored = BoardVersion(
            board_id=board.id,
            version_number=await self._next_version_number(board.id),
            parent_version_id=current_id,
            restored_from_version_id=source.id,
            source="restore",
            lifecycle_status="accepted",
            xml_ref=dict(source.xml_ref),
            xml_sha256=source.xml_sha256,
            screenshot_ref=dict(source.screenshot_ref) if source.screenshot_ref else None,
            quality_status=source.quality_status,
            quality_report=dict(source.quality_report or {}),
            summary=f"恢复版本 v{source.version_number}",
            accepted_at=datetime.utcnow(),
        )
        self.session.add(restored)
        await self.session.flush()
        self._advance_board(board, restored)
        await self.session.flush()
        return restored

    async def import_legacy(self, session_id: str, *, title: str, xml: str) -> Board:
        board = await self.ensure_board(session_id, title=title)
        board = await self.get_board(board.id, for_update=True)
        if board.current_version_id:
            return board
        version = await self._create_version(
            board,
            source="legacy_import",
            lifecycle_status="accepted",
            xml=xml,
            quality_status="passed",
            quality_report={"status": "passed", "source": "legacy_import"},
            accepted_at=datetime.utcnow(),
        )
        self._advance_board(board, version)
        await self.session.flush()
        return board

    async def _create_version(
        self,
        board: Board,
        *,
        source: str,
        lifecycle_status: str,
        xml: str,
        quality_status: str,
        quality_report: dict[str, Any],
        screenshot_ref: dict[str, Any] | None = None,
        agent_run_id: str | None = None,
        summary: str | None = None,
        accepted_at: datetime | None = None,
    ) -> BoardVersion:
        xml_ref, digest = self._store_xml(board.id, xml, prefix=source)
        version = BoardVersion(
            board_id=board.id,
            version_number=await self._next_version_number(board.id),
            parent_version_id=board.current_version_id,
            source=source,
            lifecycle_status=lifecycle_status,
            xml_ref=xml_ref,
            xml_sha256=digest,
            screenshot_ref=screenshot_ref,
            quality_status=quality_status,
            quality_report=quality_report,
            agent_run_id=agent_run_id,
            summary=summary,
            accepted_at=accepted_at,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def _next_version_number(self, board_id: str) -> int:
        result = await self.session.execute(
            select(func.max(BoardVersion.version_number)).where(BoardVersion.board_id == board_id)
        )
        return int(result.scalar_one_or_none() or 0) + 1

    async def _current_version(self, board: Board) -> BoardVersion | None:
        if not board.current_version_id:
            return None
        return await self.get_version(board.id, board.current_version_id)

    @staticmethod
    def _require_revision(board: Board, expected: int) -> None:
        if board.revision != expected:
            raise BoardVersionConflict(board.revision)

    @staticmethod
    def _advance_board(board: Board, version: BoardVersion) -> None:
        board.current_version_id = version.id
        board.revision += 1
        board.draft_xml_ref = None
        board.draft_sha256 = None
        board.updated_at = datetime.utcnow()

    @staticmethod
    def _sha256(xml: str) -> str:
        return hashlib.sha256(str(xml).encode("utf-8")).hexdigest()

    def _store_xml(self, board_id: str, xml: str, *, prefix: str) -> tuple[dict[str, Any], str]:
        digest = self._sha256(xml)
        directory = self.storage_root / board_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}_{uuid.uuid4().hex}_{digest[:12]}.drawio"
        path.write_text(str(xml), encoding="utf-8")
        local_path = str(path.resolve())
        return (
            {
                "kind": "drawio_board_xml",
                "artifact_kind": "drawio_board",
                "board_id": board_id,
                "local_path": local_path,
                "path": local_path,
                "read_url": f"/api/file/{quote(local_path, safe='')}",
                "mime_type": "application/xml",
                "format": "drawio",
                "size_bytes": len(str(xml).encode("utf-8")),
                "sha256": digest,
            },
            digest,
        )
