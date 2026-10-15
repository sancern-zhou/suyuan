"""App 远程更新公开端点：版本元数据与 APK 下载。"""

import json

import httpx
import pytest
from fastapi import FastAPI

from app.api import social_app_routes as routes


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "get_data_registry", lambda: tmp_path)
    app = FastAPI()
    app.include_router(routes.router)
    return app, tmp_path


@pytest.mark.asyncio
async def test_latest_version_reads_registry_json(app_client):
    app, registry = app_client
    payload = {
        "versionCode": 2,
        "versionName": "1.0.1",
        "downloadUrl": "/api/social/app/apk/suyuan-1.0.1-2.apk",
        "sha256": "ab" * 32,
        "releaseNotes": "修复若干问题",
        "minVersionCode": 1,
    }
    (registry / "social").mkdir(parents=True)
    (registry / "social" / "app_version.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/social/app/version/latest")
    assert response.status_code == 200
    assert response.json() == payload


@pytest.mark.asyncio
async def test_latest_version_missing_or_invalid_is_404(app_client):
    app, registry = app_client
    (registry / "social").mkdir(parents=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/social/app/version/latest")
        (registry / "social" / "app_version.json").write_text("not-json", encoding="utf-8")
        invalid = await client.get("/api/social/app/version/latest")
    assert missing.status_code == 404
    assert invalid.status_code == 404


@pytest.mark.asyncio
async def test_apk_download_serves_registry_file_and_rejects_bad_names(app_client):
    app, registry = app_client
    apk_dir = registry / "social" / "apk"
    apk_dir.mkdir(parents=True)
    (apk_dir / "suyuan-1.0.1-2.apk").write_bytes(b"PK\x03\x04fake")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.get("/api/social/app/apk/suyuan-1.0.1-2.apk")
        missing = await client.get("/api/social/app/apk/suyuan-9.9.9-99.apk")
        not_apk = await client.get("/api/social/app/apk/notes.txt")
        traversal = await client.get("/api/social/app/apk/..%2Fapp_version.json")

    assert ok.status_code == 200
    assert ok.content == b"PK\x03\x04fake"
    assert ok.headers["content-type"].startswith("application/vnd.android.package-archive")
    assert missing.status_code == 404
    assert not_apk.status_code == 404
    assert traversal.status_code == 404
