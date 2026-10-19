"""Worker-side plan controls, shared by the assistant's single scheduling tool."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import require_current_user
from app.auth.internal_identity import INTERNAL_USER_HEADER
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.social.assistant_plans import AssistantPlanService, PlanCommand
from app.social.assistant_request import AssistantRequest
from app.social.assistant_tasks import TaskConflict, TaskNotFound
from config.settings import settings

router = APIRouter()


class PlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: PlanCommand
    source_session_id: str
    request_id: str | None = None
    user_message: str | None = None
    delivery_user_id: str | None = None


def plan_service():
    return AssistantPlanService()


@router.post("/assistant-schedule")
async def assistant_schedule(
    body: PlanEnvelope,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    service: Annotated[AssistantPlanService, Depends(plan_service)],
):
    secret = settings.social_worker_internal_token
    if not request.headers.get(INTERNAL_USER_HEADER) or (
        secret and not hmac.compare_digest(request.headers.get("x-social-worker-token", ""), secret)
    ):
        raise HTTPException(403, "仅允许已认证的内部助手请求")
    source = await get_conversation_catalog().find(body.source_session_id)
    if source is None or source.owner_user_id != user.id:
        raise HTTPException(404, "会话不存在或无权访问")
    human_request = None
    if body.command.action not in {"list", "get", "history", "results"}:
        if not body.request_id or not body.user_message or not body.user_message.strip():
            raise HTTPException(403, "计划变更需要当前用户交办")
        from app.conversations import ConversationSource

        recipient = body.delivery_user_id
        if source.source == ConversationSource.WEB:
            from app.social.web_assistant import web_assistant_recipient

            recipient = web_assistant_recipient(user.id)
        human_request = AssistantRequest(
            body.source_session_id, body.request_id, body.user_message, recipient
        )
    try:
        return await service.dispatch(settings.project_id, user, body.command, human_request)
    except TaskNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except TaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        import structlog

        structlog.get_logger(__name__).exception("assistant_schedule_failed")
        raise HTTPException(503, "调度服务暂不可用；请查询计划后再决定是否重试") from exc
