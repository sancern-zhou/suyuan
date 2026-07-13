from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.social_broadcast_worker_routes import (
    set_targeted_broadcast_service_override,
)
from app.lifecycle.social_worker_api import create_social_worker_api_app


class FakeTargetedBroadcastService:
    def __init__(self):
        self.calls = []

    async def broadcast(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "success",
            "success": True,
            "channels_sent": ["weixin:auto:bot:user"],
            "failed_user_names": [],
            "delivery_results": [{
                "user_name": "周三成",
                "user_id": "admin-1",
                "social_user_id": "weixin:auto:bot:user",
                "sent": True,
                "context_persisted": True,
                "error": None,
            }],
            "media_sent": 1,
            "summary": "已广播给 1 个目标用户",
        }


def _client(service):
    set_targeted_broadcast_service_override(service)
    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    return TestClient(app)


def test_worker_broadcast_route_requires_internal_token():
    service = FakeTargetedBroadcastService()
    client = _client(service)
    try:
        response = client.post(
            "/internal/social/broadcast",
            json={"message": "运城告警", "target_user_names": ["周三成"]},
        )
    finally:
        set_targeted_broadcast_service_override(None)

    assert response.status_code == 403
    assert service.calls == []


def test_worker_broadcast_route_fails_closed_when_token_is_not_configured():
    service = FakeTargetedBroadcastService()
    set_targeted_broadcast_service_override(service)
    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="",
    )
    try:
        response = TestClient(app).post(
            "/internal/social/broadcast",
            json={"message": "运城告警", "target_user_names": ["周三成"]},
        )
    finally:
        set_targeted_broadcast_service_override(None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Social worker token is not configured"
    assert service.calls == []


def test_worker_broadcast_route_validates_required_target_names():
    service = FakeTargetedBroadcastService()
    client = _client(service)
    try:
        response = client.post(
            "/internal/social/broadcast",
            headers={"x-social-worker-token": "secret"},
            json={"message": "运城告警", "target_user_names": []},
        )
    finally:
        set_targeted_broadcast_service_override(None)

    assert response.status_code == 422
    assert service.calls == []


def test_worker_broadcast_route_forwards_names_media_and_metadata():
    service = FakeTargetedBroadcastService()
    client = _client(service)
    payload = {
        "message": "运城告警",
        "target_user_names": ["周三成"],
        "media": ["/tmp/report.docx"],
        "context_metadata": {
            "source": "assistant_tool",
            "tool_name": "broadcast_social_users",
        },
    }
    try:
        response = client.post(
            "/internal/social/broadcast",
            headers={"x-social-worker-token": "secret"},
            json=payload,
        )
    finally:
        set_targeted_broadcast_service_override(None)

    assert response.status_code == 200
    assert response.json()["delivery_results"][0]["user_name"] == "周三成"
    assert service.calls == [payload]
