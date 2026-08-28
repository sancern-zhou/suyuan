"""Human-confirmation endpoints for Jiangsu fault work-order drafts.

The Agent creates a pending draft via ``jiangsu_prepare_fault_work_order``;
these routes power the right-side preview panel: an authenticated operator
reviews, edits the whitelisted fields, and confirms — only then is the work
order created on the Suncere operations platform.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.tools.jiangsu.work_order_dispatch import (
    audit_event,
    create_fault_work_order_on_platform,
    load_draft,
    resolve_created_order_code,
    save_draft,
    validate_edits,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/jiangsu/work-order-drafts", tags=["jiangsu-work-orders"])


class WorkOrderEdits(BaseModel):
    order_title: str | None = None
    order_content: str | None = None
    fault_description: str | None = None
    remediation_plan: str | None = None
    verification_standards: list[str] | None = Field(default=None, max_length=8)
    urgency: str | None = None
    device_id: int | None = None
    fault_content_ids: list[str] | None = Field(default=None, min_length=1)
    plan_finish_time: str | None = None


class ConfirmWorkOrderRequest(BaseModel):
    edits: WorkOrderEdits


class VerificationRequest(BaseModel):
    """Business-result callback used by the pilot feedback loop."""

    outcome: Literal["resolved", "completed", "passed", "not_resolved", "failed", "reopened"]
    details: dict[str, Any] = Field(default_factory=dict)
    source_record_id: str | None = None


class WorkflowReviewRequest(BaseModel):
    """Record a workflow decision, not a subjective Agent rating."""

    scenario: str
    decision: Literal["accepted", "modified", "rejected", "needs_evidence"]
    payload: dict[str, Any] = Field(default_factory=dict)
    source_record_id: str | None = None


def _ensure_jiangsu_configured() -> None:
    from config.settings import settings

    if not settings.jiangsu_ops_api_base_url or not settings.jiangsu_ops_token_url:
        raise HTTPException(status_code=404, detail="jiangsu_work_order_not_configured")


def _load_pending_draft(draft_id: str) -> dict[str, Any]:
    _ensure_jiangsu_configured()
    draft = load_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="work_order_draft_not_found")
    if draft.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail={"reason": "work_order_draft_not_pending", "status": draft.get("status")},
        )
    expires_at = _parse_iso(draft.get("expires_at"))
    if expires_at is not None and expires_at < datetime.now().astimezone():
        raise HTTPException(status_code=409, detail={"reason": "work_order_draft_expired"})
    return draft


def _parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@router.post("/{draft_id}/confirm")
async def confirm_work_order_draft(
    draft_id: str,
    request: ConfirmWorkOrderRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    draft = _load_pending_draft(draft_id)
    try:
        final = validate_edits(draft, request.edits.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    feedback_case_id = draft.get("feedback_case_id")
    if not feedback_case_id:
        from app.services.jiangsu_feedback_loop import fault_case_id

        feedback_case_id = fault_case_id(draft.get("event_id") or "", draft_id)
    original = {field: draft.get(field) for field in request.edits.model_dump(exclude_none=True)}
    changed_fields = [
        field for field, value in request.edits.model_dump(exclude_none=True).items()
        if original.get(field) != value
    ]
    review_decision = "modified" if changed_fields else "accepted"
    try:
        from app.services.jiangsu_feedback_loop import get_feedback_loop_store

        get_feedback_loop_store().human_review(
            case_id=feedback_case_id,
            scenario="station_fault_diagnosis",
            decision=review_decision,
            actor_id=str(user.id),
            source_record_id=draft_id,
            payload={
                "draft_id": draft_id,
                "changed_fields": changed_fields,
                "final_fields": sorted(request.edits.model_dump(exclude_none=True)),
            },
        )
    except Exception as exc:
        logger.warning("jiangsu_feedback_human_review_record_failed", draft_id=draft_id, error=str(exc))

    station = draft.get("station") or {}
    now = datetime.now().astimezone()
    confirm_event = {
        "occurred_at": now.isoformat(),
        "action": "draft_confirmed",
        "draft_id": draft_id,
        "station_code": station.get("station_code"),
        "event_id": draft.get("event_id"),
        "device_id": final["device_id"],
        "order_title": final["order_title"],
        "confirmed_by": {"user_id": user.id, "username": user.username},
    }
    try:
        response = await create_fault_work_order_on_platform(
            final, str(station.get("station_code") or "")
        )
    except (ValueError, httpx.HTTPError) as exc:
        audit_event({**confirm_event, "action": "draft_confirm_failed", "error": str(exc)})
        try:
            from app.services.jiangsu_feedback_loop import get_feedback_loop_store

            get_feedback_loop_store().business_action(
                case_id=feedback_case_id,
                scenario="station_fault_diagnosis",
                action="create_fault_work_order",
                outcome="failed",
                source_record_id=draft_id,
                payload={"error": str(exc)},
            )
        except Exception as feedback_exc:
            logger.warning("jiangsu_feedback_action_record_failed", draft_id=draft_id, error=str(feedback_exc))
        logger.warning("jiangsu_work_order_create_failed", draft_id=draft_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"运维平台创建工单失败：{exc}") from exc

    accepted = response.get("result") is True or response.get("success") is not False
    if not accepted:
        message = str(response.get("msg") or response.get("message") or "平台未受理")
        audit_event({**confirm_event, "action": "draft_confirm_failed", "error": message})
        try:
            from app.services.jiangsu_feedback_loop import get_feedback_loop_store

            get_feedback_loop_store().business_action(
                case_id=feedback_case_id,
                scenario="station_fault_diagnosis",
                action="create_fault_work_order",
                outcome="failed",
                source_record_id=draft_id,
                payload={"error": message, "platform_response": response},
            )
        except Exception as feedback_exc:
            logger.warning("jiangsu_feedback_action_record_failed", draft_id=draft_id, error=str(feedback_exc))
        raise HTTPException(status_code=502, detail=f"运维平台未受理工单创建：{message}")

    work_order_code: str | None = None
    try:
        work_order_code = await resolve_created_order_code(
            unique_code=str(station.get("unique_code") or ""),
            order_title=final["order_title"],
            created_after=_parse_iso(draft.get("created_at")) or now,
        )
    except (ValueError, httpx.HTTPError) as exc:
        logger.info("jiangsu_work_order_code_resolve_failed", draft_id=draft_id, error=str(exc))

    draft.update({
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
        "confirmed_by": {"user_id": user.id, "username": user.username},
        "final": final,
        "result": {
            "accepted": True,
            "work_order_code": work_order_code,
            "platform_response": response,
        },
        "feedback_case_id": feedback_case_id,
    })
    save_draft(draft)
    audit_event({**confirm_event, "work_order_code": work_order_code})
    try:
        from app.services.jiangsu_feedback_loop import get_feedback_loop_store

        get_feedback_loop_store().business_action(
            case_id=feedback_case_id,
            scenario="station_fault_diagnosis",
            action="create_fault_work_order",
            outcome="created",
            source_record_id=work_order_code or draft_id,
            payload={
                "draft_id": draft_id,
                "work_order_code": work_order_code,
                "station_code": station.get("station_code"),
            },
        )
    except Exception as exc:
        logger.warning("jiangsu_feedback_action_record_failed", draft_id=draft_id, error=str(exc))
    return {
        "status": "confirmed",
        "work_order_code": work_order_code,
        "feedback_case_id": feedback_case_id,
        "draft": draft,
    }


@router.post("/{draft_id}/dismiss")
async def dismiss_work_order_draft(
    draft_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    draft = _load_pending_draft(draft_id)
    now = datetime.now().astimezone()
    draft.update({
        "status": "dismissed",
        "dismissed_at": now.isoformat(),
        "dismissed_by": {"user_id": user.id, "username": user.username},
    })
    save_draft(draft)
    audit_event({
        "occurred_at": now.isoformat(),
        "action": "draft_dismissed",
        "draft_id": draft_id,
        "station_code": (draft.get("station") or {}).get("station_code"),
        "dismissed_by": {"user_id": user.id, "username": user.username},
    })
    try:
        from app.services.jiangsu_feedback_loop import fault_case_id, get_feedback_loop_store

        case_id = draft.get("feedback_case_id") or fault_case_id(draft.get("event_id") or "", draft_id)
        get_feedback_loop_store().human_review(
            case_id=case_id,
            scenario="station_fault_diagnosis",
            decision="rejected",
            actor_id=str(user.id),
            source_record_id=draft_id,
            payload={"draft_id": draft_id, "reason": "dismissed"},
        )
    except Exception as exc:
        logger.warning("jiangsu_feedback_dismiss_record_failed", draft_id=draft_id, error=str(exc))
    return {"status": "dismissed", "draft": draft}


@router.post("/{draft_id}/verification")
async def verify_fault_work_order(
    draft_id: str,
    request: VerificationRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    """Record the downstream platform/field result for a fault case.

    The operations platform or a future reconciliation job can call the same
    service directly.  This endpoint is a small pilot adapter for the current
    human workflow and keeps the result tied to the original draft.
    """

    draft = load_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="work_order_draft_not_found")
    from app.services.jiangsu_feedback_loop import fault_case_id, get_feedback_loop_store

    case_id = draft.get("feedback_case_id") or fault_case_id(draft.get("event_id") or "", draft_id)
    try:
        event = get_feedback_loop_store().verification(
            case_id=case_id,
            scenario="station_fault_diagnosis",
            outcome=request.outcome,
            source_record_id=request.source_record_id or draft.get("result", {}).get("work_order_code") or draft_id,
            payload={
                "draft_id": draft_id,
                "work_order_code": draft.get("result", {}).get("work_order_code"),
                "details": request.details,
                "verified_by": {"user_id": user.id, "username": user.username},
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "recorded", "feedback_case_id": case_id, "event": event.model_dump(mode="json")}


@router.get("/feedback/cases")
async def list_workflow_feedback_cases(
    scenario: str | None = None,
    limit: int = 100,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    """List materialized workflow cases for the Jiangsu pilot."""

    from app.services.jiangsu_feedback_loop import get_feedback_loop_store

    cases = get_feedback_loop_store().list_cases(scenario=scenario, limit=limit)
    return {"cases": [case.model_dump(mode="json") for case in cases], "total": len(cases)}


@router.get("/feedback/metrics")
async def workflow_feedback_metrics(
    scenario: str | None = None,
    days: int = 30,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    """Return outcome-based pilot metrics, not conversation satisfaction."""

    from app.services.jiangsu_feedback_loop import get_feedback_loop_store

    return get_feedback_loop_store().metrics(scenario=scenario, days=days)


@router.post("/feedback/cases/{case_id}/review")
async def record_workflow_review(
    case_id: str,
    request: WorkflowReviewRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    """Record an audit/review decision from an existing business workflow.

    For operations audit, ``payload`` should include ``ai_item_ids`` and
    ``final_item_ids``.  These are compared by the metrics endpoint to obtain
    precision/recall against the human final issue list.
    """

    from app.services.jiangsu_feedback_loop import get_feedback_loop_store

    try:
        event = get_feedback_loop_store().human_review(
            case_id=case_id,
            scenario=request.scenario,
            decision=request.decision,
            actor_id=str(user.id),
            source_record_id=request.source_record_id,
            payload=request.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "recorded", "event": event.model_dump(mode="json")}


# Keep this catch-all draft lookup after the static feedback paths above;
# otherwise ``/feedback/cases`` would be interpreted as draft_id="feedback".
@router.get("/{draft_id}")
async def get_work_order_draft(
    draft_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict[str, Any]:
    _ensure_jiangsu_configured()
    draft = load_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="work_order_draft_not_found")
    return {"draft": draft}
