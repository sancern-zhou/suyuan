"""Staged API contract for the Jiangsu smart-event center."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin_user, require_current_user
from app.auth.models import CurrentUser
from app.services.jiangsu_smart_event import JiangsuSmartEventService, SmartEventUpstreamError

router = APIRouter(prefix="/api/jiangsu/smart-events", tags=["jiangsu-smart-events"])


class SmartEventConfigRequest(BaseModel):
    values: dict = Field(default_factory=dict)


class SmartEventTaskRequest(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=120)


class SmartEventOperationRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    details: dict[str, Any] = Field(default_factory=dict)


class SmartEventDispatchOrderRequest(BaseModel):
    order_type: str | None = Field(default=None, max_length=120)
    assignee: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)


class SmartEventFeedbackRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=8000)
    attachments: list[str] = Field(default_factory=list)


def _default_times() -> tuple[str, str]:
    end = datetime.now().astimezone()
    return (end - timedelta(hours=24)).isoformat(), end.isoformat()


@router.get("")
async def list_smart_events(
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    station_code: list[str] | None = Query(default=None),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    event_type: str | None = Query(default=None),
    refresh: bool = Query(default=True),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    default_start, default_end = _default_times()
    try:
        return await JiangsuSmartEventService().list_events(
            start_time=start_time or default_start,
            end_time=end_time or default_end,
            station_codes=station_code,
            status=status,
            keyword=keyword,
            limit=limit,
            refresh=refresh,
            page=page,
            summary=True,
            event_type=event_type,
        )
    except SmartEventUpstreamError as exc:
        raise HTTPException(status_code=502, detail={"code": "smart_event_upstream_unavailable", "message": str(exc)}) from exc


@router.post("/sync")
async def sync_smart_events(
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    station_code: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    wait_for_ai: bool = Query(default=False, description="是否等待事件 Agent 完成并回写详情"),
    dispatch_ai: bool = Query(default=False, description="是否将待执行事件发布到事件驱动 Agent；事件中心展示阶段默认关闭"),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    default_start, default_end = _default_times()
    try:
        result = await JiangsuSmartEventService().sync_alarm_events(
            start_time=start_time or default_start,
            end_time=end_time or default_end,
            station_codes=station_code,
            actor={"user_id": user.id, "username": user.username},
            limit=limit,
            wait_for_ai=wait_for_ai,
            dispatch_ai=dispatch_ai,
        )
    except SmartEventUpstreamError as exc:
        raise HTTPException(status_code=502, detail={"code": "smart_event_upstream_unavailable", "message": str(exc)}) from exc
    return {"status": "synced", **result}


@router.get("/config/current")
async def get_smart_event_config(
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    return {"config": service.load_config(), "source": "local_fallback", "platform_config_api": False}


@router.put("/config/current")
async def save_smart_event_config(
    request: SmartEventConfigRequest,
    user: CurrentUser = Depends(require_admin_user),
) -> dict:
    service = JiangsuSmartEventService()
    return {"config": service.save_config(request.values), "source": "local_fallback", "platform_config_api": False}


@router.get("/tasks")
async def list_smart_event_tasks(
    event_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    tasks = JiangsuSmartEventService().list_tasks(event_id=event_id, status=status, limit=limit)
    return {"tasks": tasks, "total": len(tasks), "source": "alarm_adapter_store"}


@router.get("/tasks/{task_id}")
async def get_smart_event_task(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    task = JiangsuSmartEventService().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="smart_event_task_not_found")
    return {"task": task}


@router.get("/{event_id}")
async def get_smart_event(
    event_id: str,
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    default_start, default_end = _default_times()
    try:
        event = await JiangsuSmartEventService().get_event(
            event_id,
            start_time=start_time or default_start,
            end_time=end_time or default_end,
            limit=100,
        )
    except SmartEventUpstreamError as exc:
        raise HTTPException(status_code=502, detail={"code": "smart_event_upstream_unavailable", "message": str(exc)}) from exc
    if event is None:
        raise HTTPException(status_code=404, detail="smart_event_not_found")
    return {"event": event}


@router.post("/{event_id}/evidence")
async def collect_smart_event_evidence(
    event_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    """Collect the event-specific evidence package without dispatching AI."""
    try:
        result = await JiangsuSmartEventService().collect_event_evidence(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    return {"status": "collected", **result}


@router.post("/evidence/collect")
async def collect_all_smart_event_evidence(
    limit: int = Query(default=100, ge=1, le=1000),
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    """Collect packages for all currently uncollected events; AI is untouched."""
    return {"status": "collected", **await JiangsuSmartEventService().collect_all_event_evidence(limit=limit)}


@router.post("/{event_id}/operations")
async def record_smart_event_operation(
    event_id: str,
    request: SmartEventOperationRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    try:
        record = service.record_operation(
            event_id,
            action=request.action,
            summary=request.summary,
            details=request.details,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"operation": record}


@router.post("/{event_id}/dispatch-order")
async def dispatch_smart_event_order(
    event_id: str,
    request: SmartEventDispatchOrderRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    """提交派单处置：事件状态更新为“派单处置中”。"""
    service = JiangsuSmartEventService()
    try:
        event = service.dispatch_order(
            event_id,
            title=request.title,
            order_type=request.order_type,
            assignee=request.assignee,
            description=request.description,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"event": event}


@router.post("/{event_id}/feedback")
async def submit_smart_event_feedback(
    event_id: str,
    request: SmartEventFeedbackRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    """记录事件反馈，并以增量对话继续上一轮 AI 研判（结论替换）。

    在 Web 进程该请求由 ``JiangsuSmartEventWorkerProxyMiddleware`` 代理到
    worker 执行，确保反馈触发的增量研判能真正派发。
    """
    service = JiangsuSmartEventService()
    try:
        result = await service.submit_feedback(
            event_id,
            feedback=request.feedback,
            attachments=request.attachments,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "feedback_recorded", **result}


@router.post("/{event_id}/tasks")
async def create_smart_event_task(
    event_id: str,
    request: SmartEventTaskRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    try:
        result = await service.run_ai_judgment(
            event_id,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    task = result["task"]
    if request and request.conversation_id:
        task["conversation_id"] = request.conversation_id
        store = service._load_store()
        for item in store.get("tasks", []):
            if item.get("task_id") == task["task_id"]:
                item["conversation_id"] = request.conversation_id
        service._save_store(store)
    result["task"] = service.get_task(task["task_id"]) or task
    return result


@router.post("/{event_id}/ai-dispatch")
async def dispatch_smart_event_ai_judgment(
    event_id: str,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    """Manually start one event's AI task from the event center."""
    service = JiangsuSmartEventService()
    try:
        return {
            "status": "dispatched",
            **await service.run_ai_judgment(
                event_id,
                actor={"user_id": user.id, "username": user.username},
            ),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
