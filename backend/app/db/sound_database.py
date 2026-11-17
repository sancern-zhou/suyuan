"""Dedicated database connection for the sound (noise) monitoring data store."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import DATABASE_URL, _normalize_async_database_url
from app.db.pool_config import pool_int


def resolve_sound_database_url() -> str:
    """Return the sound-data URL, falling back to a sibling database of DATABASE_URL."""
    explicit = (os.getenv("SOUND_DATA_DATABASE_URL") or "").strip()
    if explicit:
        return _normalize_async_database_url(explicit)
    base, _, _ = DATABASE_URL.rpartition("/")
    return f"{base}/sound_data"


SOUND_DATA_DATABASE_URL = resolve_sound_database_url()

sound_engine = create_async_engine(
    SOUND_DATA_DATABASE_URL,
    echo=False,
    pool_size=pool_int("SOUND_DATABASE_POOL_SIZE", 5),
    max_overflow=pool_int("SOUND_DATABASE_MAX_OVERFLOW", 10),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=120,
    connect_args={
        "command_timeout": 300,
        "server_settings": {"statement_timeout": "300000"},
    },
)

sound_async_session = async_sessionmaker(
    sound_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def close_sound_db() -> None:
    await sound_engine.dispose()
