"""Database and fetcher lifecycle extracted from app/main.py.

Dependency note:
- Database initialization is gated by DATABASE_URL.
- Fetchers are started only after database initialization because they store data.
- Knowledge base queue/model warmup is handled in app.lifecycle.knowledge_base
  and should run after init_database_and_fetchers().
"""

import os

import structlog

from app.db.database import close_db, init_db
from app.services.lifecycle_manager import initialize_fetchers, stop_fetchers

logger = structlog.get_logger()


async def init_database_and_fetchers() -> bool:
    """Initialize database and optionally start data fetchers.

    Returns:
        True when DATABASE_URL is configured and database initialization
        completed successfully; False when database-backed features should be
        skipped.
    """
    if not os.getenv("DATABASE_URL"):
        logger.info("weather_database_disabled", reason="no_DATABASE_URL")
        return False

    try:
        await init_db()
        logger.info("database_initialized")

        if os.getenv("ENABLE_AUTO_FETCHING", "true").lower() == "true":
            initialize_fetchers()
            logger.info("data_fetchers_started")
        else:
            logger.info("data_fetchers_disabled")

        return True
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_database_features")
        return False


async def stop_data_fetchers() -> None:
    """Stop background data fetchers."""
    try:
        stop_fetchers()
        logger.info("data_fetchers_stopped")
    except Exception as e:
        logger.error("fetchers_stop_failed", error=str(e))


async def close_database() -> None:
    """Close database connections when DATABASE_URL is configured."""
    try:
        if os.getenv("DATABASE_URL"):
            await close_db()
            logger.info("database_closed")
    except Exception as e:
        logger.error("database_close_failed", error=str(e))

