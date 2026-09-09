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


class SmartEventJudgmentRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    event_name: str | None = Field(default=None, max_length=240)
    level: str | None = Field(default=None, max_length=40)
    data_impact: Any = None
    diagnosis_note: str | None = Field(default=None, max_length=8000)
    confirmed: bool = False


class SmartEventOperationRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    details: dict[str, Any] = Field(default_factory=dict)


class SmartEventArchiveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


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
    limit: int = Query(default=100, ge=1, le=100),
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


@router.post("/{event_id}/ai-judgments")
async def submit_smart_event_judgment(
    event_id: str,
    request: SmartEventJudgmentRequest,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    try:
        event = service.submit_ai_judgment(
            event_id,
            request.model_dump(),
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"event": event}


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


@router.post("/{event_id}/archive")
async def archive_smart_event(
    event_id: str,
    request: SmartEventArchiveRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    try:
        event = service.archive_event(
            event_id,
            comment=request.comment if request else None,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"event": event}


@router.post("/{event_id}/tasks")
async def create_smart_event_task(
    event_id: str,
    request: SmartEventTaskRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
) -> dict:
    service = JiangsuSmartEventService()
    try:
        task = service.create_task(
            event_id,
            actor={"user_id": user.id, "username": user.username},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="smart_event_not_found") from exc
    if request and request.conversation_id:
        task["conversation_id"] = request.conversation_id
        store = service._load_store()
        for item in store.get("tasks", []):
            if item.get("task_id") == task["task_id"]:
                item["conversation_id"] = request.conversation_id
        service._save_store(store)
    dispatches = await service._dispatch_pending_tasks(service._load_store())
    return {"task": service.get_task(task["task_id"]) or task, "dispatches": dispatches}
