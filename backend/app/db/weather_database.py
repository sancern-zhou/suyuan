"""Dedicated database connection for meteorological time-series data."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import DATABASE_URL, _normalize_async_database_url
from app.db.pool_config import pool_int


def resolve_weather_database_url() -> str:
    """Return the dedicated weather URL, falling back for older deployments."""
    return _normalize_async_database_url(
        os.getenv("WEATHER_DATABASE_URL") or DATABASE_URL
    )


WEATHER_DATABASE_URL = resolve_weather_database_url()

weather_engine = create_async_engine(
    WEATHER_DATABASE_URL,
    echo=False,
    pool_size=pool_int("WEATHER_DATABASE_POOL_SIZE", 10),
    max_overflow=pool_int("WEATHER_DATABASE_MAX_OVERFLOW", 20),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=120,
    connect_args={
        "command_timeout": 300,
        "server_settings": {"statement_timeout": "300000"},
    },
)

weather_async_session = async_sessionmaker(
    weather_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def close_weather_db() -> None:
    await weather_engine.dispose()
