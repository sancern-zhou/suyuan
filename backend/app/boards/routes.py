from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.db.database import get_db
from app.utils.path_config import get_data_registry

from .models import Board, BoardVersion
from .service import (
    BoardNotFound,
    BoardVersionConflict,
    BoardVersionNotFound,
    BoardVersionService,
)


router = APIRouter(prefix="/api/boards", tags=["drawio-boards"])


class DraftRequest(BaseModel):
    xml: str = Field(min_length=1)


class ManualVersionRequest(BaseModel):
    base_revision: int = Field(ge=0)
    xml: str = Field(min_length=1)
    xml_sha256: str | None = None
    source_version_id: str | None = None


def get_board_artifact_root() -> Path:
    return get_data_registry() / "drawio_boards"


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _xml_ref_with_read_url(xml_ref: dict[str, Any] | None, read_url: str) -> dict[str, Any] | None:
    if not xml_ref:
        return xml_ref
    return {**xml_ref, "read_url": read_url}


def serialize_version(version: BoardVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "version_id": version.id,
        "board_id": version.board_id,
        "version_number": version.version_number,
        "parent_version_id": version.parent_version_id,
        "restored_from_version_id": version.restored_from_version_id,
        "source": version.source,
        "lifecycle_status": version.lifecycle_status,
        "xml_ref": _xml_ref_with_read_url(
            version.xml_ref,
            f"/api/boards/{version.board_id}/versions/{version.id}/xml",
        ),
        "xml_sha256": version.xml_sha256,
        "screenshot_ref": version.screenshot_ref,
        "quality_status": version.quality_status,
        "quality_report": version.quality_report or {},
        "agent_run_id": version.agent_run_id,
        "summary": version.summary,
        "created_at": _timestamp(version.created_at),
        "accepted_at": _timestamp(version.accepted_at),
    }


def serialize_board(board: Board) -> dict[str, Any]:
    return {
        "board_id": board.id,
        "session_id": board.session_id,
        "title": board.title,
        "current_version_id": board.current_version_id,
        "revision": board.revision,
        "draft_revision": board.draft_revision,
        "draft_xml_ref": _xml_ref_with_read_url(
            board.draft_xml_ref,
            f"/api/boards/{board.id}/draft/xml",
        ),
        "draft_sha256": board.draft_sha256,
        "updated_at": _timestamp(board.updated_at),
    }


async def _authorized_service(
    board_id: str,
    *,
    db: AsyncSession,
    artifact_root: Path,
    catalog: ConversationCatalogService,
    user: CurrentUser,
    write: bool,
) -> tuple[BoardVersionService, Board]:
    service = BoardVersionService(db, storage_root=artifact_root)
    try:
        board = await service.get_board(board_id)
    except BoardNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    checker = catalog.require_write if write else catalog.require_read
    await checker(board.session_id, user)
    return service, board


def _raise_version_error(exc: Exception) -> None:
    if isinstance(exc, BoardVersionConflict):
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "current_revision": exc.current_revision},
        ) from exc
    if isinstance(exc, (BoardNotFound, BoardVersionNotFound)):
        raise HTTPException(status_code=404, detail=exc.code) from exc
    raise exc


@router.put("/{board_id}/draft")
async def save_board_draft(
    board_id: str,
    request: DraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, _ = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=True
    )
    board = await service.save_draft(board_id, xml=request.xml)
    return serialize_board(board)


@router.post("/{board_id}/versions/manual")
async def commit_manual_board_version(
    board_id: str,
    request: ManualVersionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, _ = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=True
    )
    try:
        version = await service.commit_manual(
            board_id,
            base_revision=request.base_revision,
            xml=request.xml,
            source_version_id=request.source_version_id,
        )
        board = await service.get_board(board_id)
    except Exception as exc:
        _raise_version_error(exc)
    return {**serialize_board(board), "version": serialize_version(version)}


@router.get("/{board_id}/versions")
async def list_board_versions(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, board = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=False
    )
    versions = await service.list_versions(board_id)
    return {**serialize_board(board), "versions": [serialize_version(item) for item in versions]}


@router.get("/{board_id}/versions/{version_id}")
async def get_board_version(
    board_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, board = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=False
    )
    try:
        version = await service.get_version(board_id, version_id)
    except Exception as exc:
        _raise_version_error(exc)
    return {**serialize_board(board), "version": serialize_version(version)}


@router.get("/{board_id}/versions/{version_id}/xml", response_class=PlainTextResponse)
async def get_board_version_xml(
    board_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, _ = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=False
    )
    try:
        xml = await service.read_version_xml(board_id, version_id)
    except Exception as exc:
        _raise_version_error(exc)
    if xml is None:
        raise HTTPException(status_code=404, detail="board_xml_not_found")
    return PlainTextResponse(xml, media_type="application/xml")


@router.get("/{board_id}/draft/xml", response_class=PlainTextResponse)
async def get_board_draft_xml(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    artifact_root: Path = Depends(get_board_artifact_root),
):
    service, _ = await _authorized_service(
        board_id, db=db, artifact_root=artifact_root, catalog=catalog, user=user, write=False
    )
    xml = await service.read_draft_xml(board_id)
    if xml is None:
        raise HTTPException(status_code=404, detail="board_draft_not_found")
    return PlainTextResponse(xml, media_type="application/xml")
