"""System routes extracted from app/main.py.

Paths are intentionally preserved:
- GET /
- GET /health
- GET /api/system/status
- GET /api/config
"""

import os

from fastapi import APIRouter, HTTPException
import structlog

from app.models.schemas import ConfigResponse
from app.services.lifecycle_manager import get_fetcher_scheduler, get_tool_registry
from config.settings import settings

logger = structlog.get_logger()
router = APIRouter(tags=["system"])


@router.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "atmospheric-environment-decision-support-api",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "config": "GET /api/config",
            "analyze": "POST /api/analyze",
            "health": "GET /health",
            "system_status": "GET /api/system/status - 系统状态",
            "weather": "POST /api/weather/query - 气象数据查询",
            "weather_stats": "GET /api/weather/stats - 数据统计",
            "weather_stations": "GET /api/weather/stations - 站点列表",
            "admin": "GET /static/admin.html - 管理后台界面",
            "workflow": "GET /api/admin/workflow - 工作流可视化",
            "prompts": "GET /api/admin/prompts - 提示词管理",
            "editable_config": "GET /api/admin/config/all - 配置管理",
            "react_agent_analyze": "POST /api/agent/analyze - ReAct Agent分析 (SSE流式)",
            "react_agent_query": "POST /api/agent/query - ReAct Agent查询 (非流式)",
            "react_agent_tools": "GET /api/agent/tools - ReAct Agent工具列表",
            "react_agent_health": "GET /api/agent/health - ReAct Agent健康检查",
            "knowledge_qa_stream": "POST /api/knowledge-qa/stream - 知识问答流式接口",
            "knowledge_qa": "POST /api/knowledge-qa - 知识问答非流式接口",
        },
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "atmospheric-environment-decision-support-api",
        "version": "1.0.0",
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
    }


@router.get("/api/system/status")
async def system_status():
    """Get system status information."""
    try:
        status = {
            "service": "atmospheric-environment-decision-support-api",
            "version": "1.0.0",
            "timestamp": structlog.processors.TimeStamper(fmt="iso").__call__(
                None,
                None,
                {},
            )["timestamp"],
        }

        if os.getenv("DATABASE_URL"):
            database_url = os.getenv("DATABASE_URL", "")
            status["database"] = {
                "enabled": True,
                "url": database_url.split("@")[1] if "@" in database_url else "configured",
            }
        else:
            status["database"] = {"enabled": False}

        try:
            scheduler = get_fetcher_scheduler()
            status["fetchers"] = scheduler.get_status()
        except Exception as e:
            status["fetchers"] = {"error": str(e)}

        try:
            registry = get_tool_registry()
            status["llm_tools"] = {
                "registered": registry.list_tools(),
                "count": len(registry.list_tools()),
                "statistics": registry.get_stats(),
            }
        except Exception as e:
            status["llm_tools"] = {"error": str(e)}

        return status

    except Exception as e:
        logger.error("system_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


@router.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get public configuration for frontend."""
    try:
        logger.info("config_requested")

        return ConfigResponse(
            amapPublicKey=settings.amap_public_key,
            features={
                "dynamicPreferred": True,
                "echarts": True,
            },
        )

    except Exception as e:
        logger.error("config_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch configuration")

