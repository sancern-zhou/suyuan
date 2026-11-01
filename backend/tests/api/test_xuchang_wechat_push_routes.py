"""微信群 RPA 推送队列 API：token 鉴权、取发回执全链路、积压状态。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.xuchang_wechat_push_routes import router
from app.auth.dependencies import optional_current_user
from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue
from config.settings import settings as app_settings

QUEUE_REGISTRY_PATCH = (
    "app.scenarios.xuchang_station_deviation.wechat_push_queue.get_data_registry"
)


@pytest.fixture
def token_client(tmp_path, monkeypatch):
    """带部署级机器令牌的客户端（模拟本机推送 agent 免登录直连）。"""
    monkeypatch.setattr(QUEUE_REGISTRY_PATCH, lambda: tmp_path)
    monkeypatch.setattr(app_settings, "xuchang_wechat_push_token", "agent-token-1")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), tmp_path


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(QUEUE_REGISTRY_PATCH, lambda: tmp_path)
    monkeypatch.setattr(app_settings, "xuchang_wechat_push_token", "")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(
        is_admin=True
    )
    return TestClient(app)


def _headers(token="agent-token-1"):
    return {"Authorization": f"Bearer {token}"}


def _enqueue(registry, text="一、告警概况\n许昌市一中 PM2.5 偏高。"):
    return queue.enqueue_station_alert_wechat_message(
        {
            "station_id": "1005A",
            "station_name": "市一中",
            "alerts": [
                {
                    "alert": {
                        "target_pollutant": "PM2.5",
                        "scenario_1_episode": {"episode_id": "ep-20261102"},
                    }
                }
            ],
        },
        text,
        root=registry,
    )


def test_pending_disabled_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(QUEUE_REGISTRY_PATCH, lambda: tmp_path)
    monkeypatch.setattr(app_settings, "xuchang_wechat_push_token", "")
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/api/xuchang-wechat-push/pending")
    assert response.status_code == 403
    assert response.json()["detail"] == "wechat_push_disabled"


def test_pending_rejects_missing_and_wrong_token(token_client):
    client, _ = token_client
    assert client.get("/api/xuchang-wechat-push/pending").status_code == 401
    wrong = client.get(
        "/api/xuchang-wechat-push/pending", headers=_headers("wrong-token")
    )
    assert wrong.status_code == 401


def test_pending_empty_writes_agent_heartbeat(token_client):
    client, registry = token_client

    response = client.get(
        "/api/xuchang-wechat-push/pending?agent_id=dev-pc", headers=_headers()
    )

    assert response.status_code == 200
    assert response.json() == {"messages": [], "count": 0}
    status = queue.push_status_snapshot(root=registry)
    assert status["agent"]["agent"]["agent_id"] == "dev-pc"
    assert status["agent"]["last_seen_at"]


def test_full_flow_enqueue_fetch_ack_sent(token_client):
    client, registry = token_client
    record = _enqueue(registry)

    fetched = client.get("/api/xuchang-wechat-push/pending", headers=_headers())
    assert fetched.status_code == 200
    messages = fetched.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["id"] == record["id"]
    assert "告警概况" in messages[0]["text"]
    assert messages[0]["metadata"]["episode_id"] == "ep-20261102"
    assert messages[0]["metadata"]["station_name"] == "市一中"
    assert messages[0]["metadata"]["pollutants"] == "PM2.5"
    assert messages[0]["attempts"] == 0

    acked = client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": record["id"], "status": "sent", "agent_id": "dev-pc"},
        headers=_headers(),
    )
    assert acked.status_code == 200
    assert acked.json()["result"] == "archived_sent"

    assert client.get(
        "/api/xuchang-wechat-push/pending", headers=_headers()
    ).json()["count"] == 0
    # 重复 ack 幂等
    repeat = client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": record["id"], "status": "sent"},
        headers=_headers(),
    )
    assert repeat.json()["result"] == "unknown"


def test_ack_failed_requeues_then_archives(token_client):
    client, registry = token_client
    record = _enqueue(registry)

    for expected_attempts in (1, 2):
        result = client.post(
            "/api/xuchang-wechat-push/ack",
            json={"id": record["id"], "status": "failed", "detail": "微信窗口未找到"},
            headers=_headers(),
        ).json()["result"]
        assert result == "requeued"
        pending = queue.list_pending_messages(root=registry)
        assert len(pending) == 1
        assert pending[0]["attempts"] == expected_attempts
        assert "微信窗口" in pending[0]["last_error"]

    third = client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": record["id"], "status": "failed"},
        headers=_headers(),
    ).json()["result"]
    assert third == "archived_failed"
    assert queue.list_pending_messages(root=registry) == []
    assert queue.push_status_snapshot(root=registry)["failed_count"] == 1


def test_ack_rejects_bad_status_and_unsafe_id(token_client):
    client, registry = token_client
    record = _enqueue(registry)

    bad_status = client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": record["id"], "status": "maybe"},
        headers=_headers(),
    )
    assert bad_status.status_code == 400

    traversal = client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": "../escape", "status": "sent"},
        headers=_headers(),
    )
    assert traversal.status_code == 400
    assert queue.list_pending_messages(root=registry)[0]["id"] == record["id"]


def test_admin_reads_status_without_token(admin_client, tmp_path):
    _enqueue(tmp_path)

    response = admin_client.get("/api/xuchang-wechat-push/status")

    assert response.status_code == 200
    body = response.json()
    assert body["pending_count"] == 1
    assert body["sent_count"] == 0
    assert body["failed_count"] == 0
    assert body["oldest_pending_created_at"]


def test_non_admin_login_is_forbidden(tmp_path, monkeypatch):
    monkeypatch.setattr(QUEUE_REGISTRY_PATCH, lambda: tmp_path)
    monkeypatch.setattr(app_settings, "xuchang_wechat_push_token", "agent-token-1")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(
        is_admin=False
    )

    response = TestClient(app).get("/api/xuchang-wechat-push/status")
    assert response.status_code == 403
    assert response.json()["detail"] == "wechat_push_admin_only"


def test_queue_extract_skips_blank_message(tmp_path):
    assert (
        queue.enqueue_station_alert_wechat_message({"alerts": []}, "  ", root=tmp_path)
        is None
    )
