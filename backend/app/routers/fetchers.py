"""
Data Fetchers API Routes

提供数据抓取器的管理接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import structlog

from app.fetchers import create_scheduler

logger = structlog.get_logger()

router = APIRouter(prefix="/api/fetchers", tags=["fetchers"])

# 全局调度器实例（延迟初始化）
_fetcher_scheduler = None


def get_fetcher_scheduler():
    """获取 Fetcher 调度器实例"""
    global _fetcher_scheduler
    if _fetcher_scheduler is None:
        _fetcher_scheduler = create_scheduler()
    return _fetcher_scheduler


# ========================================
# Request/Response Models
# ========================================

class FetcherStatusResponse(BaseModel):
    """Fetcher 状态响应"""
    scheduler_running: bool
    fetchers: Dict[str, Dict[str, Any]]


class FetcherOperationResponse(BaseModel):
    """Fetcher 操作响应"""
    success: bool
    message: str
    fetcher_name: str


# ========================================
# API Endpoints
# ========================================

@router.get("/status", response_model=FetcherStatusResponse)
async def get_fetchers_status():
    """
    获取所有 Fetchers 的状态

    Returns:
        FetcherStatusResponse: 包含调度器运行状态和所有 Fetcher 的状态
    """
    try:
        scheduler = get_fetcher_scheduler()
        status = scheduler.get_status()

        logger.info(
            "fetchers_status_retrieved",
            scheduler_running=status["scheduler_running"],
            fetcher_count=len(status["fetchers"])
        )

        return FetcherStatusResponse(**status)

    except Exception as e:
        logger.error(
            "get_fetchers_status_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取 Fetcher 状态失败: {str(e)}"
        )


@router.post("/trigger/{fetcher_name}", response_model=FetcherOperationResponse)
async def trigger_fetcher(fetcher_name: str):
    """
    手动触发指定的 Fetcher 立即运行

    Args:
        fetcher_name: Fetcher 名称

    Returns:
        FetcherOperationResponse: 操作结果
    """
    try:
        scheduler = get_fetcher_scheduler()

        # 检查 Fetcher 是否存在
        if fetcher_name not in scheduler.fetchers:
            raise HTTPException(
                status_code=404,
                detail=f"Fetcher 不存在: {fetcher_name}"
            )

        # 立即运行 Fetcher
        await scheduler.run_now(fetcher_name)

        # 特殊处理：如果触发 consultation_file_fetcher，同时触发 monthly_consultation_file_fetcher
        if fetcher_name == "consultation_file_fetcher":
            monthly_fetcher_name = "monthly_consultation_file_fetcher"
            if monthly_fetcher_name in scheduler.fetchers:
                logger.info(
                    "fetcher_trigger_cascade",
                    primary=fetcher_name,
                    secondary=monthly_fetcher_name,
                    message="触发会商文件时，同时生成上个月完整版"
                )
                await scheduler.run_now(monthly_fetcher_name)

        logger.info("fetcher_triggered", fetcher_name=fetcher_name)

        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已触发",
            fetcher_name=fetcher_name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "trigger_fetcher_failed",
            fetcher_name=fetcher_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"触发 Fetcher 失败: {str(e)}"
        )


@router.post("/pause/{fetcher_name}", response_model=FetcherOperationResponse)
async def pause_fetcher(fetcher_name: str):
    """
    暂停指定的 Fetcher

    Args:
        fetcher_name: Fetcher 名称

    Returns:
        FetcherOperationResponse: 操作结果
    """
    try:
        scheduler = get_fetcher_scheduler()

        # 检查 Fetcher 是否存在
        if fetcher_name not in scheduler.fetchers:
            raise HTTPException(
                status_code=404,
                detail=f"Fetcher 不存在: {fetcher_name}"
            )

        # 暂停 Fetcher
        scheduler.pause(fetcher_name)

        logger.info("fetcher_paused", fetcher_name=fetcher_name)

        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已暂停",
            fetcher_name=fetcher_name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "pause_fetcher_failed",
            fetcher_name=fetcher_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"暂停 Fetcher 失败: {str(e)}"
        )


@router.post("/resume/{fetcher_name}", response_model=FetcherOperationResponse)
async def resume_fetcher(fetcher_name: str):
    """
    恢复指定的 Fetcher

    Args:
        fetcher_name: Fetcher 名称

    Returns:
        FetcherOperationResponse: 操作结果
    """
    try:
        scheduler = get_fetcher_scheduler()

        # 检查 Fetcher 是否存在
        if fetcher_name not in scheduler.fetchers:
            raise HTTPException(
                status_code=404,
                detail=f"Fetcher 不存在: {fetcher_name}"
            )

        # 恢复 Fetcher
        scheduler.resume(fetcher_name)

        logger.info("fetcher_resumed", fetcher_name=fetcher_name)

        return FetcherOperationResponse(
            success=True,
            message=f"Fetcher {fetcher_name} 已恢复",
            fetcher_name=fetcher_name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "resume_fetcher_failed",
            fetcher_name=fetcher_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"恢复 Fetcher 失败: {str(e)}"
        )


@router.get("/list")
async def list_fetchers():
    """
    列出所有已注册的 Fetchers

    Returns:
        List: Fetcher 名称列表
    """
    try:
        scheduler = get_fetcher_scheduler()
        fetchers = scheduler.list_fetchers()

        logger.info(
            "fetchers_listed",
            count=len(fetchers)
        )

        return {
            "fetchers": fetchers,
            "count": len(fetchers)
        }

    except Exception as e:
        logger.error(
            "list_fetchers_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取 Fetcher 列表失败: {str(e)}"
        )


@router.post("/start")
async def start_scheduler():
    """
    启动 Fetcher 调度器

    Returns:
        操作结果
    """
    try:
        scheduler = get_fetcher_scheduler()

        if scheduler.is_running():
            return {
                "success": True,
                "message": "调度器已在运行中"
            }

        scheduler.start()

        logger.info("fetcher_scheduler_started")

        return {
            "success": True,
            "message": "调度器已启动"
        }

    except Exception as e:
        logger.error(
            "start_scheduler_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"启动调度器失败: {str(e)}"
        )


@router.post("/stop")
async def stop_scheduler():
    """
    停止 Fetcher 调度器

    Returns:
        操作结果
    """
    try:
        scheduler = get_fetcher_scheduler()

        if not scheduler.is_running():
            return {
                "success": True,
                "message": "调度器未运行"
            }

        scheduler.stop()

        logger.info("fetcher_scheduler_stopped")

        return {
            "success": True,
            "message": "调度器已停止"
        }

    except Exception as e:
        logger.error(
            "stop_scheduler_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"停止调度器失败: {str(e)}"
        )
