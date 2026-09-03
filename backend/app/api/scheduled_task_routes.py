"""
定时任务API路由
提供RESTful API接口
"""
import math
import re
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
from app.scheduled_tasks.models import WorkspaceEntry, HistoryLearningConfig
from app.scheduled_tasks.storage.task_case_storage import (
    MemoryVersionConflictError,
    TaskCaseStorage,
)
from app.scheduled_tasks.event_catalog import (
    EventDefinition,
    get_event_definition,
    get_event_definitions,
)
from app.social.user_registry import get_social_user_registry
from app.social.app_identity import _accounts
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
    prompt: str = Field(..., min_length=1)
    timeout_seconds: int = Field(default=1800, ge=1)
    tags: List[str] = Field(default_factory=list, description="标签")
    workspace_entry: Optional[WorkspaceEntry] = None
    history_learning: Optional[HistoryLearningConfig] = Field(
        default=None,
        description="历史执行记忆配置（为空时使用默认配置）",
    )


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
    prompt: Optional[str] = Field(default=None, min_length=1)
    timeout_seconds: Optional[int] = Field(default=None, ge=1)
    tags: Optional[List[str]] = None
    workspace_entry: Optional[WorkspaceEntry] = None
    history_learning: Optional[HistoryLearningConfig] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task: ScheduledTask
    next_run_time: Optional[str] = None
    is_running: bool = False


class ExecutionSummary(BaseModel):
    """列表页所需的轻量执行摘要，不返回 Agent 详细执行日志。"""
    execution_id: str
    task_id: str
    task_name: str
    session_id: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    trigger_type: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    error_message: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)


