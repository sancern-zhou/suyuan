"""
定时任务API路由
提供RESTful API接口
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.scheduled_tasks import (
    get_scheduled_task_service,
    ScheduledTask,
    TaskExecution,
    ScheduleType,
    TriggerType,
)
from app.scheduled_tasks.models import TaskStep, WorkspaceEntry
from app.scheduled_tasks.event_catalog import (
    EventDefinition,
    get_event_definition,
    get_event_definitions,
)
from app.social.user_registry import get_social_user_registry
from app.services.lifecycle_manager import get_tool_registry
from app.scheduled_tasks.custom_agent import (
    CustomToolValidationError,
    authorized_tool_names_for_user,
    validate_custom_tool_names,
)
from app.agent.selection_context import describe_skill_item, load_skill_selection

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


# ===== 请求/响应模型 =====

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")
    execution_mode: str = Field(default="expert", description="执行模式（assistant/expert/query/social/custom）")
    tool_names: Optional[List[str]] = None
    skill_id: Optional[str] = None
    trigger_type: TriggerType = Field(default=TriggerType.SCHEDULE, description="触发方式")
    schedule_type: Optional[ScheduleType] = Field(default=None, description="调度类型")
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    event_type: Optional[str] = None
    event_filters: Dict[str, Any] = Field(default_factory=dict)
    broadcast_enabled: bool = False
    target_user_ids: List[str] = Field(default_factory=list)
    enabled: bool = Field(default=True, description="是否启用")
    steps: List[TaskStep] = Field(..., description="任务步骤")
    tags: List[str] = Field(default_factory=list, description="标签")
    workspace_entry: Optional[WorkspaceEntry] = None


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    execution_mode: Optional[str] = None
    tool_names: Optional[List[str]] = None
    skill_id: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    schedule_type: Optional[ScheduleType] = None
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    event_type: Optional[str] = None
    event_filters: Optional[Dict[str, Any]] = None
    broadcast_enabled: Optional[bool] = None
    target_user_ids: Optional[List[str]] = None
    enabled: Optional[bool] = None
    steps: Optional[List[TaskStep]] = None
    tags: Optional[List[str]] = None
    workspace_entry: Optional[WorkspaceEntry] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task: ScheduledTask
    next_run_time: Optional[str] = None
    is_running: bool = False


class ExecutionListResponse(BaseModel):
    """执行记录列表响应"""
    executions: List[TaskExecution]
    total: int


class StatisticsResponse(BaseModel):
    """统计信息响应"""
    total: int
    success: int
    failed: int
    running: int
    success_rate: float
    avg_duration_seconds: float
    period_days: int


# ===== API端点 =====


async def _validate_event_task_config(task: ScheduledTask) -> None:
    if task.trigger_type == TriggerType.EVENT and not get_event_definition(
        task.event_type or ""
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unregistered event_type: {task.event_type}",
        )

    if not task.broadcast_enabled:
        return

    registry = get_social_user_registry()
    for user_id in task.target_user_ids:
        user = await registry.get_user(user_id)
        if (
            not user
            or user.status != "active"
            or not user.social_user_id
            or not str(user.channel or "").startswith("weixin")
        ):
            raise HTTPException(
                status_code=400,
                detail=f"User {user_id} is not an active bound WeChat user",
            )


def _validate_custom_task_tools(task: ScheduledTask, user: CurrentUser) -> None:
    if task.execution_mode != "custom":
        return
    try:
        registry = get_tool_registry()
        validate_custom_tool_names(
            task.tool_names or [],
            registry,
            authorized_tool_names_for_user(user, registry),
        )
    except CustomToolValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_custom_task_tools", "items": exc.items},
        ) from exc


def _validate_task_skill(task: ScheduledTask) -> None:
    if not task.skill_id:
        return
    try:
        load_skill_selection(task.skill_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_task_skill",
                "skill_id": task.skill_id,
                "message": f"Skill 不存在：{task.skill_id}",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_task_skill",
                "skill_id": task.skill_id,
                "message": str(exc),
            },
        ) from exc


@router.get("/event-types", response_model=List[EventDefinition])
async def list_event_types():
    return get_event_definitions()


@router.get("/tools")
async def list_custom_task_tools(
    user: CurrentUser = Depends(require_current_user),
):
    """List tools the authenticated user may select for custom task mode."""
    registry = get_tool_registry()
    authorized = authorized_tool_names_for_user(user, registry)
    tools = registry.get_tools_info()
    return {
        "tools": [
            tool for tool in tools
            if tool.get("status") == "enabled" and tool.get("name") in authorized
        ]
    }


@router.get("/skills")
async def list_task_skills(
    _: CurrentUser = Depends(require_current_user),
):
    """List enabled project Skills available for task context injection."""
    from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool

    result = await ListSkillsTool().execute()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error") or "Skill 列表加载失败")
    described_items = [
        describe_skill_item(item)
        for item in (result.get("data") or {}).get("skills", [])
    ]
    items = [
        {
            "id": item["id"],
            "name": item.get("name") or item["id"],
            "description": item.get("description") or "",
            "aliases": item.get("aliases") or [],
        }
        for item in described_items
        if item.get("enabled", True)
    ]
    return {
        "skills": items,
        "count": len(items),
    }

@router.post("", response_model=TaskResponse)
async def create_task(
    request: CreateTaskRequest,
    user: CurrentUser = Depends(require_current_user),
):
    """创建定时任务"""
    try:
        service = get_scheduled_task_service()

        # 生成任务ID
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # 创建任务
        task = ScheduledTask(
            task_id=task_id,
            name=request.name,
            description=request.description,
            execution_mode=request.execution_mode,
            tool_names=request.tool_names,
            skill_id=request.skill_id,
            trigger_type=request.trigger_type,
            schedule_type=request.schedule_type,
            run_at=request.run_at,
            interval_minutes=request.interval_minutes,
            hour=request.hour,
            minute=request.minute,
            event_type=request.event_type,
            event_filters=request.event_filters,
            broadcast_enabled=request.broadcast_enabled,
            target_user_ids=request.target_user_ids,
            enabled=request.enabled,
            steps=request.steps,
            tags=request.tags,
            workspace_entry=request.workspace_entry,
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
        )
        await _validate_event_task_config(task)
        _validate_custom_task_tools(task, user)
        _validate_task_skill(task)

        created_task = service.create_task(task)

        # 获取下次运行时间
        scheduler_status = service.get_scheduler_status()
        next_run_time = None
        for scheduled in scheduler_status.get("scheduled_tasks", []):
            if scheduled["task_id"] == task_id:
                next_run_time = scheduled.get("next_run_time")
                break

        return TaskResponse(
            task=created_task,
            next_run_time=str(next_run_time) if next_run_time else None,
            is_running=False
        )

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    enabled_only: bool = Query(default=False, description="仅显示启用的任务")
):
    """列出所有任务"""
    try:
        service = get_scheduled_task_service()
        tasks = service.list_tasks(enabled_only=enabled_only)

        # 获取调度器状态
        scheduler_status = service.get_scheduler_status()
        scheduled_tasks = {
            st["task_id"]: st.get("next_run_time")
            for st in scheduler_status.get("scheduled_tasks", [])
        }

        return [
            TaskResponse(
                task=task,
                next_run_time=str(scheduled_tasks.get(task.task_id)) if scheduled_tasks.get(task.task_id) else None,
                is_running=False  # TODO: 从调度器获取运行状态
            )
            for task in tasks
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取任务详情"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # 获取下次运行时间
        scheduler_status = service.get_scheduler_status()
        next_run_time = None
        for scheduled in scheduler_status.get("scheduled_tasks", []):
            if scheduled["task_id"] == task_id:
                next_run_time = scheduled.get("next_run_time")
                break

        return TaskResponse(
            task=task,
            next_run_time=str(next_run_time) if next_run_time else None,
            is_running=False
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    user: CurrentUser = Depends(require_current_user),
):
    """更新任务"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        updates = request.model_dump(exclude_unset=True)
        if updates.get("execution_mode") != "custom" and "execution_mode" in updates:
            updates.setdefault("tool_names", None)
        task_data = task.model_dump()
        task_data.update(updates)
        task = ScheduledTask.model_validate(task_data)
        await _validate_event_task_config(task)
        _validate_custom_task_tools(task, user)
        _validate_task_skill(task)

        updated_task = service.update_task(task)

        return TaskResponse(task=updated_task)

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    try:
        service = get_scheduled_task_service()
        success = service.delete_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {"success": True, "message": f"Task {task_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/enable", response_model=TaskResponse)
