from importlib.util import find_spec
import time

import httpx
import pytest
from fastapi import FastAPI

from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.share_access import (
    ShareAccessService,
    external_api_path,
    resource_preview_identity,
)
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
    identity = resource_preview_identity("session-1", "resource-1")
    grant = service.issue("session-resource", identity, now=now)

    assert service.verify(grant, "session-resource", identity, now=now + 10)
    assert not service.verify(grant, "session-resource", resource_preview_identity("session-1", "resource-2"), now=now + 10)
    assert not service.verify(grant, "report", identity, now=now + 10)
    assert not service.verify(f"{grant}x", "session-resource", identity, now=now + 10)
    assert not service.verify(grant, "session-resource", identity, now=now + 61)


@pytest.mark.asyncio
async def test_preview_ticket_permits_only_bound_resource_subtree():
    grants = ShareAccessService("secret", ttl_seconds=60)
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(),
        auth_service=RejectingAuth(),
        share_access=grants,
    )

    @app.get("/api/sessions/{session_id}/resources/{resource_id}/content/{path:path}")
    async def resource_asset(session_id: str, resource_id: str, path: str):
        return {"session_id": session_id, "resource_id": resource_id, "path": path}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    grant = grants.issue(
        "session-resource",
        resource_preview_identity("session-1", "resource-1"),
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.get(
            f"/api/sessions/session-1/resources/resource-1/content/assets/chart.png?preview_ticket={grant}",
        )
        cross_resource = await client.get(
            f"/api/sessions/session-1/resources/resource-2/content/assets/chart.png?preview_ticket={grant}",
        )
        altered = await client.get(
            f"/api/sessions/session-1/resources/resource-1/content/assets/chart.png?preview_ticket={grant}x",
        )

    assert allowed.status_code == 200
    assert cross_resource.status_code == 401
    assert altered.status_code == 401


def test_legacy_social_media_transport_is_physically_removed():
    from app.core.routing import ROUTER_REGISTRY

    assert find_spec("app.services.signed_media") is None
    assert find_spec("app.services.media_object_store") is None
    assert find_spec("app.api.signed_media_routes") is None
    assert not any(spec.module == "app.api.signed_media_routes" for spec in ROUTER_REGISTRY)

    settings = Settings(_env_file=None)
    legacy_fields = {
        "signed_media_base_url",
        "signed_media_secret",
        "signed_media_ttl_seconds",
        "media_object_store_enabled",
        "media_object_store_endpoint_url",
        "media_object_store_access_key_id",
        "media_object_store_secret_access_key",
        "media_object_store_bucket",
        "media_object_store_region",
        "media_object_store_prefix",
        "media_object_store_presign_ttl_seconds",
    }
    assert legacy_fields.isdisjoint(type(settings).model_fields)
    assert Settings(_env_file=None, signed_media_secret="legacy-secret").share_signing_secret is None
