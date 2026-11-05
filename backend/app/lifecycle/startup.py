"""Application startup orchestration extracted from app/main.py.

Startup order is intentional:
1. Set working directory so tools and agents resolve project-relative paths.
2. Initialize LLM tools and refresh long-lived Agent instances.
3. Initialize database and fetchers; this also applies compatibility migrations.
4. Start scheduled tasks; task executions create Agents and need tools ready.
5. Start social channels only when the database is ready.
6. Start knowledge base services only when database initialization succeeded.
"""

import os
from pathlib import Path

from fastapi import FastAPI
import structlog

from app.lifecycle.database import init_database, init_database_and_fetchers
from app.lifecycle.knowledge_base import (
    start_knowledge_base_services,
)
from app.lifecycle.loop_watchdog import start_loop_watchdog
from app.lifecycle.nacos import start_nacos
from app.lifecycle.roles import normalize_app_role, starts_background_services
from app.lifecycle.scheduled import start_scheduled_task_service
from app.lifecycle.social import start_social_platform_service
from app.lifecycle.social_worker_api import start_social_worker_api_service
from app.lifecycle.tools import initialize_tools_and_agents
from config.settings import settings

logger = structlog.get_logger()


async def run_startup(app: FastAPI) -> None:
    """Run application startup resource initialization."""
    backend_dir = Path(__file__).resolve().parents[2]
    os.chdir(backend_dir)
    start_loop_watchdog()
    logger.info(
        "working_directory_set",
        cwd=os.getcwd(),
        backend_dir=str(backend_dir),
    )

    app_role = normalize_app_role(settings.app_role)

    logger.info(
        "application_starting",
        environment=settings.environment,
        host=settings.host,
        port=settings.port,
        llm_provider=settings.llm_provider,
        app_role=app_role,
    )

    await start_nacos(app)

    await initialize_tools_and_agents()

    if app_role == "web":
        # Web 进程独占 SSE agent run 的取消状态键，且部署为单实例：启动瞬间
        # 进程内不可能有存活 run，非终态状态全部是上次硬杀/重启留下的孤儿。
        # 不回收则 REGISTER 拒绝新 run、暂停屏障等满超时，会话被锁死到 TTL。
        try:
            from app.agent.runtime.cancellation import cancellation_registry

            recovered = await cancellation_registry.recover_stale_states()
            if recovered:
                logger.info("cancellation_stale_states_recovered", recovered=recovered)
        except Exception as e:
            logger.warning("cancellation_stale_state_recovery_skipped", error=str(e))

    if starts_background_services(app_role):
        database_ready = await init_database_and_fetchers()
        await start_scheduled_task_service()

        if database_ready:
            await start_social_platform_service(app)
            if app_role == "worker":
                await start_social_worker_api_service(app)
            await start_knowledge_base_services()
            from app.api.knowledge_graph_routes import start_graph_build_recovery

            start_graph_build_recovery()
        else:
            logger.warning(
                "database_dependent_services_skipped",
                services=["social_platform", "social_worker_api", "knowledge_base"],
            )
    else:
        database_ready = await init_database()
        if database_ready:
            from app.api.knowledge_graph_routes import start_graph_build_recovery

            start_graph_build_recovery()
        else:
            logger.warning(
                "database_dependent_services_skipped",
                services=["knowledge_base_processing_queue"],
            )
        try:
            from app.project_config.loader import load_project_context
            from config.settings import settings as app_settings

            if load_project_context(app_settings.project_id).manifest.scheduled_tasks_enabled:
                from app.scheduled_tasks import init_service

                init_service(recover_interrupted=False)
        except Exception as e:
            logger.warning(
                "scheduled_task_service_init_skipped_for_web_role",
                error=str(e),
            )
        logger.info(
            "background_services_skipped_for_web_role",
            app_role=app_role,
            database_ready=database_ready,
            knowledge_base_models="lazy_on_request",
        )
