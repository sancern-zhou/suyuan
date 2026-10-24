"""大屏快照 API：文件读、ETag 304、快照缺失 503。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.xuchang_dashboard_routes import router
from app.auth.dependencies import require_current_user
from app.fetchers.xuchang_screen_snapshot import SNAPSHOT_DIR, SNAPSHOT_FILE


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.xuchang_dashboard_routes.get_data_registry",
        lambda: tmp_path,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: object()
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
