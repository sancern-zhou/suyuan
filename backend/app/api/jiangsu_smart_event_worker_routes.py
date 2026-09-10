"""Worker-only endpoints for Jiangsu smart-event AI dispatch and feedback."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.services.jiangsu_smart_event import JiangsuSmartEventService

router = APIRouter(
    prefix="/internal/jiangsu/smart-events",
    tags=["jiangsu-smart-event-worker"],
)
logger = structlog.get_logger()


class WorkerFeedbackRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=8000)
    attachments: list[str] = Field(default_factory=list)


@router.post("/{event_id}/ai-dispatch")
async def dispatch_jiangsu_smart_event_ai_on_worker(
    event_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
) -> dict:
    """Run the dispatch in the worker process that owns ScheduledTaskService."""
    logger.info(
        "jiangsu_smart_event_worker_dispatch_started",
        event_id=event_id,
        user_id=user.id,
    )
    service = JiangsuSmartEventService()
    try:
        result = {
            "status": "dispatched",
            **await service.run_ai_judgment(
                event_id,
                actor={"user_id": user.id, "username": user.username},
            ),
        }
        logger.info(
            "jiangsu_smart_event_worker_dispatch_accepted",
            event_id=event_id,
            dispatches=result.get("dispatches"),
        )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc


@router.post("/{event_id}/feedback")
async def submit_jiangsu_smart_event_feedback_on_worker(
    event_id: str,
    request: WorkerFeedbackRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
) -> dict:
    """Record feedback and dispatch the incremental judgment in the worker."""
    logger.info(
        "jiangsu_smart_event_worker_feedback_started",
        event_id=event_id,
        user_id=user.id,
    )
    service = JiangsuSmartEventService()
    try:
        result = await service.submit_feedback(
            event_id,
            feedback=request.feedback,
            attachments=request.attachments,
            actor={"user_id": user.id, "username": user.username},
        )
        logger.info(
            "jiangsu_smart_event_worker_feedback_accepted",
            event_id=event_id,
            dispatches=result.get("dispatches"),
        )
        return {"status": "feedback_recorded", **result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
