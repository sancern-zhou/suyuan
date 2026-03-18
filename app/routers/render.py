from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Any, Dict

from backend.app.services.render_service import submit_render, get_task

router = APIRouter(prefix="/render", tags=["render"])


@router.post("/", summary="提交渲染任务")
def post_render(visual: Dict[str, Any], sync: bool = False):
    """
    接收 single visual 对象（与 tools 输出的 single visuals 元素相同）
    返回 task_id（异步）或最终状态（同步）。
    """
    if not isinstance(visual, dict):
        raise HTTPException(status_code=400, detail="visual must be an object")
    result = submit_render(visual, synchronous=sync)
    return result


@router.get("/{task_id}", summary="查询渲染任务状态")
def get_render(task_id: str):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task









