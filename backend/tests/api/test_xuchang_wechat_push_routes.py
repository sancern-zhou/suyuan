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


def test_media_endpoint_serves_registry_image(token_client, tmp_path, monkeypatch):
    from app.utils.path_config import resolve_agent_path

    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.resolve_agent_path",
        lambda p: tmp_path / p,
    )
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.get_data_registry",
        lambda: tmp_path,
    )
    client, registry = token_client
    media_rel = "xuchang_wechat_push_selftest/chart.png"
    image_file = tmp_path / media_rel
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"\x89PNG-fake-bytes")
    record = queue.enqueue_station_alert_wechat_message(
        {"station_id": "1", "station_name": "s", "alerts": []},
        "带图通报",
        media=[media_rel, "xuchang_wechat_push_selftest/missing.png"],
        root=registry,
    )

    ok = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/0", headers=_headers()
    )
    assert ok.status_code == 200
    assert ok.content == b"\x89PNG-fake-bytes"
    assert ok.headers["content-type"] == "image/png"

    # 越界 / 缺文件 / 消息不存在
    out_of_range = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/5", headers=_headers()
    )
    assert out_of_range.status_code == 404
    missing_file = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/1", headers=_headers()
    )
    assert missing_file.status_code == 404
    missing_msg = client.get(
        "/api/xuchang-wechat-push/media/wx-none/0", headers=_headers()
    )
    assert missing_msg.status_code == 404
    negative = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/-1", headers=_headers()
    )
    assert negative.status_code == 400


def test_media_endpoint_serves_archived_message(token_client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.resolve_agent_path",
        lambda p: tmp_path / p,
    )
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.get_data_registry",
        lambda: tmp_path,
    )
    client, registry = token_client
    media_rel = "xuchang_wechat_push_selftest/chart.png"
    image_file = tmp_path / media_rel
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"\x89PNG-archived")
    record = queue.enqueue_station_alert_wechat_message(
        {"alerts": []}, "正文", media=[media_rel], root=registry
    )
    client.post(
        "/api/xuchang-wechat-push/ack",
        json={"id": record["id"], "status": "sent"},
        headers=_headers(),
    )

    ok = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/0", headers=_headers()
    )
    assert ok.status_code == 200
    assert ok.content == b"\x89PNG-archived"


def test_media_outside_registry_is_404(token_client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.resolve_agent_path",
        lambda p: tmp_path / p,
    )
    client, registry = token_client
    outside = tmp_path / "outside_secret.png"
    outside.write_bytes(b"secret")
    record = queue.enqueue_station_alert_wechat_message(
        {"alerts": []}, "正文", media=["outside_secret.png"], root=registry
    )

    response = client.get(
        f"/api/xuchang-wechat-push/media/{record['id']}/0", headers=_headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "media_outside_registry"


def test_media_requires_token(token_client, tmp_path):
    client, registry = token_client
    assert client.get(
        "/api/xuchang-wechat-push/media/wx-1/0"
    ).status_code == 401


def test_queue_extract_skips_blank_message(tmp_path):
    assert (
        queue.enqueue_station_alert_wechat_message({"alerts": []}, "  ", root=tmp_path)
        is None
    )


def _patch_attachment_paths(monkeypatch, tmp_path, registry_root=None):
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.resolve_agent_path",
        lambda p: tmp_path / p,
    )
    monkeypatch.setattr(
        "app.api.xuchang_wechat_push_routes.get_data_registry",
        lambda: registry_root or tmp_path,
    )


def test_attachment_endpoint_serves_report_docx(token_client, tmp_path, monkeypatch):
    _patch_attachment_paths(monkeypatch, tmp_path)
    client, registry = token_client
    docx_rel = "reports/pollution/report.docx"
    docx_file = tmp_path / docx_rel
    docx_file.parent.mkdir(parents=True, exist_ok=True)
    docx_file.write_bytes(b"fake-docx-bytes")
    record = queue.enqueue_wechat_message(
        "pollution_cause",
        "【污染原因分析】正文",
        attachments=[{
            "path": docx_rel,
            "filename": "污染原因分析通报_20261120.docx",
            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }],
        root=registry,
    )
    assert record is not None

    ok = client.get(
        f"/api/xuchang-wechat-push/attachment/{record['id']}/0", headers=_headers()
    )
    assert ok.status_code == 200
    assert ok.content == b"fake-docx-bytes"
    assert ok.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "filename" in ok.headers.get("content-disposition", "")

    out_of_range = client.get(
        f"/api/xuchang-wechat-push/attachment/{record['id']}/5", headers=_headers()
    )
    assert out_of_range.status_code == 404
    assert out_of_range.json()["detail"] == "attachment_index_out_of_range"
    negative = client.get(
        f"/api/xuchang-wechat-push/attachment/{record['id']}/-1", headers=_headers()
    )
    assert negative.status_code == 400
    missing_msg = client.get(
        "/api/xuchang-wechat-push/attachment/wx-none/0", headers=_headers()
    )
    assert missing_msg.status_code == 404


def test_attachment_rejects_unsupported_and_outside_registry(
    token_client, tmp_path, monkeypatch
):
    client, registry = token_client
    exe_rel = "reports/pollution/tool.exe"
    exe_file = tmp_path / exe_rel
    exe_file.parent.mkdir(parents=True, exist_ok=True)
    exe_file.write_bytes(b"binary")
    unsupported = queue.enqueue_wechat_message(
        "pollution_cause",
        "【污染原因分析】正文",
        attachments=[{"path": exe_rel, "filename": "tool.exe"}],
        root=registry,
    )
    assert unsupported is not None
    _patch_attachment_paths(monkeypatch, tmp_path)

    rejected = client.get(
        f"/api/xuchang-wechat-push/attachment/{unsupported['id']}/0",
        headers=_headers(),
    )
    assert rejected.status_code == 404
    assert rejected.json()["detail"] == "unsupported_attachment_type"

    outside_rel = "outside_secret.docx"
    (tmp_path / outside_rel).write_bytes(b"secret")
    outside = queue.enqueue_wechat_message(
        "pollution_cause",
        "【污染原因分析】正文",
        attachments=[{"path": outside_rel, "filename": outside_rel}],
        root=registry,
    )
    assert outside is not None
    _patch_attachment_paths(monkeypatch, tmp_path, registry_root=tmp_path / "registry")

    response = client.get(
        f"/api/xuchang-wechat-push/attachment/{outside['id']}/0", headers=_headers()
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "attachment_outside_registry"


def test_pending_caps_hold_attachments_for_legacy_agent(token_client):
    client, registry = token_client
    queue.enqueue_wechat_message(
        "pollution_cause",
        "【污染原因分析】带附件",
        attachments=[{"path": "backend/backend_data_registry/reports/r/report.docx"}],
        root=registry,
    )

    legacy = client.get("/api/xuchang-wechat-push/pending", headers=_headers())
    assert legacy.status_code == 200
    assert legacy.json()["count"] == 0
    assert queue.list_pending_messages(root=registry)

    capable = client.get(
        "/api/xuchang-wechat-push/pending?caps=attachments", headers=_headers()
    )
    assert capable.status_code == 200
    assert capable.json()["count"] == 1
    assert capable.json()["messages"][0]["attachments"][0]["path"].endswith(".docx")
