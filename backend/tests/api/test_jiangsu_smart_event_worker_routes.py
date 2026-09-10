from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth.internal_identity import encode_internal_user
from app.auth.models import CurrentUser
from app.lifecycle.social_worker_api import create_social_worker_api_app


def test_worker_smart_event_dispatch_requires_internal_identity(monkeypatch):
    class FakeService:
        async def run_ai_judgment(self, event_id, *, actor):
            raise AssertionError("must reject before dispatch")

    monkeypatch.setattr(
        "app.api.jiangsu_smart_event_worker_routes.JiangsuSmartEventService",
        FakeService,
    )
    client = TestClient(
        create_social_worker_api_app(SimpleNamespace(channel_manager=None), internal_token="secret")
    )

    response = client.post(
        "/internal/jiangsu/smart-events/alarm:1/ai-dispatch",
        headers={"x-social-worker-token": "secret"},
    )

    assert response.status_code == 401


def test_worker_smart_event_dispatch_runs_in_worker_process(monkeypatch):
    calls = []

    class FakeService:
        async def run_ai_judgment(self, event_id, *, actor):
            calls.append((event_id, actor))
            return {"event": {"event_id": event_id}, "task": {"task_id": "task:1"}, "dispatches": []}

    monkeypatch.setattr(
        "app.api.jiangsu_smart_event_worker_routes.JiangsuSmartEventService",
        FakeService,
    )
    client = TestClient(
        create_social_worker_api_app(SimpleNamespace(channel_manager=None), internal_token="secret")
    )
    user = CurrentUser(id="u1", username="alice", display_name="Alice")

    response = client.post(
        "/internal/jiangsu/smart-events/alarm:1/ai-dispatch",
        headers={
            "x-social-worker-token": "secret",
            "x-suyuan-current-user": encode_internal_user(user, secret="secret"),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    assert calls == [("alarm:1", {"user_id": "u1", "username": "alice"})]
