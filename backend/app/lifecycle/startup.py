"""Application startup orchestration extracted from app/main.py.

Startup order is intentional:
1. Set working directory so tools and agents resolve project-relative paths.
2. Initialize LLM tools and refresh long-lived Agent instances.
3. Start scheduled tasks; task executions create Agents and need tools ready.
4. Start social channels; AgentBridge also depends on the tool-ready Agent.
5. Initialize database and fetchers; fetchers require DB-backed storage.
6. Start knowledge base services only when DB initialization succeeded.
"""

import os
from pathlib import Path

from fastapi import FastAPI
import structlog

from app.lifecycle.database import init_database, init_database_and_fetchers
from app.lifecycle.knowledge_base import start_knowledge_base_services
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

    await initialize_tools_and_agents()

    if starts_background_services(app_role):
        await start_scheduled_task_service()
        await start_social_platform_service(app)
        if app_role == "worker":
            await start_social_worker_api_service(app)

        database_ready = await init_database_and_fetchers()
        if database_ready:
            await start_knowledge_base_services()
    else:
        database_ready = await init_database()
        logger.info(
            "background_services_skipped_for_web_role",
            app_role=app_role,
            database_ready=database_ready,
        )
