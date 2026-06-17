"""Application shutdown orchestration extracted from app/main.py.

Shutdown order is intentional:
1. Stop scheduled jobs so no new Agent work starts.
2. Stop social channels and AgentBridge background tasks.
3. Stop data fetchers before database teardown.
4. Stop knowledge base queue before closing database sessions.
5. Close database connections.
6. Close shared HTTP client last.
"""

from fastapi import FastAPI
import structlog

from app.lifecycle.database import close_database, stop_data_fetchers
from app.lifecycle.knowledge_base import stop_knowledge_base_services
from app.lifecycle.roles import normalize_app_role, starts_background_services
from app.lifecycle.scheduled import stop_scheduled_task_service
from app.lifecycle.social import stop_social_platform_service
from app.lifecycle.social_worker_api import stop_social_worker_api_service
from app.utils.http_client import http_client
from config.settings import settings

logger = structlog.get_logger()


async def run_shutdown(app: FastAPI) -> None:
    """Run application shutdown resource cleanup."""
    app_role = normalize_app_role(settings.app_role)
    logger.info("application_shutting_down", app_role=app_role)

    if starts_background_services(app_role):
        await stop_social_worker_api_service(app)
        await stop_scheduled_task_service()
        await stop_social_platform_service(app)
        await stop_data_fetchers()
        await stop_knowledge_base_services()
    await close_database()
    await http_client.close()
