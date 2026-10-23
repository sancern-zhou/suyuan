"""App 报告成果附件接口：URL 尾段唯一化 + 缓存头 + 尾段不参与解析。"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.social import app_identity
from app.social import report_service
from app.api.social_app_routes import router as app_router
from app.api import social_app_routes
from app.api.upload_routes import _office_pdf_preview_path
from app.auth.middleware import GatewayAuthenticationMiddleware
from config.settings import Settings


def configure_accounts(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")
    monkeypatch.setattr(
        app_identity.settings,
        "app_accounts_json",
        json.dumps({"alice": {"secret": "alice-secret", "name": "Alice"}}),
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


def _row(report_id: str, attachments: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        report_id=report_id,
        task_id="task-demo",
        execution_id="exec-demo",
        task_name="演示任务",
        report_type="scheduled_report",
        title="演示报告",
        summary="",
        status="success",
        generated_at=datetime(2026, 10, 9, 12, 0, 0),
        read=False,
        read_at=None,
        attachments=attachments,
        metadata_json={},
    )


def test_report_payload_urls_end_with_unique_segment_per_report():
    attachment = {"filename": "report.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    payloads = [
        social_app_routes._report_payload(_row(report_id, [attachment]))
        for report_id in ("report-aaa", "report-bbb")
    ]
    urls = [item["attachments"][0]["url"] for item in payloads]
    previews = [item["attachments"][0]["preview_url"] for item in payloads]
    # URL 最后一段必须是唯一文件名：App 端缓存若按末段做 key，
    # 以 /preview 结尾会让所有报告都显示同一份 PDF。
    assert all(url.rsplit("/", 1)[-1] not in {"content", "preview", "0"} for url in urls)
    assert len({url.rsplit("/", 1)[-1] for url in urls}) == 2
    assert len({preview.rsplit("/", 1)[-1] for preview in previews}) == 2
    for item in payloads:
        attachment_payload = item["attachments"][0]
        assert attachment_payload["preview_mime_type"] == "application/pdf"
        assert attachment_payload["download_url"].startswith(attachment_payload["url"])


def test_report_payload_identity_is_stable_and_covers_index():
    attachment = {"filename": "report.docx", "mime_type": "application/msword"}
    row = _row("report-aaa", [attachment, dict(attachment)])
    payload = social_app_routes._report_payload(row)
    identity = hashlib.sha256(b"report-aaa").hexdigest()[:16]
    assert payload["attachments"][0]["file_id"] == "report-report-aaa-0"
    assert f"{identity}-0-" in payload["attachments"][0]["url"]
    assert f"{identity}-1-" in payload["attachments"][1]["url"]
    assert payload == social_app_routes._report_payload(_row("report-aaa", [attachment, dict(attachment)]))


@pytest.mark.asyncio
async def test_report_attachment_content_and_preview_routes(tmp_path, monkeypatch):
    configure_accounts(monkeypatch)
    registry_root = tmp_path / "registry"
    reports_dir = registry_root / "reports" / "exec-demo-report"
    reports_dir.mkdir(parents=True)
    docx = reports_dir / "report.docx"
    docx.write_bytes(b"docx-bytes")
    # 预置按指纹命名的缓存 PDF，避免测试依赖 soffice
    cached_preview = _office_pdf_preview_path(docx)
    cached_preview.write_bytes(b"%PDF-1.5 cached-preview")

    report_id = "report:demo"
    row = _row(
        report_id,
        [{
            "filename": "report.docx",
            "path": str(docx),
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }],
    )

    async def fake_get_report(owner_user_id, rid):
        return row if rid == report_id else None

    monkeypatch.setattr(report_service, "get_report", fake_get_report)
    monkeypatch.setattr(social_app_routes, "get_data_registry", lambda: registry_root)

    app = build_app()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/social/app/auth/login",
            json={"account_id": "alice", "account_secret": "alice-secret"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        payload = social_app_routes._report_payload(row)
        attachment = payload["attachments"][0]
        assert attachment["preview_url"].endswith(".pdf")
        tail = attachment["preview_url"].rsplit("/", 1)[-1]
        assert tail not in {"preview", "report.pdf"}

        content = await client.get(attachment["url"], headers=headers)
        assert content.status_code == 200
        assert content.content == b"docx-bytes"
        assert content.headers["cache-control"] == "private, max-age=31536000, immutable"

        # 文件名尾巴不参与解析：任意名字都按 report_id + index 解析。
        renamed = await client.get(
            attachment["url"].rsplit("/", 1)[0] + "/whatever.bin", headers=headers
        )
        assert renamed.status_code == 200
        assert renamed.content == b"docx-bytes"

        # 旧路由（无尾段）保持可用，兼容已安装的 App。
        legacy = await client.get(
            f"/api/social/app/report-results/report%3Ademo/attachments/0",
            headers=headers,
        )
        assert legacy.status_code == 200
        assert legacy.content == b"docx-bytes"

        preview = await client.get(attachment["preview_url"], headers=headers)
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("application/pdf")
        assert preview.content == b"%PDF-1.5 cached-preview"
        assert preview.headers["cache-control"] == "private, max-age=86400"

        legacy_preview = await client.get(
            f"/api/social/app/report-results/report%3Ademo/attachments/0/preview",
            headers=headers,
        )
        assert legacy_preview.status_code == 200
        assert legacy_preview.content == b"%PDF-1.5 cached-preview"

        missing = await client.get(
            attachment["preview_url"].replace("report%3Ademo", "report%3Aother"),
            headers=headers,
        )
        assert missing.status_code == 404

        no_auth = await client.get(attachment["url"])
        assert no_auth.status_code == 401
