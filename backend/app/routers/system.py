"""System routes extracted from app/main.py.

Paths are intentionally preserved:
- GET /, with frontend index.html served when frontend/dist is present
- GET /api/info
- GET /health
- GET /api/system/status
- GET /api/config
"""

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
import structlog

from app.core.static_files import get_frontend_dist_path
from app.api.routes import ConfigResponse
from app.services.lifecycle_manager import get_fetcher_scheduler, get_tool_registry
from config.settings import settings

logger = structlog.get_logger()
router = APIRouter(tags=["system"])


def _api_info():
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


@router.get("/")
async def root():
    """Serve the frontend entry when built assets exist; otherwise return API information."""
    frontend_dist = get_frontend_dist_path()
    if frontend_dist:
        return FileResponse(frontend_dist / "index.html")
    return _api_info()


@router.get("/api/info")
async def api_info():
    """Root API information for deployments where / serves the frontend."""
    return _api_info()


@router.get("/session/{session_id}", include_in_schema=False)
@router.get("/fetchers", include_in_schema=False)
@router.get("/knowledge-base", include_in_schema=False)
@router.get("/tools-management", include_in_schema=False)
@router.get("/skills-management", include_in_schema=False)
@router.get("/social-accounts", include_in_schema=False)
@router.get("/expert-deliberation", include_in_schema=False)
async def frontend_route():
    """Serve known Vue history-mode routes from the backend deployment port."""
    frontend_dist = get_frontend_dist_path()
    if not frontend_dist:
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(frontend_dist / "index.html")


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


@router.get("/ready")
async def readiness_check(request: Request):
    """Report gateway-facing dependency readiness without exposing secrets."""
    auth_ready = bool(settings.auth_service_url.strip()) or settings.auth_mode == "mock"
    nacos_ready = bool(getattr(request.app.state, "nacos_ready", False))
    components = {
        "authentication": "ready" if auth_ready else "not_configured",
        "nacos": "ready" if nacos_ready else "not_ready",
    }
    production = settings.environment.strip().lower() == "production"
    ready = not production or (auth_ready and nacos_ready)
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "components": components},
        status_code=200 if ready else 503,
    )


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
