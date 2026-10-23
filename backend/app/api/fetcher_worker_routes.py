"""Worker-backed fetcher management routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/fetchers", tags=["fetchers"])


def get_fetcher_scheduler():
    """Resolve the worker singleton only when handling a management request."""
    from app.services.lifecycle_manager import get_fetcher_scheduler as get_scheduler
    scheduler = get_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Fetcher scheduler unavailable")
    return scheduler


class FetcherStatusResponse(BaseModel):
    scheduler_running: bool
    fetchers: dict[str, dict[str, Any]]


class FetcherOperationResponse(BaseModel):
    success: bool
    message: str
    fetcher_name: str


@router.get("/status", response_model=FetcherStatusResponse)
async def get_fetchers_status(scheduler=Depends(get_fetcher_scheduler)) -> FetcherStatusResponse:
    """Return the live fetcher scheduler status from the worker process."""
    try:
        return FetcherStatusResponse(**scheduler.get_status())
    except Exception as e:
        logger.error("worker_fetchers_status_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取 Fetcher 状态失败: {str(e)}")


@router.post("/trigger/{fetcher_name}", response_model=FetcherOperationResponse)
async def trigger_fetcher(fetcher_name: str, scheduler=Depends(get_fetcher_scheduler)) -> FetcherOperationResponse:
    """Run a fetcher immediately on the worker process."""
    if fetcher_name not in scheduler.fetchers:
        raise HTTPException(status_code=404, detail=f"Fetcher 不存在: {fetcher_name}")

    try:
        await scheduler.run_now(fetcher_name)
        if fetcher_name == "consultation_file_fetcher" and "monthly_consultation_file_fetcher" in scheduler.fetchers:
            await scheduler.run_now("monthly_consultation_file_fetcher")
        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已触发",
            fetcher_name=fetcher_name,
        )
    except Exception as e:
        logger.error("worker_fetcher_trigger_failed", fetcher_name=fetcher_name, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"触发 Fetcher 失败: {str(e)}")


@router.post("/pause/{fetcher_name}", response_model=FetcherOperationResponse)
async def pause_fetcher(fetcher_name: str, scheduler=Depends(get_fetcher_scheduler)) -> FetcherOperationResponse:
    """Pause a fetcher on the worker process."""
    if fetcher_name not in scheduler.fetchers:
        raise HTTPException(status_code=404, detail=f"Fetcher 不存在: {fetcher_name}")

    try:
        scheduler.pause(fetcher_name)
        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已暂停",
            fetcher_name=fetcher_name,
        )
    except Exception as e:
        logger.error("worker_fetcher_pause_failed", fetcher_name=fetcher_name, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"暂停 Fetcher 失败: {str(e)}")


@router.post("/resume/{fetcher_name}", response_model=FetcherOperationResponse)
async def resume_fetcher(fetcher_name: str, scheduler=Depends(get_fetcher_scheduler)) -> FetcherOperationResponse:
    """Resume a fetcher on the worker process."""
    if fetcher_name not in scheduler.fetchers:
        raise HTTPException(status_code=404, detail=f"Fetcher 不存在: {fetcher_name}")

    try:
        scheduler.resume(fetcher_name)
        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已恢复",
            fetcher_name=fetcher_name,
        )
    except Exception as e:
        logger.error("worker_fetcher_resume_failed", fetcher_name=fetcher_name, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"恢复 Fetcher 失败: {str(e)}")


@router.get("/list")
async def list_fetchers(scheduler=Depends(get_fetcher_scheduler)) -> dict[str, Any]:
    """List the worker's registered fetchers without creating another scheduler."""
    fetchers = scheduler.list_fetchers()
    return {"fetchers": fetchers, "count": len(fetchers)}


@router.post("/start")
async def start_scheduler(scheduler=Depends(get_fetcher_scheduler)) -> dict[str, Any]:
    if scheduler.is_running():
        return {"success": True, "message": "调度器已在运行中"}
    try:
        scheduler.start()
    except Exception as exc:
        logger.exception("worker_fetcher_scheduler_start_failed")
        raise HTTPException(status_code=500, detail="启动调度器失败") from exc
    return {"success": True, "message": "调度器已启动"}


@router.post("/stop")
async def stop_scheduler(scheduler=Depends(get_fetcher_scheduler)) -> dict[str, Any]:
    if not scheduler.is_running():
        return {"success": True, "message": "调度器未运行"}
    try:
        scheduler.stop()
    except Exception as exc:
        logger.exception("worker_fetcher_scheduler_stop_failed")
        raise HTTPException(status_code=500, detail="停止调度器失败") from exc
    return {"success": True, "message": "调度器已停止"}
