from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .service import BoardNotFound, BoardVersionConflict, BoardVersionService


async def resolve_board_context_reference(
    session: AsyncSession,
    board_context: dict[str, Any] | None,
    *,
    expected_session_id: str | None,
) -> dict[str, Any]:
    context = dict(board_context or {})
    board_id = str(context.get("board_id") or context.get("active_board_id") or "").strip()
    version_id = str(context.get("version_id") or context.get("current_version_id") or "").strip()
    if not board_id or not version_id:
        return context
    if not expected_session_id:
        raise BoardNotFound(board_id)

    service = BoardVersionService(session)
    board = await service.get_board(board_id)
    if expected_session_id and board.session_id != expected_session_id:
        raise BoardNotFound(board_id)
    requested_revision = int(context.get("revision") or 0)
    if board.revision != requested_revision:
        raise BoardVersionConflict(board.revision)
    version = await service.get_version(board.id, version_id)
    # A candidate is a valid continuation state even though it has not been
    # promoted to board.current_version_id yet. This is required for a
    # follow-up turn after candidate generation; treating it as a stale
    # current version incorrectly produced HTTP 409.
    if board.current_version_id != version_id and version.lifecycle_status != "candidate":
        raise BoardVersionConflict(board.revision)
    path_value = version.xml_ref.get("local_path") or version.xml_ref.get("path")
    if not path_value:
        raise FileNotFoundError("board_version_xml_ref_missing")
    xml = Path(path_value).read_text(encoding="utf-8")
    return {
        **context,
        "artifact_kind": "drawio_board",
        "board_id": board.id,
        "active_board_id": board.id,
        "title": board.title,
        "current_xml": xml,
        "xml": xml,
        "current_version_id": version.id,
        "version_id": version.id,
        "version": version.version_number,
        "revision": board.revision,
        "lifecycle_status": version.lifecycle_status,
        "xml_sha256": version.xml_sha256,
    }
