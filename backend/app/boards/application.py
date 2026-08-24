from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from .context import resolve_board_context_reference
from .models import Board, BoardVersion
from .service import BoardVersionService, InvalidBoardCandidate


@dataclass(frozen=True)
class BoardCandidateReceipt:
    board_id: str
    candidate_version_id: str
    version_number: int
    revision: int
    lifecycle_status: str
    xml_ref: dict[str, Any]


@dataclass(frozen=True)
class BoardRenderSource:
    board_id: str
    candidate_version_id: str
    title: str
    xml: str
    xml_ref: dict[str, Any]
    lifecycle_status: str
    quality_status: str
    quality_report: dict[str, Any]
    screenshot_ref: dict[str, Any] | None


@dataclass(frozen=True)
class BoardRenderReceipt:
    board_id: str
    candidate_version_id: str
    lifecycle_status: str
    quality_status: str
    quality_report: dict[str, Any]
    screenshot_ref: dict[str, Any] | None


@dataclass(frozen=True)
class BoardAcceptedReceipt:
    board_id: str
    version_id: str
    version_number: int
    revision: int
    title: str
    lifecycle_status: str
    xml_ref: dict[str, Any]
    screenshot_ref: dict[str, Any] | None
    quality_status: str
    quality_report: dict[str, Any]


@dataclass(frozen=True)
class BoardSnapshot:
    board_id: str
    session_id: str
    title: str
    revision: int
    version_id: str
    current_version_id: str | None
    version_number: int
    lifecycle_status: str
    xml: str
    xml_sha256: str
    quality_status: str
    quality_report: dict[str, Any]
    screenshot_ref: dict[str, Any] | None
    updated_at: str | None