async def enable_task(task_id: str):
    """启用任务"""
    try:
        service = get_scheduled_task_service()
        task = service.enable_task(task_id)
        return TaskResponse(task=task)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/disable", response_model=TaskResponse)
async def disable_task(task_id: str):
    """禁用任务"""
    try:
        service = get_scheduled_task_service()
        task = service.disable_task(task_id)
        return TaskResponse(task=task)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/execute")
async def execute_task_now(task_id: str):
    """立即执行任务（手动触发）"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if task.trigger_type == TriggerType.EVENT:
            raise HTTPException(
                status_code=400,
                detail="Event-triggered tasks cannot be executed manually",
            )

        execution = await service.execute_task_now(task_id)

        return {
            "success": True,
            "message": f"任务已开始执行",
            "execution_id": execution.execution_id,
            "execution": execution
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/retry-delivery")
async def retry_failed_delivery(execution_id: str):
    try:
        service = get_scheduled_task_service()
        return await service.retry_failed_delivery(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/executions", response_model=ExecutionListResponse)
async def get_task_executions(
    task_id: str,
    limit: int = Query(default=10, ge=1, le=50, description="返回记录数")
):
    """获取任务的执行记录"""
    try:
        service = get_scheduled_task_service()
        executions = service.list_executions(task_id=task_id, limit=limit)

        return ExecutionListResponse(
            executions=executions,
            total=len(executions)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/recent", response_model=ExecutionListResponse)
async def get_recent_executions(
    limit: int = Query(default=20, ge=1, le=50, description="返回记录数")
):
    """获取最近的执行记录"""
    try:
        service = get_scheduled_task_service()
        executions = service.list_executions(limit=limit)

        return ExecutionListResponse(
            executions=executions,
            total=len(executions)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/summary", response_model=StatisticsResponse)
async def get_statistics(
    task_id: Optional[str] = Query(default=None, description="任务ID（可选）"),
    days: int = Query(default=7, ge=1, le=30, description="统计天数")
):
    """获取统计信息"""
    try:
        service = get_scheduled_task_service()
        stats = service.get_statistics(task_id=task_id, days=days)

        return StatisticsResponse(**stats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status():
    """获取调度器状态"""
    try:
        service = get_scheduled_task_service()
        return service.get_scheduler_status()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
