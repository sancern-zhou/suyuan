"""任务结果接口对分享任务（owner=system + workspace）开放只读访问。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scheduled_task_routes import router
from app.auth.dependencies import optional_current_user, require_current_user
from app.auth.models import CurrentUser
from app.scheduled_tasks import ScheduledTask, ScheduleType
from app.scheduled_tasks.models.result import TaskResult

_USER = CurrentUser(id="2", username="周三成", display_name="周三成")


def _result(**overrides) -> TaskResult:
    payload = dict(
        execution_id="exec-share-1",
        task_id="task_shared_system",
        task_name="系统分享任务",
        session_id="session-share-1",
        status="success",
        started_at=datetime(2026, 10, 8, 8, 0, 0),
        completed_at=datetime(2026, 10, 8, 8, 5, 0),
        city="许昌市",
        station_id=None,
        station_name=None,
        pollutant=None,
        conclusion="结论",
        findings=[],
        image_paths=[],
        document_paths=[],
        evidence_package_paths=[],
        report_refs=[],
    )
    payload.update(overrides)
    return TaskResult(**payload)


def _shared_task() -> ScheduledTask:
    return ScheduledTask(
        task_id="task_shared_system",
        name="系统分享任务",
        description="owner=system 的 workspace 分享任务",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试",
        timeout_seconds=300,
        workspace_entry={"enabled": True},
    )


def _private_task() -> ScheduledTask:
    return ScheduledTask(
        task_id="task_private",
        name="私有任务",
        description="owner=其他人",
        schedule_type=ScheduleType.EVERY_30MIN,
        enabled=True,
        prompt="测试",
        timeout_seconds=300,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: _USER
    app.dependency_overrides[optional_current_user] = lambda: _USER
    return TestClient(app)


def test_shared_system_task_results_visible_to_ordinary_user():
    task = _shared_task()
    record = _result()
    service = SimpleNamespace(
        get_task=lambda task_id: task if task_id == task.task_id else None,
        list_task_results=lambda **kwargs: ([record], 1),
    )

    with patch("app.api.scheduled_task_routes.get_scheduled_task_service", lambda: service):
        response = _client().get("/api/scheduled-tasks/results", params={"task_id": task.task_id})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_private_task_results_stay_hidden_from_other_users():
    private = _private_task()
    service = SimpleNamespace(
        get_task=lambda task_id: private if task_id == private.task_id else None,
    )

    with patch("app.api.scheduled_task_routes.get_scheduled_task_service", lambda: service):
        response = _client().get("/api/scheduled-tasks/results", params={"task_id": private.task_id})
    assert response.status_code == 404


def test_shared_system_task_facets_visible_to_ordinary_user():
    task = _shared_task()
    service = SimpleNamespace(
        get_task=lambda task_id: task if task_id == task.task_id else None,
        list_task_result_facets=lambda **kwargs: {"stations": [], "pollutants": []},
    )

    with patch("app.api.scheduled_task_routes.get_scheduled_task_service", lambda: service):
        response = _client().get("/api/scheduled-tasks/results/facets", params={"task_id": task.task_id})
    assert response.status_code == 200
