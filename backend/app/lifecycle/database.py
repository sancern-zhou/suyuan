"""Database and fetcher lifecycle extracted from app/main.py.

Dependency note:
- Database initialization is gated by DATABASE_URL.
- Fetchers are started only after database initialization because they store data.
- Knowledge base queue/model warmup is handled in app.lifecycle.knowledge_base
  and should run after init_database_and_fetchers().
"""

import os

import structlog

from app.db.database import check_db_connection, close_db, init_db
from app.services.lifecycle_manager import initialize_fetchers, stop_fetchers

logger = structlog.get_logger()


async def init_database() -> bool:
    """Initialize database-backed features without starting background fetchers.

    Returns:
        True when DATABASE_URL is configured and database initialization
        completed successfully; False when database-backed features should be
        skipped.
    """
    if not os.getenv("DATABASE_URL"):
        logger.info("weather_database_disabled", reason="no_DATABASE_URL")
        return False

    try:
        initialize_schema = os.getenv(
            "DATABASE_SCHEMA_INIT_ON_STARTUP", "true"
        ).lower() in {"1", "true", "yes", "on"}
        if initialize_schema:
            await init_db()
            logger.info("database_initialized")
        else:
            await check_db_connection()
            logger.info("database_connection_verified", schema_managed_externally=True)
        return True
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_database_features")
        return False


async def init_database_and_fetchers() -> bool:
    """Initialize the database and optionally start data fetchers.

    The return value represents database readiness. Fetcher startup failures do
    not make other database-backed services unavailable.
    """
    database_ready = await init_database()
    if not database_ready:
        return False

    try:
        if os.getenv("ENABLE_AUTO_FETCHING", "true").lower() == "true":
            initialize_fetchers()
            logger.info("data_fetchers_started")
        else:
            logger.info("data_fetchers_disabled")
        return True
    except Exception as e:
        logger.error("data_fetchers_initialization_failed", error=str(e), exc_info=True)
        logger.warning("continuing_without_data_fetchers")
        return True


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