class ExecutionListResponse(BaseModel):
    """执行记录列表响应"""
    executions: List[ExecutionSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class StatisticsResponse(BaseModel):
    """统计信息响应"""
    total: int
    success: int
    failed: int
    running: int
    success_rate: float
    avg_duration_seconds: float
    period_days: int


class TaskHistoryCasesResponse(BaseModel):
    """任务历史案例库响应（最新在前）"""
    cases: List[Dict[str, Any]]
    total: int


class TaskMemoryResponse(BaseModel):
    """任务专属长期记忆响应"""
    memory: str
    meta: Dict[str, Any]
    case_count: int


class UpdateTaskMemoryRequest(BaseModel):
    """人工编辑长期记忆请求"""
    content: str = Field(..., min_length=1, description="记忆 Markdown 全文")
    expected_version: int = Field(..., ge=0, description="编辑时读取到的记忆版本")


# ===== API端点 =====


_ARTIFACT_PATTERN = re.compile(
    r"(?:[A-Za-z]:)?[^\s\"'`<>]+\.(?:docx|pdf|xlsx?|csv|qmd|md|png|jpg|jpeg)",
    re.IGNORECASE,
)


def _execution_summary(execution: TaskExecution) -> ExecutionSummary:
    artifacts: List[str] = []
    for step in execution.steps:
        for visual in step.result_visuals:
            value = visual.get("title") or visual.get("name") or visual.get("file_name")
            if value:
                artifacts.append(str(value).replace("\\", "/").rsplit("/", 1)[-1])
        for value in _ARTIFACT_PATTERN.findall(step.agent_response or ""):
            artifacts.append(value.replace("\\", "/").rsplit("/", 1)[-1])

    return ExecutionSummary(
        **execution.model_dump(exclude={"steps", "event_attributes", "delivery_results"}),
        artifacts=list(dict.fromkeys(filter(None, artifacts))),
    )


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
        # App recipients may be represented by their direct social identity,
        # or by the synthetic id used by the management user list.
        normalized_user_id = str(user_id)
        if normalized_user_id.startswith("app-account-"):
            account_id = normalized_user_id.removeprefix("app-account-")
            account = _accounts().get(account_id)
            if account and str(account.get("status", "active")).lower() == "active":
                normalized_user_id = f"app:android:{account_id}"
        if normalized_user_id.startswith("app:"):
            account_id = normalized_user_id.rsplit(":", 1)[-1]
            account = _accounts().get(account_id)
            if account and str(account.get("status", "active")).lower() == "active":
                continue
        user = await registry.get_user(user_id)
        if (
            not user
            or user.status != "active"
            or not user.social_user_id
            or not str(user.channel or "").startswith(("weixin", "app"))
        ):
            raise HTTPException(
                status_code=400,
                detail=f"User {user_id} is not an active bound WeChat user or App user",
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


# Company auth system super-admin account resolved from external user records.
_SYSTEM_SUPER_ADMIN_USER_IDS = {"1"}
_SYSTEM_MANAGED_CUSTOM_TASK_TOOLS = {"search_scheduled_task_history"}


def _is_scheduled_task_admin(user: CurrentUser) -> bool:
    return bool(user.is_admin or user.id in _SYSTEM_SUPER_ADMIN_USER_IDS)


def _can_access_task(task: ScheduledTask, user: CurrentUser) -> bool:
    return _is_scheduled_task_admin(user) or task.owner_user_id == user.id


def _require_task_access(task: ScheduledTask, user: CurrentUser) -> None:
    if not _can_access_task(task, user):
        raise HTTPException(status_code=404, detail=f"Task {task.task_id} not found")


def _accessible_task_ids(user: CurrentUser) -> set[str] | None:
    """Return owned task ids for non-admin users; None means unrestricted."""
    if _is_scheduled_task_admin(user):
        return None
    service = get_scheduled_task_service()
    return {
        task.task_id
        for task in service.list_tasks(enabled_only=False)
        if _can_access_task(task, user)
    }


@router.get("/event-types", response_model=List[EventDefinition])
async def list_event_types(
    _: CurrentUser = Depends(require_current_user),
):
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
            if (
                tool.get("status") == "enabled"
                and tool.get("name") in authorized
                and tool.get("name") not in _SYSTEM_MANAGED_CUSTOM_TASK_TOOLS
            )
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
            prompt=request.prompt,
            timeout_seconds=request.timeout_seconds,
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
            tags=request.tags,
            workspace_entry=request.workspace_entry,
            history_learning=request.history_learning or HistoryLearningConfig(),
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
    enabled_only: bool = Query(default=False, description="仅显示启用的任务"),
    user: CurrentUser = Depends(require_current_user),
):
    """列出所有任务（非管理员仅能看到自己的任务）"""
    try:
        service = get_scheduled_task_service()
        tasks = service.list_tasks(enabled_only=enabled_only)
        tasks = [task for task in tasks if _can_access_task(task, user)]

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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """获取任务详情"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        _require_task_access(task, user)

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
        _require_task_access(task, user)

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
async def delete_task(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """删除任务"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        _require_task_access(task, user)

        success = service.delete_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {"success": True, "message": f"Task {task_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/enable", response_model=TaskResponse)
async def enable_task(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """启用任务"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)
        if task:
            _require_task_access(task, user)
        task = service.enable_task(task_id)
        return TaskResponse(task=task)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/disable", response_model=TaskResponse)
async def disable_task(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """禁用任务"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)
        if task:
            _require_task_access(task, user)
        task = service.disable_task(task_id)
        return TaskResponse(task=task)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/execute", status_code=202)
async def execute_task_now(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """立即执行任务（手动触发，后台执行并立即返回）"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        _require_task_access(task, user)

        if task.trigger_type == TriggerType.EVENT:
            event = service.claim_storage.latest_event(task.event_type or "")
            if not event:
                raise HTTPException(
                    status_code=409,
                    detail="No recorded event available for manual execution",
                )
            dispatch = await service.publish_event(
                event,
                wait=False,
                force_retry=True,
                target_task_id=task_id,
            )
            if not dispatch.accepted_task_ids:
                if task_id not in dispatch.matched_task_ids:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Task is not an event task, event type does not match, "
                            "or the latest event does not satisfy the task filters"
                        ),
                    )
                raise HTTPException(
                    status_code=409,
                    detail="Event is already being processed, please try again later",
                )
        else:
            # 同步等待整个 Agent 执行会被网关超时切断（HTTP 504），
            # 因此在后台启动执行并立即返回，前端通过执行记录查看进度。
            service.start_task_now(task_id)

        return {
            "success": True,
            "message": "任务已开始执行，请在执行记录中查看进度和结果",
            "execution_id": None,
            "execution": None
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/retry-delivery")
async def retry_failed_delivery(
    execution_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    try:
        service = get_scheduled_task_service()
        execution = service.get_execution(execution_id)
        if execution is not None:
            task = service.get_task(execution.task_id)
            if task:
                _require_task_access(task, user)
        return await service.retry_failed_delivery(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise


@router.get("/{task_id}/executions", response_model=ExecutionListResponse)
async def get_task_executions(
    task_id: str,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页记录数"),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=50,
        description="兼容旧客户端的每页记录数",
    ),
    user: CurrentUser = Depends(require_current_user),
):
    """获取任务的执行记录"""
    try:
        service = get_scheduled_task_service()
        effective_page_size = limit or page_size
        task = service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        _require_task_access(task, user)
        executions, total = service.list_executions_page(
            task_id=task_id,
            page=page,
            page_size=effective_page_size,
        )

        return ExecutionListResponse(
            executions=[_execution_summary(item) for item in executions],
            total=total,
            page=page,
            page_size=effective_page_size,
            total_pages=math.ceil(total / effective_page_size),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_task_case_storage(task_id: str, user: CurrentUser) -> TaskCaseStorage:
    service = get_scheduled_task_service()
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _require_task_access(task, user)
    return TaskCaseStorage(task_id)


@router.get("/{task_id}/history/cases", response_model=TaskHistoryCasesResponse)
async def get_task_history_cases(
    task_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="返回最近案例数量"),
    user: CurrentUser = Depends(require_current_user),
):
    """获取任务专属历史案例库（最新在前）"""
    try:
        storage = _get_task_case_storage(task_id, user)
        cases = storage.recent_cases(limit)
        cases.reverse()  # recent_cases 返回旧→新，接口统一最新在前
        return TaskHistoryCasesResponse(cases=cases, total=storage.case_count())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/history/memory", response_model=TaskMemoryResponse)
async def get_task_history_memory(
    task_id: str,
    user: CurrentUser = Depends(require_current_user),
):
    """获取任务专属长期记忆与巩固元信息"""
    try:
        storage = _get_task_case_storage(task_id, user)
        return TaskMemoryResponse(
            memory=storage.read_memory(),
            meta=storage.read_meta(),
            case_count=storage.case_count(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}/history/memory", response_model=TaskMemoryResponse)
async def update_task_history_memory(
    task_id: str,
    request: UpdateTaskMemoryRequest,
    user: CurrentUser = Depends(require_current_user),
):
    """人工编辑任务专属长期记忆（用于纠正记忆偏差），版本号递增并标记 manual"""
    try:
        storage = _get_task_case_storage(task_id, user)
        meta = storage.read_meta()
        storage.write_memory(
            request.content,
            {
                **meta,
                "version": int(meta.get("version", 0)) + 1,
                "last_consolidation_status": "manual",
                "updated_at": datetime.now().isoformat(),
            },
            expected_version=request.expected_version,
        )
        return TaskMemoryResponse(
            memory=storage.read_memory(),
            meta=storage.read_meta(),
            case_count=storage.case_count(),
        )
    except MemoryVersionConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "memory_version_conflict", "message": str(e)},
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/recent", response_model=ExecutionListResponse)
async def get_recent_executions(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页记录数"),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=50,
        description="兼容旧客户端的每页记录数",
    ),
    user: CurrentUser = Depends(require_current_user),
):
    """获取最近的执行记录（非管理员仅能看到自己任务的记录）"""
    try:
        service = get_scheduled_task_service()
        effective_page_size = limit or page_size
        executions, total = service.list_executions_page(
            page=page,
            page_size=effective_page_size,
        )
        accessible = _accessible_task_ids(user)
        if accessible is not None:
            executions = [e for e in executions if e.task_id in accessible]
            total = len(executions)

        return ExecutionListResponse(
            executions=[_execution_summary(item) for item in executions],
            total=total,
            page=page,
            page_size=effective_page_size,
            total_pages=math.ceil(total / effective_page_size),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/summary", response_model=StatisticsResponse)
async def get_statistics(
    task_id: Optional[str] = Query(default=None, description="任务ID（可选）"),
    days: int = Query(default=7, ge=1, le=30, description="统计天数"),
    user: CurrentUser = Depends(require_current_user),
):
    """获取统计信息（非管理员仅统计自己的任务）"""
    try:
        service = get_scheduled_task_service()
        if task_id:
            task = service.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            _require_task_access(task, user)
            stats = service.get_statistics(task_id=task_id, days=days)
            return StatisticsResponse(**stats)

        accessible = _accessible_task_ids(user)
        if accessible is None:
            stats = service.get_statistics(task_id=None, days=days)
            return StatisticsResponse(**stats)

        totals = [service.get_statistics(task_id=tid, days=days) for tid in accessible]
        total = sum(item["total"] for item in totals)
        success = sum(item["success"] for item in totals)
        failed = sum(item["failed"] for item in totals)
        running = sum(item["running"] for item in totals)
        durations = [item["avg_duration_seconds"] for item in totals if item["total"]]
        return StatisticsResponse(
            total=total,
            success=success,
            failed=failed,
            running=running,
            success_rate=success / total if total > 0 else 0,
            avg_duration_seconds=sum(durations) / len(durations) if durations else 0,
            period_days=days,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status(
    user: CurrentUser = Depends(require_current_user),
):
    """获取调度器状态（非管理员仅能看到自己任务的调度信息）"""
    try:
        service = get_scheduled_task_service()
        status = service.get_scheduler_status()
        accessible = _accessible_task_ids(user)
        if accessible is not None and isinstance(status, dict):
            scheduled = status.get("scheduled_tasks")
            if isinstance(scheduled, list):
                status["scheduled_tasks"] = [
                    item for item in scheduled
                    if isinstance(item, dict) and item.get("task_id") in accessible
                ]
        return status

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
