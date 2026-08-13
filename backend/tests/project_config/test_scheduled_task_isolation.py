import pytest

from app.lifecycle import scheduled
from config.settings import settings


@pytest.mark.asyncio
async def test_jiangsu_initializes_scheduled_task_service_and_seeds_defaults(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")
    calls = []

    class Service:
        def get_task(self, task_id):
            return None

        def create_task(self, task):
            calls.append(("create", task.task_id))
            return task

    monkeypatch.setattr("app.scheduled_tasks.init_service", lambda **_: Service())
    monkeypatch.setattr("app.scheduled_tasks.start_service", lambda: calls.append(("start", None)))

    await scheduled.start_scheduled_task_service()

    assert calls == [
        ("create", "jiangsu_station_fault_diagnosis"),
        ("start", None),
    ]
