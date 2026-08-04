import pytest

from app.lifecycle import database as lifecycle_database


@pytest.mark.asyncio
async def test_managed_schema_startup_only_checks_connectivity(monkeypatch):
    calls = []

    async def init_schema():
        calls.append("init_schema")

    async def check_connection():
        calls.append("check_connection")

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example/test")
    monkeypatch.setenv("DATABASE_SCHEMA_INIT_ON_STARTUP", "false")
    monkeypatch.setattr(lifecycle_database, "init_db", init_schema)
    monkeypatch.setattr(lifecycle_database, "check_db_connection", check_connection)

    assert await lifecycle_database.init_database() is True
    assert calls == ["check_connection"]


@pytest.mark.asyncio
async def test_schema_initialization_is_opt_in(monkeypatch):
    calls = []

    async def init_schema():
        calls.append("init_schema")

    async def check_connection():
        calls.append("check_connection")

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example/test")
    monkeypatch.delenv("DATABASE_SCHEMA_INIT_ON_STARTUP", raising=False)
    monkeypatch.setattr(lifecycle_database, "init_db", init_schema)
    monkeypatch.setattr(lifecycle_database, "check_db_connection", check_connection)

    assert await lifecycle_database.init_database() is True
    assert calls == ["check_connection"]


@pytest.mark.asyncio
async def test_explicit_schema_initialization_runs_migrations(monkeypatch):
    calls = []

    async def init_schema():
        calls.append("init_schema")

    async def check_connection():
        calls.append("check_connection")

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example/test")
    monkeypatch.setenv("DATABASE_SCHEMA_INIT_ON_STARTUP", "true")
    monkeypatch.setattr(lifecycle_database, "init_db", init_schema)
    monkeypatch.setattr(lifecycle_database, "check_db_connection", check_connection)

    assert await lifecycle_database.init_database() is True
    assert calls == ["init_schema"]
