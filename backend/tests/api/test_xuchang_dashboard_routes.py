"""大屏快照 API：文件读、ETag 304、快照缺失 503。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.xuchang_dashboard_routes import router
from app.auth.dependencies import optional_current_user, require_current_user
from app.fetchers.xuchang_screen_snapshot import SNAPSHOT_DIR, SNAPSHOT_FILE
from config.settings import settings as app_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    app = FastAPI()
    app.include_router(router)
    # 大屏页面开发阶段仅超级管理员可见：require_dashboard_reader 校验 is_admin
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(is_admin=True)
    return TestClient(app)


@pytest.fixture
def token_client(tmp_path, monkeypatch):
    """带部署级大屏令牌的客户端（模拟大屏设备免登录直连）。"""
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    monkeypatch.setattr(app_settings, "dashboard_access_token", "screen-token-123")
    app = FastAPI()
    app.include_router(router)
    # 不注入 current_user，模拟无网关会话的大屏设备
    return TestClient(app)


def _write_snapshot(registry, payload):
    directory = registry / SNAPSHOT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SNAPSHOT_FILE).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_returns_503_before_first_snapshot(client, tmp_path):
    response = client.get("/api/xuchang-dashboard/screen-snapshot")

    assert response.status_code == 503
    assert "尚未生成" in response.json()["detail"]


def test_serves_snapshot_and_304_on_unchanged(client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    first = client.get("/api/xuchang-dashboard/screen-snapshot")
    assert first.status_code == 200
    assert first.json()["header"]["aqi"] == 82
    etag = first.headers["ETag"]

    unchanged = client.get(
        "/api/xuchang-dashboard/screen-snapshot", headers={"If-None-Match": etag}
    )
    assert unchanged.status_code == 304

    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 71}})
    changed = client.get(
        "/api/xuchang-dashboard/screen-snapshot", headers={"If-None-Match": etag}
    )
    assert changed.status_code == 200
    assert changed.json()["header"]["aqi"] == 71


def test_hot_alerts_merge_overrides_snapshot_alerts(client, tmp_path):
    _write_snapshot(tmp_path, {
        "schema_version": 1,
        "alerts": [{
            "episode_id": "ep-1", "station_name": "许昌学院", "status": "active",
            "lon": 113.8611, "lat": 34.0443,
        }],
    })
    directory = tmp_path / "xuchang_station_deviation_alerts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "episode_state.json").write_text(json.dumps({
        "active": [{
            "episode_id": "ep-1", "station_id": "1008A", "station_name": "许昌学院",
            "status": "closed", "started_at": "2026-10-24T10:00:00",
            "last_seen_at": "2026-10-24T15:30:00",
        }, {
            "episode_id": "ep-new", "station_id": "1005A", "station_name": "市一中",
            "status": "active", "started_at": "2026-10-24T15:40:00",
            "last_seen_at": "2026-10-24T15:45:00",
        }],
        "history": [],
    }), encoding="utf-8")

    response = client.get("/api/xuchang-dashboard/screen-snapshot")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # 状态机以 episode_state 为准，ep-1 变 closed，且新增 ep-new
    statuses = {item["episode_id"]: item["status"] for item in alerts}
    assert statuses == {"ep-1": "closed", "ep-new": "active"}
    # 快照里已有的坐标在热合并时保留
    coords = {item["episode_id"]: item["lon"] for item in alerts}
    assert coords["ep-1"] == 113.8611
    assert coords["ep-new"] is None
    # 热合并行带 hot 标记
    assert all(item["hot"] for item in alerts)


def test_hot_alerts_can_be_disabled(client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "alerts": [{"episode_id": "ep-x"}]})

    response = client.get(
        "/api/xuchang-dashboard/screen-snapshot?hot_alerts=false"
    )
    assert response.json()["alerts"] == [{"episode_id": "ep-x"}]


def test_asset_route_rejects_traversal_and_non_images(client, tmp_path):
    # 目录穿越
    response = client.get("/api/xuchang-dashboard/asset", params={"path": "../secret.png"})
    assert response.status_code == 400
    # 绝对路径
    response = client.get("/api/xuchang-dashboard/asset", params={"path": "/etc/passwd"})
    assert response.status_code == 400
    # 非白名单扩展名
    response = client.get(
        "/api/xuchang-dashboard/asset", params={"path": "xuchang_transport_analysis/20261024/job.json"}
    )
    assert response.status_code == 400


def test_asset_route_serves_registry_image(client, tmp_path):
    import os

    asset = tmp_path / "xuchang_transport_analysis" / "20261024"
    asset.mkdir(parents=True, exist_ok=True)
    png = asset / "job-a.regional-paths.png"
    png.write_bytes(b"\x89PNG-fake-bytes")
    os.utime(png, None)

    response = client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_asset_route_404_for_missing_file(client, tmp_path):
    response = client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/none.png"},
    )
    assert response.status_code == 404


def test_token_client_without_token_is_401(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    response = token_client.get("/api/xuchang-dashboard/screen-snapshot")
    assert response.status_code == 401


def test_token_client_with_valid_token_reads_snapshot(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1, "header": {"aqi": 82}})

    response = token_client.get(
        "/api/xuchang-dashboard/screen-snapshot?access_token=screen-token-123"
    )
    assert response.status_code == 200
    assert response.json()["header"]["aqi"] == 82


def test_token_client_with_wrong_token_is_401(token_client, tmp_path):
    _write_snapshot(tmp_path, {"schema_version": 1})

    response = token_client.get(
        "/api/xuchang-dashboard/screen-snapshot?access_token=wrong"
    )
    assert response.status_code == 401


def test_token_grants_asset_route_too(token_client, tmp_path):
    import os

    asset = tmp_path / "xuchang_transport_analysis" / "20261024"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "job-a.regional-paths.png").write_bytes(b"\x89PNG-fake-bytes")

    ok = token_client.get(
        "/api/xuchang-dashboard/asset",
        params={
            "path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png",
            "access_token": "screen-token-123",
        },
    )
    assert ok.status_code == 200
    denied = token_client.get(
        "/api/xuchang-dashboard/asset",
        params={"path": "xuchang_transport_analysis/20261024/job-a.regional-paths.png"},
    )
    assert denied.status_code == 401
