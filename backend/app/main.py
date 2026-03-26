"""
Main FastAPI application for Air Pollution Source Traceability System.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from app.models.schemas import (
    ConfigResponse,
)
from app.utils.http_client import http_client
from app.routers import admin, agent as react_agent_router
from config.settings import settings
from app.db.database import init_db, close_db
from app.services.lifecycle_manager import (
    initialize_fetchers,
    stop_fetchers,
    initialize_llm_tools,
    get_tool_registry,
    get_fetcher_scheduler,
)
import structlog
import sys
import logging
from pathlib import Path
import os
import asyncio

# Configure Python logging first
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,  # 确保 INFO 级别能输出
)

# Configure structured logging
# 优化: 使用易读的控制台输出，同时避免截断，支持大型LLM输出
# 根据环境变量决定输出格式：开发环境使用彩色易读格式，生产环境使用JSON
import os
use_json_logs = os.getenv("USE_JSON_LOGS", "false").lower() == "true"

if use_json_logs:
    # 生产环境：JSON格式（便于日志收集和分析）
    renderer = structlog.processors.JSONRenderer()
else:
    # 开发环境：彩色易读格式（便于人类阅读）
    renderer = structlog.dev.ConsoleRenderer(
        colors=True,  # 启用彩色输出
        exception_formatter=structlog.dev.plain_traceback,  # 清晰的异常堆栈
    )

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # 动态选择渲染器 - ConsoleRenderer不会截断，同样支持大型输出
        renderer,
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Air Pollution Source Traceability API",
    description="Backend API for analyzing air pollution sources with LLM-powered insights",
    version="1.0.0",
    debug=settings.debug,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,  # 预检请求缓存1小时
)

# Include routers
app.include_router(admin.router)

# Include ReAct Agent router (new architecture)
app.include_router(react_agent_router.router)

# Include Export router (report export functionality)
from app.routers import export as export_router
app.include_router(export_router.router)

# Include API routes (streaming support)
from app.api import routes as api_routes
app.include_router(api_routes.router, prefix="/api")

# Include Knowledge Base routes
from app.api.knowledge_base_routes import router as kb_router
app.include_router(kb_router, prefix="/api")

# Include Report Generation routes
from app.routers import report_generation
app.include_router(report_generation.router, prefix="/api")

# Include Monitoring router (LLM API monitoring)
from app.routers import monitoring as monitoring_router
app.include_router(monitoring_router.router)

# Include Image routes (chart image caching and retrieval)
from app.api.image_routes import router as image_router
app.include_router(image_router, prefix="/api")

# Include Session Management routes (会话持久化)
from app.api.session_routes import router as session_router
app.include_router(session_router)

# Include Knowledge QA routes (RAG-based Q&A)
from app.routers.knowledge_qa import router as knowledge_qa_router
app.include_router(knowledge_qa_router)

# Include Quick Trace Alert routes (污染高值告警快速溯源)
from app.api.quick_trace_routes import router as quick_trace_router
app.include_router(quick_trace_router)

# Include Scheduled Tasks routes (定时任务系统)
from app.api.scheduled_task_routes import router as scheduled_task_router
app.include_router(scheduled_task_router)

# Include Scheduled Tasks WebSocket
from app.api.scheduled_task_ws import router as scheduled_task_ws_router
app.include_router(scheduled_task_ws_router)

# Include File Upload routes (对话文件上传)
from app.api.upload_routes import router as upload_router
app.include_router(upload_router, prefix="/api/upload")

# Include Office routes (Office文档预览)
from app.api.office_routes import router as office_router
app.include_router(office_router)

# Include Social Platform routes (社交平台管理)
from app.routers import social_routes
app.include_router(social_routes.router)


# 全局异常处理器：捕获请求验证错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """捕获请求验证错误，返回详细错误信息"""
    errors = exc.errors()
    logger.error(
        "request_validation_failed",
        path=request.url.path,
        method=request.method,
        errors=errors,
        error_count=len(errors)
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": errors,
            "message": "请求数据验证失败，请检查数据格式"
        }
    )


# Mount static files for admin interface
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info("static_files_mounted", path=str(static_path))


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info(
        "application_starting",
        environment=settings.environment,
        host=settings.host,
        port=settings.port,
        llm_provider=settings.llm_provider,
    )

    # 1. 初始化LLM工具（独立于数据库）
    try:
        initialize_llm_tools()
        logger.info("llm_tools_initialized")

        # 🔧 刷新全局 Agent 实例的工具注册表
        try:
            from app.routers.agent import (
                multi_expert_agent_instance,
                meteorology_expert_agent_instance,
                quick_tracing_agent_instance,
                data_viz_agent_instance,
                deep_tracing_agent_instance
            )

            logger.info("refreshing_global_agent_tools")

            multi_expert_agent_instance.refresh_tools()
            meteorology_expert_agent_instance.refresh_tools()
            quick_tracing_agent_instance.refresh_tools()
            data_viz_agent_instance.refresh_tools()
            deep_tracing_agent_instance.refresh_tools()

            logger.info(
                "global_agents_refreshed",
                multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
                meteorology_tools=len(meteorology_expert_agent_instance.get_available_tools()),
                quick_tracing_tools=len(quick_tracing_agent_instance.get_available_tools()),
                data_viz_tools=len(data_viz_agent_instance.get_available_tools()),
                deep_tracing_tools=len(deep_tracing_agent_instance.get_available_tools())
            )
        except Exception as e:
            logger.warning("agent_refresh_failed", error=str(e))

    except Exception as e:
        logger.error("llm_tools_initialization_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_llm_tools")

    # 1.5 初始化定时任务系统
    try:
        from app.scheduled_tasks import init_service, start_service
        from app.agent.react_agent import create_react_agent

        # 初始化服务（传入Agent工厂 - 使用单专家ReAct Agent）
        init_service(agent_factory=lambda: create_react_agent())

        # 启动调度器
        start_service()
        logger.info("scheduled_task_service_started")
    except Exception as e:
        logger.error("scheduled_task_service_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_scheduled_tasks")

    # 1.6 初始化社交平台服务
    try:
        from app.social.message_bus import MessageBus
        from app.social.session_mapper import SessionMapper
        from app.social.agent_bridge import AgentBridge
        from app.social.config import SocialConfig
        from app.channels.manager import ChannelManager
        from app.agent.react_agent import create_react_agent

        # 加载社交平台配置
        social_config = SocialConfig.load_from_yaml(settings.social_config_path)

        # 检查是否启用了任何平台
        if not any([social_config.qq.enabled, social_config.weixin.enabled]):
            logger.info("social_platform_disabled", reason="no_platforms_enabled")
        else:
            # 创建消息总线
            message_bus = MessageBus()

            # 创建会话映射器
            session_mapper = SessionMapper()
            await session_mapper.load()

            # 创建Agent桥接层（使用社交模式）
            agent = create_react_agent()
            agent_bridge = AgentBridge(
                agent=agent,
                message_bus=message_bus,
                session_mapper=session_mapper,
                mode="social"  # ⚠️ Social模式：移动端呼吸式Agent
            )

            # 创建Channel管理器（传递配置）
            channel_manager = ChannelManager(config=social_config, bus=message_bus)

            # 启动Agent桥接层（后台任务）
            async def run_agent_bridge():
                try:
                    logger.info("agent_bridge_starting")
                    await agent_bridge.start()
                    logger.info("agent_bridge_started")
                except Exception as e:
                    logger.error("agent_bridge_failed", error=str(e), exc_info=True)

            # 启动Channel管理器（后台任务）
            async def run_channel_manager():
                try:
                    logger.info("channel_manager_starting")
                    await channel_manager.start_all()
                    logger.info("channel_manager_started")
                except Exception as e:
                    logger.error("channel_manager_failed", error=str(e), exc_info=True)

            # 创建后台任务
            try:
                app.state.agent_bridge_task = asyncio.create_task(run_agent_bridge())
                logger.info("agent_bridge_task_created", task_id=id(app.state.agent_bridge_task))
            except Exception as e:
                logger.error("agent_bridge_task_creation_failed", error=str(e), exc_info=True)

            try:
                app.state.channel_manager_task = asyncio.create_task(run_channel_manager())
                logger.info("channel_manager_task_created", task_id=id(app.state.channel_manager_task))
            except Exception as e:
                logger.error("channel_manager_task_creation_failed", error=str(e), exc_info=True)

            # 保存引用以便后续清理
            app.state.social_config = social_config
            app.state.message_bus = message_bus
            app.state.session_mapper = session_mapper
            app.state.agent_bridge = agent_bridge
            app.state.channel_manager = channel_manager

            enabled_platforms = [name for name, config in [
                ("qq", social_config.qq),
                ("weixin", social_config.weixin)
            ] if config.enabled]

            logger.info(
                "social_platform_service_started",
                enabled_platforms=enabled_platforms,
                agent_bridge_running=True,
                channel_manager_running=True
            )
    except Exception as e:
        logger.error("social_platform_service_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_social_platforms")

    # 2. 初始化数据库（如果配置了DATABASE_URL）
    if os.getenv("DATABASE_URL"):
        try:
            # 初始化数据库连接和表结构
            await init_db()
            logger.info("database_initialized")

            # 启动数据获取后台（如果启用）
            if os.getenv("ENABLE_AUTO_FETCHING", "true").lower() == "true":
                initialize_fetchers()
                logger.info("data_fetchers_started")
            else:
                logger.info("data_fetchers_disabled")

            # 启动知识库文档处理队列
            try:
                from app.knowledge_base.tasks import start_processing_queue
                await start_processing_queue()
                logger.info("knowledge_base_processing_queue_started")
            except Exception as e:
                logger.warning("knowledge_base_queue_start_failed", error=str(e))

            # 预热知识库检索模型（Embedding + Reranker）
            try:
                await warmup_knowledge_base_models()
            except Exception as e:
                logger.warning("knowledge_base_warmup_failed", error=str(e))

        except Exception as e:
            logger.error("database_initialization_failed", error=str(e), exc_info=True)
            logger.warning("continuing_without_database_features")
    else:
        logger.info("weather_database_disabled", reason="no_DATABASE_URL")


async def warmup_knowledge_base_models():
    """预热知识库相关模型，避免首次检索时延迟"""
    import time
    start = time.time()
    logger.info("knowledge_base_models_warmup_starting")
    
    # 1. 预热Embedding模型（BGE-M3）
    try:
        from app.knowledge_base import get_vector_store
        vector_store = get_vector_store()
        # 执行一次dummy embedding来预热模型
        _ = vector_store.embedding_model.encode(["预热测试"], show_progress_bar=False)
        logger.info("embedding_model_warmed_up")
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))
    
    # 2. 预热Reranker模型（使用全局单例）
    try:
        from app.knowledge_base.service import get_reranker
        reranker = get_reranker()
        if reranker:
            # 执行一次dummy predict来预热
            _ = reranker.predict([("预热", "测试")])
            logger.info("reranker_model_warmed_up")
        else:
            logger.info("reranker_warmup_skipped", reason="reranker_not_available")
    except Exception as e:
        logger.warning("reranker_warmup_failed", error=str(e))
    
    elapsed = time.time() - start
    logger.info("knowledge_base_models_warmup_completed", elapsed_seconds=round(elapsed, 2))


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("application_shutting_down")

    # 停止定时任务系统
    try:
        from app.scheduled_tasks import stop_service
        stop_service()
        logger.info("scheduled_task_service_stopped")
    except Exception as e:
        logger.warning("scheduled_task_service_stop_failed", error=str(e))

    # 停止社交平台服务
    try:
        # 取消后台任务
        if hasattr(app.state, "channel_manager_task") and app.state.channel_manager_task:
            app.state.channel_manager_task.cancel()
            try:
                await app.state.channel_manager_task
            except asyncio.CancelledError:
                pass
            logger.info("channel_manager_task_cancelled")

        if hasattr(app.state, "agent_bridge_task") and app.state.agent_bridge_task:
            app.state.agent_bridge_task.cancel()
            try:
                await app.state.agent_bridge_task
            except asyncio.CancelledError:
                pass
            logger.info("agent_bridge_task_cancelled")

        # 停止Channel管理器
        if hasattr(app.state, "channel_manager") and app.state.channel_manager:
            await app.state.channel_manager.stop_all()
            logger.info("channel_manager_stopped")

        # 停止Agent桥接层
        if hasattr(app.state, "agent_bridge") and app.state.agent_bridge:
            await app.state.agent_bridge.stop()
            logger.info("agent_bridge_stopped")

        # 保存会话映射器状态
        if hasattr(app.state, "session_mapper") and app.state.session_mapper:
            await app.state.session_mapper.save()
            # 清理过期会话
            cleaned = await app.state.session_mapper.cleanup_expired(ttl_hours=24)
            logger.info("session_mapper_saved_and_cleaned", cleaned_count=cleaned)

        logger.info("social_platform_service_stopped")
    except Exception as e:
        logger.warning("social_platform_service_stop_failed", error=str(e))

    # 1. 停止数据获取后台
    try:
        stop_fetchers()
        logger.info("data_fetchers_stopped")
    except Exception as e:
        logger.error("fetchers_stop_failed", error=str(e))

    # 1.5. 停止知识库处理队列
    try:
        from app.knowledge_base.tasks import stop_processing_queue
        await stop_processing_queue()
        logger.info("knowledge_base_processing_queue_stopped")
    except Exception as e:
        logger.warning("knowledge_base_queue_stop_failed", error=str(e))

    # 2. 关闭数据库连接
    try:
        if os.getenv("DATABASE_URL"):
            await close_db()
            logger.info("database_closed")
    except Exception as e:
        logger.error("database_close_failed", error=str(e))

    # 3. 关闭HTTP客户端
    await http_client.close()


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "air-pollution-traceability-api",
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
            "quick_trace_alert": "POST /api/quick-trace/alert - 污染高值告警快速溯源",
            "quick_trace_health": "GET /api/quick-trace/health - 快速溯源健康检查",
            "quick_trace_cities": "GET /api/quick-trace/supported-cities - 支持的城市列表",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "air-pollution-traceability-api",
        "version": "1.0.0",
        "environment": settings.environment,
        "llm_provider": settings.llm_provider,
    }


@app.get("/api/system/status")
async def system_status():
    """
    获取系统状态信息

    包括：
    - Fetchers运行状态
    - LLM Tools注册情况
    - 数据库连接状态
    """
    try:
        status = {
            "service": "air-pollution-traceability-api",
            "version": "1.0.0",
            "timestamp": structlog.processors.TimeStamper(fmt="iso").__call__(None, None, {})["timestamp"],
        }

        # 数据库状态
        if os.getenv("DATABASE_URL"):
            status["database"] = {
                "enabled": True,
                "url": os.getenv("DATABASE_URL").split("@")[1] if "@" in os.getenv("DATABASE_URL", "") else "configured"
            }
        else:
            status["database"] = {"enabled": False}

        # Fetchers状态
        try:
            scheduler = get_fetcher_scheduler()
            status["fetchers"] = scheduler.get_status()
        except Exception as e:
            status["fetchers"] = {"error": str(e)}

        # Tools状态
        try:
            registry = get_tool_registry()
            status["llm_tools"] = {
                "registered": registry.list_tools(),
                "count": len(registry.list_tools()),
                "statistics": registry.get_stats()
            }
        except Exception as e:
            status["llm_tools"] = {"error": str(e)}

        return status

    except Exception as e:
        logger.error("system_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """
    Get public configuration for frontend.

    Returns:
        Configuration including AMap key and feature flags
    """
    try:
        logger.info("config_requested")

        config = ConfigResponse(
            amapPublicKey=settings.amap_public_key,
            features={
                "dynamicPreferred": True,
                "echarts": True,
            },
        )

        return config

    except Exception as e:
        logger.error("config_fetch_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch configuration")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal server error: {str(exc)}",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
