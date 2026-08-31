import json

import pytest
import httpx
from fastapi import FastAPI

from app.social import app_identity
from app.api.social_app_routes import router as app_router
from app.api import social_app_routes
from app.auth.middleware import GatewayAuthenticationMiddleware
from config.settings import Settings
from app.social.broadcast_context import resolve_broadcast_media_path


def configure_accounts(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")
    monkeypatch.setattr(
        app_identity.settings,
        "app_accounts_json",
        json.dumps(
            {
                "alice": {"secret": "alice-secret", "name": "Alice"},
                "bob": {"secret": "bob-secret", "name": "Bob"},
            }
        ),
    )
    monkeypatch.setattr(app_identity.settings, "app_access_token_ttl_seconds", 3600)


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=Settings(),
        auth_service=None,
    )
    app.include_router(app_router)
    return app


def test_report_package_source_path_resolves_to_rendered_docx(tmp_path):
    report_dir = tmp_path / "report-package"
    report_dir.mkdir()
    qmd = report_dir / "report.qmd"
    docx = report_dir / "report.docx"
    qmd.write_text("# source", encoding="utf-8")
    docx.write_bytes(b"docx")

    assert resolve_broadcast_media_path(qmd) == docx


def test_report_package_source_path_falls_back_to_pdf(tmp_path):
    report_dir = tmp_path / "report-package"
    report_dir.mkdir()
    qmd = report_dir / "report.qmd"
    pdf = report_dir / "report.pdf"
    qmd.write_text("# source", encoding="utf-8")
    pdf.write_bytes(b"%PDF")

    assert resolve_broadcast_media_path(qmd) == pdf


BROADCAST_MESSAGE = {
    "id": "broadcast:daily:evt-1:app:android:alice",
    "type": "broadcast",
    "role": "assistant",
    "content": "报表已生成",
    "timestamp": "2026-08-30T17:00:00+08:00",
    "read": False,
    "data": {
        "attachments": [
            {
                "name": "统计报表.xlsx",
                "path": "/registry/reports/统计报表.xlsx",
                "type": "file",
            },
            {
                "name": "外链.png",
                "url": "https://example.com/chart.png",
            },
        ],
        "read": False,
    },
}


async def _inbox_for(social_user_id):
    if social_user_id == "app:android:alice":
        return [dict(BROADCAST_MESSAGE)]
    return []


@pytest.mark.asyncio
async def test_broadcast_payload_hides_paths_and_links_content_endpoint():
    payload = social_app_routes._broadcast_payload(BROADCAST_MESSAGE)
    assert "/registry/reports" not in json.dumps(payload)
    local_attachment = payload["attachments"][0]
    expected_url = (
        "/api/social/app/broadcasts/broadcast:daily:evt-1:app:android:alice"
        "/attachments/0/content"
    )
    assert local_attachment["url"] == expected_url
    assert local_attachment["download_url"] == expected_url
    assert local_attachment["mime_type"].endswith(
        "spreadsheetml.sheet"
    )
    assert local_attachment["preview_url"] == (
        "/api/social/app/broadcasts/broadcast:daily:evt-1:app:android:alice"
        "/attachments/0/preview"
    )
    assert local_attachment["preview_mime_type"] == "application/pdf"
    remote_attachment = payload["attachments"][1]
    assert remote_attachment["url"] == "https://example.com/chart.png"
    assert "download_url" not in remote_attachment
    assert "preview_url" not in remote_attachment


@pytest.mark.asyncio
async def test_broadcast_attachment_content_streaming(tmp_path, monkeypatch):
    configure_accounts(monkeypatch)
    registry_root = tmp_path / "registry"
    reports_dir = registry_root / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "统计报表.xlsx").write_bytes(b"xlsx-bytes")

    original_message = dict(BROADCAST_MESSAGE)
    original_message["data"] = {
        "attachments": [
            {
                "name": "统计报表.xlsx",
                "path": str(reports_dir / "统计报表.xlsx"),
                "type": "file",
            },
            {"name": "越权文件.txt", "path": str(tmp_path / "outside.txt"), "type": "file"},
            {"name": "普通文本.txt", "path": str(reports_dir / "notes.txt"), "type": "file"},
        ],
        "read": False,
    }
    (tmp_path / "outside.txt").write_text("forbidden")
    (reports_dir / "notes.txt").write_text("notes")
    # 预置 LibreOffice 管线约定位置的缓存 PDF，避免测试依赖 soffice
    (reports_dir / "统计报表.preview.pdf").write_bytes(b"%PDF-1.5 cached-preview")

    async def fake_inbox(social_user_id):
        return [dict(original_message)] if social_user_id == "app:android:alice" else []

    from app.social import broadcast_context

    monkeypatch.setattr(broadcast_context, "load_broadcast_messages", fake_inbox)
    monkeypatch.setattr(social_app_routes, "get_data_registry", lambda: registry_root)

    app = build_app()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/social/app/auth/login",
            json={"account_id": "alice", "account_secret": "alice-secret"},
        )
        alice_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        bob_login = await client.post(
            "/api/social/app/auth/login",
            json={"account_id": "bob", "account_secret": "bob-secret"},
        )
        bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}"}

        inbox = await client.get("/api/social/app/broadcasts", headers=alice_headers)
        assert inbox.status_code == 200
        body = inbox.json()
        attachment = body["messages"][0]["attachments"][0]
        assert attachment["url"].startswith("/api/social/app/broadcasts/")
        assert attachment["preview_url"].endswith("/attachments/0/preview")
        assert attachment["preview_mime_type"] == "application/pdf"

        base = "/api/social/app/broadcasts/broadcast:daily:evt-1:app:android:alice/attachments"

        content = await client.get(f"{base}/0/content", headers=alice_headers)
        assert content.status_code == 200
        assert content.content == b"xlsx-bytes"

        preview = await client.get(f"{base}/0/preview", headers=alice_headers)
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("application/pdf")
        assert preview.content == b"%PDF-1.5 cached-preview"

        txt_preview = await client.get(f"{base}/2/preview", headers=alice_headers)
        assert txt_preview.status_code == 404

        forbidden = await client.get(f"{base}/1/content", headers=alice_headers)
        assert forbidden.status_code == 403

        missing_index = await client.get(f"{base}/9/content", headers=alice_headers)
        assert missing_index.status_code == 404

        other_user = await client.get(f"{base}/0/content", headers=bob_headers)
        assert other_user.status_code == 404

        no_auth = await client.get(f"{base}/0/content")
        assert no_auth.status_code == 401
