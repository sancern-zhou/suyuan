from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import database
from app.lifecycle import database as lifecycle_database
from app.lifecycle import startup


def test_social_binding_migration_preserves_legacy_rows_and_adds_unique_active_indexes():
    backend_dir = Path(__file__).resolve().parents[2]
    sql = (backend_dir / "app/db/migrations/007_add_platform_social_bindings.sql").read_text()

    assert "ADD COLUMN IF NOT EXISTS platform_user_id" in sql
    assert "CREATE TABLE IF NOT EXISTS weixin_scan_tasks" in sql
    assert "WHERE status = 'active'" in sql
    assert "UPDATE social_users SET platform_user_id" not in sql


@pytest.mark.asyncio
async def test_init_db_ensures_social_binding_schema(monkeypatch):
    calls = []

    class FakeConnection:
        async def run_sync(self, operation):
            calls.append(("create_all", operation))

    class BeginContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def begin(self):
            return BeginContext()

    async def fake_uploaded_files_schema(connection):
        calls.append(("uploaded_files", connection))

    async def fake_social_binding_schema(connection):
        calls.append(("social_binding", connection))

    monkeypatch.setattr(database, "engine", FakeEngine())
    monkeypatch.setattr(database, "_ensure_uploaded_files_schema", fake_uploaded_files_schema)
    monkeypatch.setattr(
        database,
        "_ensure_social_binding_schema",
        fake_social_binding_schema,
        raising=False,
    )

    await database.init_db()

    assert [name for name, _ in calls] == [
        "create_all",
        "uploaded_files",
        "social_binding",
    ]


@pytest.mark.asyncio
async def test_social_binding_schema_uses_idempotent_postgresql_ddl():
    statements = []

    class FakeDialect:
        name = "postgresql"

    class FakeConnection:
        dialect = FakeDialect()

        async def execute(self, statement):
            statements.append(str(statement))

    await database._ensure_social_binding_schema(FakeConnection())

    ddl = "\n".join(statements)
    for column in (
        "platform_user_id",
        "platform_username",
        "platform_display_name",
        "account_id",
        "ilink_user_id",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in ddl

    assert "CREATE TABLE IF NOT EXISTS weixin_scan_tasks" in ddl
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_platform_user" in ddl
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_ilink_user" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_social_users_active_account" in ddl
    assert ddl.count("WHERE status = 'active'") == 2


@pytest.mark.asyncio
async def test_social_binding_schema_skips_non_postgresql_dialects():
    statements = []

    class FakeDialect:
        name = "sqlite"

    class FakeConnection:
        dialect = FakeDialect()

        async def execute(self, statement):
            statements.append(str(statement))

    await database._ensure_social_binding_schema(FakeConnection())

    assert statements == []


def _patch_worker_startup(monkeypatch, calls, *, database_ready):
    async def record(name, *args, **kwargs):
        calls.append(name)
        if name == "init_database_and_fetchers":
            return database_ready
        return None

    monkeypatch.setattr(startup.settings, "app_role", "worker", raising=False)
    monkeypatch.setattr(startup, "start_nacos", lambda app: record("start_nacos"))
    monkeypatch.setattr(
        startup,
        "initialize_tools_and_agents",
        lambda: record("initialize_tools_and_agents"),
    )
    monkeypatch.setattr(
        startup,
        "init_database_and_fetchers",
        lambda: record("init_database_and_fetchers"),
    )
    monkeypatch.setattr(
        startup,
        "start_scheduled_task_service",
        lambda: record("start_scheduled_task_service"),
    )
    monkeypatch.setattr(
        startup,
        "start_social_platform_service",
        lambda app: record("start_social_platform_service"),
    )
    monkeypatch.setattr(
        startup,
        "start_social_worker_api_service",
        lambda app: record("start_social_worker_api_service"),
    )
    monkeypatch.setattr(
        startup,
        "start_knowledge_base_services",
        lambda: record("start_knowledge_base_services"),
    )


@pytest.mark.asyncio
async def test_worker_social_services_start_only_after_database_is_ready(monkeypatch):
    calls = []
    _patch_worker_startup(monkeypatch, calls, database_ready=True)

    await startup.run_startup(SimpleNamespace(state=SimpleNamespace()))

    assert calls == [
        "start_nacos",
        "initialize_tools_and_agents",
        "init_database_and_fetchers",
        "start_scheduled_task_service",
        "start_social_platform_service",
        "start_social_worker_api_service",
        "start_knowledge_base_services",
    ]


@pytest.mark.asyncio
async def test_database_failure_skips_worker_social_services(monkeypatch):
    calls = []
    _patch_worker_startup(monkeypatch, calls, database_ready=False)

    await startup.run_startup(SimpleNamespace(state=SimpleNamespace()))

    assert calls == [
        "start_nacos",
        "initialize_tools_and_agents",
        "init_database_and_fetchers",
        "start_scheduled_task_service",
    ]


@pytest.mark.asyncio
async def test_web_role_starts_only_document_processing_queue(monkeypatch):
    calls = []

    async def record(name):
        calls.append(name)
        return True

    monkeypatch.setattr(startup.settings, "app_role", "web")
    monkeypatch.setattr(startup, "start_nacos", lambda app: record("start_nacos"))
    monkeypatch.setattr(
        startup,
        "initialize_tools_and_agents",
        lambda: record("initialize_tools_and_agents"),
    )
    monkeypatch.setattr(startup, "init_database", lambda: record("init_database"))
    monkeypatch.setattr(
        startup,
        "start_document_processing_queue",
        lambda: record("start_document_processing_queue"),
    )

    await startup.run_startup(SimpleNamespace(state=SimpleNamespace()))

    assert calls == [
        "start_nacos",
        "initialize_tools_and_agents",
        "init_database",
        "start_document_processing_queue",
    ]


@pytest.mark.asyncio
async def test_fetcher_failure_does_not_mark_database_unavailable(monkeypatch):
    async def database_ready():
        return True

    def fail_fetcher_startup():
        raise RuntimeError("fetcher startup failed")

    monkeypatch.setenv("ENABLE_AUTO_FETCHING", "true")
    monkeypatch.setattr(lifecycle_database, "init_database", database_ready)
    monkeypatch.setattr(lifecycle_database, "initialize_fetchers", fail_fetcher_startup)

    assert await lifecycle_database.init_database_and_fetchers() is True
