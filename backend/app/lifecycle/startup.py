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

from app.lifecycle.database import init_database_and_fetchers
from app.lifecycle.knowledge_base import start_knowledge_base_services
from app.lifecycle.scheduled import start_scheduled_task_service
from app.lifecycle.social import start_social_platform_service
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

    logger.info(
        "application_starting",
        environment=settings.environment,
        host=settings.host,
        port=settings.port,
        llm_provider=settings.llm_provider,
    )

    await initialize_tools_and_agents()
    await start_scheduled_task_service()
    await start_social_platform_service(app)

    database_ready = await init_database_and_fetchers()
    if database_ready:
        await start_knowledge_base_services()

