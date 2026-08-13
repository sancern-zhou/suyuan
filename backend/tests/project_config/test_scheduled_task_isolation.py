import pytest

from app.lifecycle import scheduled
from config.settings import settings


@pytest.mark.asyncio
async def test_jiangsu_does_not_initialize_scheduled_task_service(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    def unexpected_init(*args, **kwargs):
        raise AssertionError("scheduled task service must remain disabled for Jiangsu")

    monkeypatch.setattr("app.scheduled_tasks.init_service", unexpected_init)

    await scheduled.start_scheduled_task_service()
