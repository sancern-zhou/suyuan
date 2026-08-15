from types import SimpleNamespace

import pytest

from app.lifecycle import startup


@pytest.mark.asyncio
async def test_web_role_does_not_start_background_services(monkeypatch):
    calls = []

    async def record(name, *args, **kwargs):
        calls.append(name)
        if name == "init_database_only":
            return True
        return None

    monkeypatch.setattr(startup.settings, "app_role", "web", raising=False)
    monkeypatch.setattr(
        startup,
        "initialize_tools_and_agents",
        lambda: record("initialize_tools_and_agents"),
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
        "init_database",
        lambda: record("init_database"),
    )
    monkeypatch.setattr(
        startup,
        "init_database_and_fetchers",
        lambda: record("init_database_and_fetchers"),
    )
    monkeypatch.setattr(
        startup,
        "start_knowledge_base_services",
        lambda: record("start_knowledge_base_services"),
    )

    await startup.run_startup(SimpleNamespace())

    assert calls == ["initialize_tools_and_agents", "init_database"]


@pytest.mark.asyncio
async def test_all_role_keeps_legacy_single_process_startup(monkeypatch):
    calls = []

    async def record(name, *args, **kwargs):
        calls.append(name)
        if name == "init_database_and_fetchers":
            return True
        return None

    monkeypatch.setattr(startup.settings, "app_role", "all", raising=False)
    monkeypatch.setattr(
        startup,
        "initialize_tools_and_agents",
        lambda: record("initialize_tools_and_agents"),
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
        "init_database",
        lambda: record("init_database"),
    )
    monkeypatch.setattr(
        startup,
        "init_database_and_fetchers",
        lambda: record("init_database_and_fetchers"),
    )
    monkeypatch.setattr(
        startup,
        "start_knowledge_base_services",
        lambda: record("start_knowledge_base_services"),
    )

    await startup.run_startup(SimpleNamespace())

    assert calls == [
        "initialize_tools_and_agents",
        "start_scheduled_task_service",
        "start_social_platform_service",
        "init_database_and_fetchers",
        "start_knowledge_base_services",
    ]


@pytest.mark.asyncio
async def test_worker_role_starts_internal_social_worker_api(monkeypatch):
    calls = []

    async def record(name, *args, **kwargs):
        calls.append(name)
        if name == "init_database_and_fetchers":
            return True
        return None

    monkeypatch.setattr(startup.settings, "app_role", "worker", raising=False)
    monkeypatch.setattr(
        startup,
        "initialize_tools_and_agents",
        lambda: record("initialize_tools_and_agents"),
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
        "init_database_and_fetchers",
        lambda: record("init_database_and_fetchers"),
    )
    monkeypatch.setattr(
        startup,
        "start_knowledge_base_services",
        lambda: record("start_knowledge_base_services"),
    )

    await startup.run_startup(SimpleNamespace(state=SimpleNamespace()))

    assert calls == [
        "initialize_tools_and_agents",
        "start_scheduled_task_service",
        "start_social_platform_service",
        "start_social_worker_api_service",
        "init_database_and_fetchers",
        "start_knowledge_base_services",
    ]
