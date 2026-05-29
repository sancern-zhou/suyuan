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
from app.lifecycle.scheduled import stop_scheduled_task_service
from app.lifecycle.social import stop_social_platform_service
from app.utils.http_client import http_client

logger = structlog.get_logger()


async def run_shutdown(app: FastAPI) -> None:
    """Run application shutdown resource cleanup."""
    logger.info("application_shutting_down")

    await stop_scheduled_task_service()
    await stop_social_platform_service(app)
    await stop_data_fetchers()
    await stop_knowledge_base_services()
    await close_database()
    await http_client.close()

