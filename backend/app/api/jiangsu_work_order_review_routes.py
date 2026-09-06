"""Human archive endpoints for Jiangsu fault work-order SOP reviews."""

from __future__ import annotations

import mimetypes
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services.jiangsu_work_order_review import (
    REVIEW_SCENARIO,
    load_review_evidence,
    load_review,
    mark_human_review,
)
from app.utils.path_config import get_data_registry, is_path_within, resolve_agent_path

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/jiangsu/work-order-reviews", tags=["jiangsu-work-order-reviews"])

IMAGE_MEDIA_TYPE_ALIASES = {
    "application/jpg": "image/jpeg",
    "application/jpeg": "image/jpeg",
    "application/pjpeg": "image/jpeg",
    "application/x-jpg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "application/png": "image/png",
    "application/gif": "image/gif",
    "application/webp": "image/webp",
    "application/bmp": "image/bmp",
}


class ReviewArchiveRequest(BaseModel):
    final_work_order_decision: Literal["approve", "reject", "needs_evidence"] | None = None
    data_impact: list[dict[str, Any]] | None = None
    exclusion_required: bool | None = None
    exclusion_intervals: list[dict[str, Any]] | None = None
    review_comment: str | None = Field(default=None, max_length=2000)


class ReviewStateRequest(ReviewArchiveRequest):
    reason: str | None = Field(default=None, max_length=2000)


def _actor(user: CurrentUser) -> dict[str, Any]:
    return {"user_id": user.id, "username": user.username}


def _feedback_decision(action: str, review: dict[str, Any]) -> str:
    if review.get('final_work_order_decision') == 'reject':
        return "rejected"
    return 'modified' if (review.get('human_feedback') or {}).get('differences') else 'accepted'


def _record_feedback(
    *,
    action: str,
    review: dict[str, Any],
    previous: dict[str, Any],
    user: CurrentUser,
) -> None:
    try:
        from app.services.jiangsu_feedback_loop import get_feedback_loop_store

        get_feedback_loop_store().human_review(
            case_id=review.get("feedback_case_id")
            or f"fault_work_order_review:{review.get('work_order_code')}",
            scenario=REVIEW_SCENARIO,
            decision=_feedback_decision(action, review),
            actor_id=str(user.id),
            source_record_id=review.get("review_id"),
            payload={
                "review_id": review.get("review_id"),
                "work_order_code": review.get("work_order_code"),
                "previous_decision": previous.get("work_order_decision"),
                "final_decision": review.get("final_work_order_decision"),
                "exclusion_required": review.get("exclusion_required"),
                "confirmed_interval_count": len(review.get("final_exclusion_intervals") or []),
                "human_feedback": review.get('human_feedback'),
            },
        )
    except Exception as exc:
        logger.warning(
            "jiangsu_work_order_review_feedback_failed",
            review_id=review.get("review_id"),
            error=str(exc),
        )


def _iter_detail_rows(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    work_order = evidence.get("work_order") if isinstance(evidence, dict) else {}
    detail = work_order.get("detail") if isinstance(work_order, dict) else {}
    rows = detail.get("data") if isinstance(detail, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _iter_attachments(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for row in _iter_detail_rows(evidence):
        row_attachments = row.get("attachments")
        if not isinstance(row_attachments, list):
            continue
        for attachment in row_attachments:
            if isinstance(attachment, dict):
                attachments.append(attachment)
    return attachments


def _augment_attachment_urls(review_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return evidence
    for index, attachment in enumerate(_iter_attachments(evidence)):
        content_url = f"/api/jiangsu/work-order-reviews/{review_id}/attachments/{index}/content"
        attachment["content_url"] = content_url
        attachment["download_url"] = content_url
        attachment["preview_url"] = content_url
    return evidence


def _normalise_attachment_media_type(raw_media_type: object, filename: str) -> str:
    raw = str(raw_media_type or "").split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_type(filename)[0]
    if raw in IMAGE_MEDIA_TYPE_ALIASES:
        return IMAGE_MEDIA_TYPE_ALIASES[raw]
    if raw in {"", "application/octet-stream", "binary/octet-stream"}:
        return guessed or "application/octet-stream"
    if raw.startswith("application/") and guessed and guessed.startswith("image/"):
        subtype = raw.rsplit("/", 1)[-1]
        if subtype in {"png", "jpg", "jpeg", "pjpeg", "gif", "webp", "bmp"}:
            return guessed
    return raw


@router.get("/{review_id}")
async def get_work_order_review(
    review_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    review = load_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="work_order_review_not_found")
    return {"review": review}


@router.get("/{review_id}/evidence")
async def get_work_order_review_evidence(
    review_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    try:
        evidence = load_review_evidence(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if evidence is None:
        raise HTTPException(status_code=404, detail="work_order_review_evidence_not_found")
    return {"evidence": _augment_attachment_urls(review_id, evidence)}


@router.get("/{review_id}/attachments/{attachment_index}/content")
async def get_work_order_review_attachment_content(
    review_id: str,
    attachment_index: int,
    user: CurrentUser = Depends(require_current_user),
) -> FileResponse:
    try:
        evidence = load_review_evidence(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if evidence is None:
        raise HTTPException(status_code=404, detail="work_order_review_evidence_not_found")
    attachments = _iter_attachments(evidence)
    if attachment_index < 0 or attachment_index >= len(attachments):
        raise HTTPException(status_code=404, detail="attachment_not_found")
    attachment = attachments[attachment_index]
    local_path = str(attachment.get("local_path") or "").strip()
    if not local_path:
        raise HTTPException(status_code=404, detail="attachment_content_unavailable")
    target = resolve_agent_path(local_path)
    if not target.is_file() or not is_path_within(target, [get_data_registry()]):
        raise HTTPException(status_code=404, detail="attachment_content_missing")
    filename = str(attachment.get("fileName") or target.name).strip() or target.name
    media_type = _normalise_attachment_media_type(attachment.get("content_type"), filename)
    return FileResponse(
        path=target,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/{review_id}/confirm")
async def confirm_work_order_review(
    review_id: str,
    request: ReviewArchiveRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    previous = load_review(review_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="work_order_review_not_found")
    try:
        review = mark_human_review(
            review_id,
            action="confirm",
            actor=_actor(user),
            payload=request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_feedback(action="confirm", review=review, previous=previous, user=user)
    return {"status": review["status"], "review": review}


@router.post("/{review_id}/needs-evidence")
async def request_work_order_review_evidence(
    review_id: str,
    request: ReviewStateRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    previous = load_review(review_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="work_order_review_not_found")
    try:
        review = mark_human_review(
            review_id,
            action="needs_evidence",
            actor=_actor(user),
            payload=request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_feedback(action="needs_evidence", review=review, previous=previous, user=user)
    return {"status": review["status"], "review": review}


@router.post("/{review_id}/reject")
async def reject_work_order_review(
    review_id: str,
    request: ReviewStateRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    previous = load_review(review_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="work_order_review_not_found")
    try:
        review = mark_human_review(
            review_id,
            action="reject",
            actor=_actor(user),
            payload=request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_feedback(action="reject", review=review, previous=previous, user=user)
    return {"status": review["status"], "review": review}
