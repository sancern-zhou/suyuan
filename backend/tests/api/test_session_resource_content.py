from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.agent.resources.resource_service import StoredResource
from app.api import session_resource_routes
from app.auth.share_access import get_share_access_service, resource_preview_identity


def stored(path: Path, **updates) -> StoredResource:
    values = {
        "resource_id": "resource-1",
        "session_id": "session-1",
        "group_id": "group-1",
        "parent_resource_id": None,
        "resource_key": "report",
        "relation": "primary",
        "kind": "file",
        "role": "output",
        "label": path.name,
        "locator": {"path": str(path)},
        "format": path.suffix.lstrip(".") or "file",
        "media_type": "application/pdf",
        "renderer": "pdf",
        "capabilities": ["preview", "download"],
        "metadata": {},
        "tool_name": "test",
        "run_id": "run-1",
        "turn_sequence": 0,
        "version": 1,
        "status": "active",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(updates)
    return StoredResource(**values)


class Catalog:
    async def require_read(self, *_args):
        return object()


def install_service(monkeypatch, resource):
    class Service:
        async def get_resource(self, session_id, resource_id, **_kwargs):
            if session_id != resource.session_id or resource_id != resource.resource_id:
                return None
            return resource

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )


@pytest.mark.asyncio
async def test_file_content_sets_explicit_inline_and_attachment_dispositions(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    pdf = registry / "report.pdf"
    pdf.write_bytes(b"%PDF")
    install_service(monkeypatch, stored(pdf))
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    inline = await session_resource_routes.get_session_resource_content(
        "session-1", "resource-1", disposition="inline", user=object(), catalog=Catalog()
    )
    download = await session_resource_routes.get_session_resource_content(
        "session-1", "resource-1", disposition="attachment", user=object(), catalog=Catalog()
    )

    assert inline.headers["content-disposition"].startswith("inline;")
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
@pytest.mark.parametrize("asset_path", ["../../secret.txt", "/etc/passwd"])
async def test_directory_content_rejects_path_traversal(tmp_path, monkeypatch, asset_path):
    registry = tmp_path / "registry"
    artifact = registry / "artifact"
    artifact.mkdir(parents=True)
    (artifact / "index.html").write_text("ok")
    install_service(
        monkeypatch,
        stored(
            artifact,
            kind="artifact",
            format="html",
            media_type="text/html",
            renderer="html",
            metadata={"entrypoint": "index.html"},
        ),
    )
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    with pytest.raises(HTTPException) as exc_info:
        await session_resource_routes.get_session_resource_content(
            "session-1",
            "resource-1",
            asset_path=asset_path,
            user=object(),
            catalog=Catalog(),
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_directory_content_rejects_symlink_escape(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    artifact = registry / "artifact"
    artifact.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    (artifact / "escape.txt").symlink_to(outside)
    install_service(
        monkeypatch,
        stored(
            artifact,
            kind="artifact",
            format="html",
            media_type="text/html",
            renderer="html",
            metadata={"entrypoint": "index.html"},
        ),
    )
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    with pytest.raises(HTTPException) as exc_info:
        await session_resource_routes.get_session_resource_content(
            "session-1",
            "resource-1",
            asset_path="escape.txt",
            user=object(),
            catalog=Catalog(),
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_content_hides_unauthorized_wrong_session_and_missing_resources(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    file_path = registry / "report.pdf"
    file_path.write_bytes(b"pdf")
    install_service(monkeypatch, stored(file_path))
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    class DeniedCatalog:
        async def require_read(self, *_args):
            raise HTTPException(status_code=404, detail="session_not_found")

    for session_id, resource_id, catalog in (
        ("private-session", "resource-1", DeniedCatalog()),
        ("wrong-session", "resource-1", Catalog()),
        ("session-1", "missing", Catalog()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await session_resource_routes.get_session_resource_content(
                session_id,
                resource_id,
                user=object(),
                catalog=catalog,
            )
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_content_does_not_expose_agent_internal_source_resources(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    file_path = registry / "source.pdf"
    file_path.write_bytes(b"pdf")
    install_service(monkeypatch, stored(file_path, role="source"))
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    with pytest.raises(HTTPException) as exc_info:
        await session_resource_routes.get_session_resource_content(
            "session-1", "resource-1", user=object(), catalog=Catalog()
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_preview_ticket_serves_bound_resource_and_sets_scoped_asset_cookie(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    pdf = registry / "report.pdf"
    pdf.write_bytes(b"%PDF")
    install_service(monkeypatch, stored(pdf))
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)
    ticket = get_share_access_service().issue(
        "session-resource",
        resource_preview_identity("session-1", "resource-1"),
    )
    query = urlencode({"preview_ticket": ticket}).encode()
    request = Request({
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "server": ("test", 443),
        "path": "/api/sessions/session-1/resources/resource-1/content",
        "query_string": query,
        "headers": [],
    })

    response = await session_resource_routes.get_session_resource_content(
        "session-1",
        "resource-1",
        request=request,
        user=None,
        catalog=Catalog(),
    )

    cookie = response.headers["set-cookie"]
    assert "suyuan-resource-preview=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "Path=/api/suyuan/sessions/session-1/resources/resource-1/content" in cookie


@pytest.mark.asyncio
async def test_html_preview_allows_quarto_assets_from_opaque_sandbox_origin(
    tmp_path, monkeypatch
):
    registry = tmp_path / "registry"
    artifact = registry / "artifact"
    asset = artifact / "report_files" / "quarto.js"
    asset.parent.mkdir(parents=True)
    (artifact / "report.html").write_text("<script src='report_files/quarto.js'></script>")
    asset.write_text("window.quarto = true")
    install_service(
        monkeypatch,
        stored(
            artifact,
            kind="artifact",
            format="html",
            media_type="text/html",
            renderer="html",
            metadata={"entrypoint": "report.html"},
        ),
    )
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)

    html = await session_resource_routes.get_session_resource_content(
        "session-1", "resource-1", user=object(), catalog=Catalog()
    )
    script = await session_resource_routes.get_session_resource_content(
        "session-1",
        "resource-1",
        asset_path="report_files/quarto.js",
        user=object(),
        catalog=Catalog(),
    )

    assert html.headers["access-control-allow-origin"] == "*"
    assert script.headers["access-control-allow-origin"] == "*"
    assert "font-src 'self' data:" in html.headers["content-security-policy"]
