"""Dedicated engine for conversation-history and scheduled-task-execution storage.

Session messages and task executions carry large JSONB payloads that are
latency-sensitive, so deployments may keep them on a local PostgreSQL instance
separate from ``DATABASE_URL``.  Tables routed here: ``sessions``,
``session_messages``, ``session_resources``, ``session_resource_versions`` and
``scheduled_task_executions``.  When ``SESSION_DATABASE_URL`` is unset the
module falls back to ``DATABASE_URL``, preserving legacy single-database
behavior.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import (
    DATABASE_URL,
    _normalize_async_database_url,
)

import os

SESSION_DATABASE_URL = _normalize_async_database_url(
    os.getenv("SESSION_DATABASE_URL") or DATABASE_URL
)

session_engine = create_async_engine(
    SESSION_DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=120,
    connect_args={
        "command_timeout": 300,
        "server_settings": {
            "statement_timeout": "300000",
        },
    },
)

session_async_session = async_sessionmaker(
    session_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session_db():
    """FastAPI dependency yielding a session on the session-data database."""
    async with session_async_session() as session:
        yield session
