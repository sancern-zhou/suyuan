"""Worker-backed fetcher management routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from app.services import lifecycle_manager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/fetchers", tags=["fetchers"])


class FetcherStatusResponse(BaseModel):
    scheduler_running: bool
    fetchers: dict[str, dict[str, Any]]


class FetcherOperationResponse(BaseModel):
    success: bool
    message: str
    fetcher_name: str


@router.get("/status", response_model=FetcherStatusResponse)
async def get_fetchers_status() -> FetcherStatusResponse:
    """Return the live fetcher scheduler status from the worker process."""
    try:
        scheduler = lifecycle_manager.get_fetcher_scheduler()
        return FetcherStatusResponse(**scheduler.get_status())
    except Exception as e:
        logger.error("worker_fetchers_status_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取 Fetcher 状态失败: {str(e)}")


@router.post("/trigger/{fetcher_name}", response_model=FetcherOperationResponse)
async def trigger_fetcher(fetcher_name: str) -> FetcherOperationResponse:
    """Run a fetcher immediately on the worker process."""
    scheduler = lifecycle_manager.get_fetcher_scheduler()
    if fetcher_name not in scheduler.fetchers:
        raise HTTPException(status_code=404, detail=f"Fetcher 不存在: {fetcher_name}")

    try:
        await scheduler.run_now(fetcher_name)
        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已触发",
            fetcher_name=fetcher_name,
        )
    except Exception as e:
        logger.error("worker_fetcher_trigger_failed", fetcher_name=fetcher_name, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"触发 Fetcher 失败: {str(e)}")


@router.post("/pause/{fetcher_name}", response_model=FetcherOperationResponse)
async def pause_fetcher(fetcher_name: str) -> FetcherOperationResponse:
    """Pause a fetcher on the worker process."""
    scheduler = lifecycle_manager.get_fetcher_scheduler()
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
async def resume_fetcher(fetcher_name: str) -> FetcherOperationResponse:
    """Resume a fetcher on the worker process."""
    scheduler = lifecycle_manager.get_fetcher_scheduler()
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
