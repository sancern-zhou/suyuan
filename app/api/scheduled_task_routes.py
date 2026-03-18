"""
定时任务API路由
提供RESTful API接口
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.scheduled_tasks import (
    get_scheduled_task_service,
    ScheduledTask,
    TaskExecution,
    ScheduleType
)
from app.scheduled_tasks.models import TaskStep

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


# ===== 请求/响应模型 =====

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    name: str = Field(..., description="任务名称")
    description: str = Field(..., description="任务描述")
    schedule_type: ScheduleType = Field(..., description="调度类型")
    enabled: bool = Field(default=True, description="是否启用")
    steps: List[TaskStep] = Field(..., description="任务步骤")
    tags: List[str] = Field(default_factory=list, description="标签")


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_type: Optional[ScheduleType] = None
    enabled: Optional[bool] = None
    steps: Optional[List[TaskStep]] = None
    tags: Optional[List[str]] = None


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

@router.post("", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest):
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
            schedule_type=request.schedule_type,
            enabled=request.enabled,
            steps=request.steps,
            tags=request.tags
        )

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
async def update_task(task_id: str, request: UpdateTaskRequest):
    """更新任务"""
    try:
        service = get_scheduled_task_service()
        task = service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # 更新字段
        if request.name is not None:
            task.name = request.name
        if request.description is not None:
            task.description = request.description
        if request.schedule_type is not None:
            task.schedule_type = request.schedule_type
        if request.enabled is not None:
            task.enabled = request.enabled
        if request.steps is not None:
            task.steps = request.steps
        if request.tags is not None:
            task.tags = request.tags

        updated_task = service.update_task(task)

        return TaskResponse(task=updated_task)

    except HTTPException:
        raise
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
        execution = await service.execute_task_now(task_id)

        return {
            "success": True,
            "message": f"任务已开始执行",
            "execution_id": execution.execution_id,
            "execution": execution
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
