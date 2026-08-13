"""Dedicated database connection for knowledge metadata and documents."""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import DATABASE_URL, _normalize_async_database_url


KNOWLEDGE_DATABASE_URL = _normalize_async_database_url(
    os.getenv("KNOWLEDGE_DATABASE_URL") or DATABASE_URL
)

knowledge_engine = create_async_engine(
    KNOWLEDGE_DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=120,
    connect_args={
        "command_timeout": 300,
        "server_settings": {"statement_timeout": "300000"},
    },
)

knowledge_async_session = async_sessionmaker(
    knowledge_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_knowledge_db() -> AsyncGenerator[AsyncSession, None]:
    async with knowledge_async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_knowledge_db() -> None:
    await knowledge_engine.dispose()
