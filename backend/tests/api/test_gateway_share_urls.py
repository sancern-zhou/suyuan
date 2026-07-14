import time

import httpx
import pytest
from fastapi import FastAPI

from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.share_access import ShareAccessService, external_api_path
from config.settings import Settings


class RejectingAuth:
    async def authenticate(self, token, sys_code):
        raise AssertionError("share assets must not call company authentication")


def _settings():
    return Settings(
        _env_file=None,
        auth_mode="company",
        auth_sys_code="SUYUAN",
        trusted_gateway_networks="127.0.0.1/32",
    )


def test_external_api_path_replaces_exactly_one_api_prefix():
    assert external_api_path("/api/reports/r1/html", "/api/suyuan") == "/api/suyuan/reports/r1/html"
    assert external_api_path("/health", "/api/suyuan") == "/health"
    assert external_api_path("/apiary/file", "/api/suyuan") == "/apiary/file"


def test_share_grant_is_resource_scoped_tamper_evident_and_expiring():
    now = int(time.time())
    service = ShareAccessService("secret", ttl_seconds=60)
    grant = service.issue("report", "report-1", now=now)

    assert service.verify(grant, "report", "report-1", now=now + 10)
    assert not service.verify(grant, "report", "report-2", now=now + 10)
    assert not service.verify(grant, "html-artifact", "report-1", now=now + 10)
    assert not service.verify(f"{grant}x", "report", "report-1", now=now + 10)
    assert not service.verify(grant, "report", "report-1", now=now + 61)


@pytest.mark.asyncio
async def test_grant_permits_only_bound_asset_subtree_and_bad_grants_are_403():
    grants = ShareAccessService("secret", ttl_seconds=60)
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(),
        auth_service=RejectingAuth(),
        share_access=grants,
    )

    @app.get("/api/reports/{report_id}/assets/{path:path}")
    async def report_asset(report_id: str, path: str):
        return {"report_id": report_id, "path": path}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    grant = grants.issue("report", "report-1")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.get(
            "/api/reports/report-1/assets/chart.png",
            cookies={"suyuan-share-grant": grant},
        )
        cross_resource = await client.get(
            "/api/reports/report-2/assets/chart.png",
            cookies={"suyuan-share-grant": grant},
        )
        altered = await client.get(
            "/api/reports/report-1/assets/chart.png",
            cookies={"suyuan-share-grant": f"{grant}x"},
        )

    assert allowed.status_code == 200
    assert cross_resource.status_code == 403
    assert altered.status_code == 403


def test_signed_media_uses_gateway_prefix(tmp_path):
    from app.services.signed_media import SignedMediaService

    media = tmp_path / "image.png"
    media.write_bytes(b"image")
    service = SignedMediaService(
        [tmp_path],
        "secret",
        "https://platform.example",
        gateway_api_prefix="/api/suyuan",
    )

    url = service.create_url(media)

    assert url.startswith("https://platform.example/api/suyuan/signed-media/image.png?")


@pytest.mark.asyncio
async def test_html_share_sets_scoped_httponly_grant_and_gateway_base(tmp_path, monkeypatch):
    from app.api import html_artifact_routes

    artifact_dir = tmp_path / "artifact-1"
    artifact_dir.mkdir()
    index = artifact_dir / "index.html"
    index.write_text("<html><head></head><body>artifact</body></html>", encoding="utf-8")
    monkeypatch.setattr(
        html_artifact_routes.html_artifact_service,
        "find_by_share_token",
        lambda token: index,
    )

    response = await html_artifact_routes.get_shared_html_artifact("share-token")

    assert '<base href="/api/suyuan/html-artifacts/artifact-1/">' in response.body.decode()
    cookie = response.headers["set-cookie"]
    assert "suyuan-share-grant=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/api/suyuan/html-artifacts/artifact-1/" in cookie


@pytest.mark.asyncio
async def test_report_share_rewrites_base_and_scopes_grant(tmp_path, monkeypatch):
    from app.api import report_routes

    report_dir = tmp_path / "report-1"
    report_dir.mkdir()
    html = report_dir / "report.html"
    html.write_text(
        '<html><head><base href="/api/reports/report-1/"></head></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        report_routes.quarto_report_renderer,
        "find_shared_html",
        lambda token: html,
    )

    response = await report_routes.get_shared_report("share-token")

    assert '<base href="/api/suyuan/reports/report-1/">' in response.body.decode()
    assert "Path=/api/suyuan/reports/report-1/" in response.headers["set-cookie"]