class BoardApplicationService:
    """Owns board transactions and returns detached immutable receipts."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        storage_root: Path | str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage_root = storage_root

    def _domain(self, session: AsyncSession) -> BoardVersionService:
        return BoardVersionService(session, storage_root=self.storage_root)

    async def create_candidate(
        self,
        *,
        session_id: str,
        board_id: str | None,
        title: str,
        base_revision: int,
        agent_run_id: str,
        xml: str,
        quality_status: str,
        quality_report: dict[str, Any],
        screenshot_ref: dict[str, Any] | None,
        summary: str,
        lifecycle_status: str = "candidate",
    ) -> BoardCandidateReceipt:
        async with self.session_factory() as session:
            async with session.begin():
                domain = self._domain(session)
                if board_id:
                    board = await domain.get_board(board_id, for_update=True)
                    if board.session_id != session_id:
                        raise ValueError("board_session_mismatch")
                else:
                    board = await domain.ensure_board(session_id, title=title)
                candidate = await domain.create_candidate(
                    board.id,
                    base_revision=base_revision,
                    xml=xml,
                    agent_run_id=agent_run_id,
                    quality_status=quality_status,
                    quality_report=quality_report,
                    screenshot_ref=screenshot_ref,
                    summary=summary,
                )
                if lifecycle_status == "rejected" and candidate.lifecycle_status == "candidate":
                    candidate = await domain.reject_candidate(
                        board.id,
                        candidate_version_id=candidate.id,
                        quality_status=quality_status,
                        quality_report=quality_report,
                    )
                receipt = BoardCandidateReceipt(
                    board_id=str(board.id),
                    candidate_version_id=str(candidate.id),
                    version_number=int(candidate.version_number),
                    revision=int(board.revision),
                    lifecycle_status=str(candidate.lifecycle_status),
                    xml_ref={
                        **dict(candidate.xml_ref),
                        "read_url": f"/api/boards/{board.id}/versions/{candidate.id}/xml",
                    },
                )
        return receipt

    async def accept_candidate(
        self,
        *,
        board_id: str,
        candidate_version_id: str,
        expected_board_revision: int,
        agent_run_id: str,
    ) -> BoardAcceptedReceipt:
        async with self.session_factory() as session:
            async with session.begin():
                domain = self._domain(session)
                version = await domain.accept_candidate(
                    board_id,
                    candidate_version_id=candidate_version_id,
                    expected_board_revision=expected_board_revision,
                    agent_run_id=agent_run_id,
                )
                board = await domain.get_board(board_id)
                receipt = self._accepted_receipt(board, version)
        return receipt

    async def load_candidate_for_render(
        self,
        *,
        session_id: str,
        board_id: str,
        candidate_version_id: str,
        agent_run_id: str,
    ) -> BoardRenderSource:
        async with self.session_factory() as session:
            async with session.begin():
                domain = self._domain(session)
                board = await domain.get_board(board_id)
                version = await domain.get_version(board_id, candidate_version_id)
                self._require_render_identity(board, version, session_id, agent_run_id)
                xml_path = version.xml_ref.get("local_path") or version.xml_ref.get("path")
                if not xml_path:
                    raise FileNotFoundError("board_version_xml_ref_missing")
                return BoardRenderSource(
                    board_id=str(board.id),
                    candidate_version_id=str(version.id),
                    title=str(board.title),
                    xml=Path(xml_path).read_text(encoding="utf-8"),
                    xml_ref={
                        **dict(version.xml_ref),
                        "read_url": f"/api/boards/{board.id}/versions/{version.id}/xml",
                    },
                    lifecycle_status=str(version.lifecycle_status),
                    quality_status=str(version.quality_status),
                    quality_report=dict(version.quality_report or {}),
                    screenshot_ref=dict(version.screenshot_ref) if version.screenshot_ref else None,
                )

    async def complete_candidate_render(
        self,
        *,
        session_id: str,
        board_id: str,
        candidate_version_id: str,
        agent_run_id: str,
        quality_status: str,
        quality_report: dict[str, Any],
        screenshot_ref: dict[str, Any] | None,
    ) -> BoardRenderReceipt:
        async with self.session_factory() as session:
            async with session.begin():
                domain = self._domain(session)
                board = await domain.get_board(board_id)
                version = await domain.get_version(board_id, candidate_version_id)
                self._require_render_identity(board, version, session_id, agent_run_id)
                version = await domain.complete_candidate_render(
                    board_id,
                    candidate_version_id=candidate_version_id,
                    agent_run_id=agent_run_id,
                    quality_status=quality_status,
                    quality_report=quality_report,
                    screenshot_ref=screenshot_ref,
                )
                return BoardRenderReceipt(
                    board_id=str(board.id),
                    candidate_version_id=str(version.id),
                    lifecycle_status=str(version.lifecycle_status),
                    quality_status=str(version.quality_status),
                    quality_report=dict(version.quality_report or {}),
                    screenshot_ref=dict(version.screenshot_ref) if version.screenshot_ref else None,
                )

    async def load_session_board(
        self,
        session_id: str,
        *,
        legacy_title: str | None = None,
        legacy_xml: str | None = None,
    ) -> BoardSnapshot | None:
        async with self.session_factory() as session:
            async with session.begin():
                domain = self._domain(session)
                board = await domain.get_board_for_session(session_id)
                if board is None and legacy_xml:
                    board = await domain.import_legacy(
                        session_id,
                        title=legacy_title or "Draw.io Board",
                        xml=legacy_xml,
                    )
                if board is None:
                    return None
                version = await domain.get_latest_restorable_version(board)
                if version is None:
                    return None
                xml_path = version.xml_ref.get("local_path") or version.xml_ref.get("path")
                if not xml_path:
                    raise FileNotFoundError("board_version_xml_ref_missing")
                xml = Path(xml_path).read_text(encoding="utf-8")
                snapshot = BoardSnapshot(
                    board_id=str(board.id),
                    session_id=str(board.session_id),
                    title=str(board.title),
                    revision=int(board.revision),
                    version_id=str(version.id),
                    current_version_id=(
                        str(board.current_version_id) if board.current_version_id else None
                    ),
                    version_number=int(version.version_number),
                    lifecycle_status=str(version.lifecycle_status),
                    xml=xml,
                    xml_sha256=str(version.xml_sha256),
                    quality_status=str(version.quality_status),
                    quality_report=dict(version.quality_report or {}),
                    screenshot_ref=dict(version.screenshot_ref) if version.screenshot_ref else None,
                    updated_at=board.updated_at.isoformat() if board.updated_at else None,
                )
        return snapshot

    async def resolve_context_reference(
        self,
        board_context: dict[str, Any] | None,
        *,
        expected_session_id: str | None,
    ) -> dict[str, Any]:
        """Resolve a compact board reference without exposing an ORM session."""
        async with self.session_factory() as session:
            async with session.begin():
                resolved = await resolve_board_context_reference(
                    session,
                    board_context,
                    expected_session_id=expected_session_id,
                )
        return resolved

    @staticmethod
    def _accepted_receipt(board: Board, version: BoardVersion) -> BoardAcceptedReceipt:
        return BoardAcceptedReceipt(
            board_id=str(board.id),
            version_id=str(version.id),
            version_number=int(version.version_number),
            revision=int(board.revision),
            title=str(board.title),
            lifecycle_status=str(version.lifecycle_status),
            xml_ref={
                **dict(version.xml_ref),
                "read_url": f"/api/boards/{board.id}/versions/{version.id}/xml",
            },
            screenshot_ref=dict(version.screenshot_ref) if version.screenshot_ref else None,
            quality_status=str(version.quality_status),
            quality_report=dict(version.quality_report or {}),
        )

    @staticmethod
    def _require_render_identity(
        board: Board,
        version: BoardVersion,
        session_id: str,
        agent_run_id: str,
    ) -> None:
        if (
            str(board.session_id) != str(session_id)
            or str(version.agent_run_id or "") != str(agent_run_id)
            or str(version.lifecycle_status) not in {"candidate", "accepted"}
        ):
            raise InvalidBoardCandidate(str(version.id))
