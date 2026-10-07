from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import social_app_routes, scheduled_task_routes
from app.auth.models import CurrentUser


@pytest.mark.asyncio
async def test_app_tasks_use_normalized_identity(monkeypatch):
    user = CurrentUser(id="app:android:alice", username="alice", display_name="Alice")
    seen = {}

    async def list_tasks(**kwargs):
        seen.update(kwargs)
        return ["visible-task"]

    monkeypatch.setattr(scheduled_task_routes, "list_tasks", list_tasks)
    result = await social_app_routes.app_scheduled_tasks(SimpleNamespace(as_current_user=lambda: user))
    assert result == ["visible-task"]
    assert seen == {"enabled_only": False, "user": user}


@pytest.mark.asyncio
async def test_app_results_deny_unrelated_task_before_query(monkeypatch):
    task = SimpleNamespace(task_id="private", owner_user_id="bob", workspace_entry=None)
    service = SimpleNamespace(get_task=lambda _: task)
    monkeypatch.setattr(scheduled_task_routes, "get_scheduled_task_service", lambda: service)
    user = CurrentUser(id="app:android:alice", username="alice", display_name="Alice")
    identity = SimpleNamespace(as_current_user=lambda: user)
    with pytest.raises(HTTPException) as error:
        await social_app_routes.app_scheduled_results(task_id="private", identity=identity)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_app_facets_allow_visible_system_workspace_task(monkeypatch):
    task = SimpleNamespace(task_id="system", owner_user_id="system", created_by="system", workspace_entry=SimpleNamespace(enabled=True))
    service = SimpleNamespace(get_task=lambda _: task, list_task_result_facets=lambda **kwargs: {"stations": [{"station_id": "one"}], "pollutants": ["O3"]})
    monkeypatch.setattr(scheduled_task_routes, "get_scheduled_task_service", lambda: service)
    user = CurrentUser(id="app:android:alice", username="alice", display_name="Alice")
    result = await social_app_routes.app_scheduled_facets("system", SimpleNamespace(as_current_user=lambda: user))
    assert result["pollutants"] == ["O3"]
