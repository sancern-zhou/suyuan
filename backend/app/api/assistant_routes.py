"""Authenticated Web views of the shared assistant's personal matters and choices."""

from typing import Annotated, Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations import ConversationSource
from app.conversations.dependencies import get_conversation_catalog
from app.social.assistant_coaching import AssistantCoachingService
from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_request import require_assistant_request
from app.social.assistant_tasks import AssistantTaskService, TaskConflict, TaskNotFound
from app.social.web_assistant import web_assistant_request
from config.settings import settings

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def task_service():
    return AssistantTaskService()


def coaching_service():
    return AssistantCoachingService()


def followup_service():
    return AssistantFollowupService()


AuthenticatedUser = Annotated[CurrentUser, Depends(require_current_user)]
Tasks = Annotated[AssistantTaskService, Depends(task_service)]
Coaching = Annotated[AssistantCoachingService, Depends(coaching_service)]
Followups = Annotated[AssistantFollowupService, Depends(followup_service)]
Catalog = Annotated[object, Depends(get_conversation_catalog)]


async def result(awaitable):
    try:
        return await awaitable
    except HTTPException:
        raise
    except TaskNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except TaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        structlog.get_logger(__name__).exception("web_assistant_operation_failed")
        raise HTTPException(503, "助理服务暂不可用，请稍后重试") from exc


@router.get("/tasks")
async def tasks(
    user: AuthenticatedUser,
    service: Tasks,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    return {
        "tasks": await result(
            service.list(settings.project_id, user.id, limit=limit, offset=offset)
        )
    }


@router.get("/tasks/{task_id}")
async def task(task_id: str, user: AuthenticatedUser, service: Tasks):
    return {"task": await result(service.get(settings.project_id, user.id, task_id))}


@router.get("/suggestions")
async def suggestions(
    user: AuthenticatedUser,
    service: Coaching,
    state: Literal["pending", "accepted", "dismissed", "all"] = "pending",
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    return {
        "suggestions": await result(
            service.list(settings.project_id, user.id, state=state, limit=limit, offset=offset)
        )
    }


class TaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    action: Literal["feedback", "resume", "complete", "cancel", "stop_followups"]
    text: str = Field(default="", max_length=20000)


async def _source(catalog, user, session_id):
    row = await catalog.require_write(session_id, user)
    # Admin read privileges are not authority to operate another user's assistant.
    if row.owner_user_id != user.id or row.source != ConversationSource.WEB:
        raise HTTPException(404, "session_not_found")
    return row


def _available(name):
    from app.agent.prompts.tool_registry import get_tools_by_mode
    from app.tools import global_tool_registry

    if (
        name not in get_tools_by_mode("assistant")
        or global_tool_registry.get_tool_status(name) != "enabled"
    ):
        raise HTTPException(403, "当前项目未开放此助理操作")


@router.post("/tasks/{task_id}/actions")
async def task_action(
    task_id: str,
    payload: TaskAction,
    user: AuthenticatedUser,
    service: Tasks,
    followups: Followups,
    catalog: Catalog,
):
    _available("manage_assistant_tasks")
    stored = await result(service.get(settings.project_id, user.id, task_id))
    await result(_source(catalog, user, stored["source_session_id"]))
    if payload.action in {"feedback", "complete"} and not payload.text.strip():
        raise HTTPException(400, "请填写反馈或完成依据")
    message = f"Web 用户操作：{payload.action}；事项 {task_id}。\n{payload.text}"
    with web_assistant_request(stored["source_session_id"], user, message, uuid4().hex):
        request = require_assistant_request(stored["source_session_id"])
        if payload.action == "stop_followups":
            return await result(
                followups.disable(
                    settings.project_id,
                    user.id,
                    task_id,
                    request,
                    expected_version=payload.expected_version,
                )
            )
        fields = {}
        if payload.action == "complete":
            fields["result_summary"] = payload.text.strip()
        elif payload.action == "resume":
            fields["next_step"] = payload.text.strip() or "用户要求继续推进事项"
        return {
            "task": await result(
                service.change(
                    settings.project_id,
                    user.id,
                    task_id,
                    request,
                    expected_version=payload.expected_version,
                    action=payload.action,
                    **fields,
                )
            )
        }


class SuggestionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    action: Literal["accept", "dismiss"]


@router.post("/suggestions/{suggestion_id}/actions")
async def suggestion_action(
    suggestion_id: str,
    payload: SuggestionAction,
    user: AuthenticatedUser,
    service: Coaching,
    catalog: Catalog,
):
    # An exact owner-scoped lookup avoids accepting arbitrary sessions supplied by a client.
    from app.social.assistant_coaching_models import AssistantSuggestionDB

    _available("manage_assistant_coaching")

    async def apply():
        async with service.session_factory() as session:
            row = (
                await session.execute(
                    select(AssistantSuggestionDB).where(
                        *service._scope(settings.project_id, user.id),
                        AssistantSuggestionDB.suggestion_id == suggestion_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "suggestion_not_found")
            session_id = row.source_session_id
        await _source(catalog, user, session_id)
        with web_assistant_request(
            session_id, user, f"Web 用户{payload.action}建议 {suggestion_id}", uuid4().hex
        ):
            return await service.decide(
                settings.project_id,
                user.id,
                require_assistant_request(session_id),
                suggestion_id=suggestion_id,
                expected_version=payload.expected_version,
                action=payload.action,
            )

    return await result(apply())


@router.get("/notifications")
async def notifications(
    user: AuthenticatedUser,
    service: Tasks,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
):
    from app.social.assistant_notifications import AssistantNotificationService

    return await result(AssistantNotificationService(service.session_factory).list(
        settings.project_id, user.id, limit=limit, offset=offset, unread_only=unread_only,
    ))


@router.post("/notifications/{message_id}/read")
async def read_notification(message_id: str, user: AuthenticatedUser, service: Tasks):
    from app.social.assistant_notifications import AssistantNotificationService

    await result(AssistantNotificationService(service.session_factory).mark_read(settings.project_id, user.id, message_id))
    return {"success": True}
