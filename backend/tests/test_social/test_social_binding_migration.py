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
async def test_init_db_ensures_runtime_schemas(monkeypatch):
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

    async def fake_session_resources_schema(connection):
        calls.append(("session_resources", connection))

    async def fake_coordinator_quick_prompts_schema(connection):
        calls.append(("coordinator_quick_prompts", connection))

    monkeypatch.setattr(database, "engine", FakeEngine())
    monkeypatch.setattr(database, "_ensure_uploaded_files_schema", fake_uploaded_files_schema)
    monkeypatch.setattr(
        database,
        "_ensure_session_resources_schema",
        fake_session_resources_schema,
        raising=False,
    )
    monkeypatch.setattr(
        database,
        "_ensure_coordinator_quick_prompts_schema",
        fake_coordinator_quick_prompts_schema,
        raising=False,
    )

    await database.init_db()

    assert [name for name, _ in calls] == [
        "create_all",
        "create_all",
        "uploaded_files",
        "session_resources",
        "coordinator_quick_prompts",
    ]


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
        "start_social_worker_api_service",
        lambda app: record("start_social_worker_api_service"),
    )
    monkeypatch.setattr(
        startup,
        "start_knowledge_base_services",
        lambda: record("start_knowledge_base_services"),
    )
    # run_startup 在 worker 就绪路径内即时 import 并调用图谱恢复任务
    monkeypatch.setattr(
        "app.api.knowledge_graph_routes.start_graph_build_recovery",
        lambda: calls.append("start_graph_build_recovery"),
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
        "start_social_worker_api_service",
        "start_knowledge_base_services",
        "start_graph_build_recovery",
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
async def test_web_role_skips_knowledge_base_background_services(monkeypatch):
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

    await startup.run_startup(SimpleNamespace(state=SimpleNamespace()))

    assert calls == [
        "start_nacos",
        "initialize_tools_and_agents",
        "init_database",
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
