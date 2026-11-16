"""HTML 预览运行时注入与 CSP 档位的行为测试。"""
from datetime import UTC, datetime

import pytest

from app.agent.resources.resource_service import StoredResource
from app.api import session_resource_routes
from app.services.html_preview_runtime import RUNTIME_MARKER, inject_html_runtime


def stored_resource(**updates) -> StoredResource:
    values = {
        "resource_id": "resource-1",
        "session_id": "session-1",
        "group_id": "group-1",
        "parent_resource_id": None,
        "resource_key": "preview:html",
        "relation": "preview",
        "kind": "artifact",
        "role": "output",
        "label": "交互报告",
        "locator": {"path": "/tmp/private/air-report"},
        "format": "html",
        "media_type": "text/html",
        "renderer": "html",
        "capabilities": ["preview"],
        "metadata": {"entrypoint": "index.html"},
        "tool_name": "create_html_artifact",
        "run_id": "run-1",
        "turn_sequence": 2,
        "version": 3,
        "status": "active",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(updates)
    return StoredResource(**values)


class Catalog:
    async def require_read(self, *_args):
        return object()


class Service:
    def __init__(self, resource):
        self._resource = resource

    async def get_resource(self, *_args, **_kwargs):
        return self._resource


def _html_document(body: str = "<p>hello</p>") -> str:
    return (
        "<!doctype html><html><head><title>t</title></head>"
        f"<body>{body}</body></html>"
    )


def test_inject_places_runtime_before_body_close():
    injected = inject_html_runtime(_html_document())
    assert injected.endswith("</body></html>")
    marker_index = injected.index(RUNTIME_MARKER)
    assert marker_index < injected.rindex("</body>")


def test_inject_is_idempotent():
    html = _html_document()
    once = inject_html_runtime(html)
    assert inject_html_runtime(once) == once
    assert inject_html_runtime(once).count("<script") == 1


def test_inject_appends_when_no_document_skeleton():
    injected = inject_html_runtime("<p>fragment</p>")
    assert injected.startswith("<p>fragment</p>")
    assert injected.endswith("</script>")


def test_csp_defaults_to_strict_profile_for_plain_html():
    csp, no_store = session_resource_routes._html_content_security_policy(
        stored_resource(), "report.html"
    )
    assert csp == session_resource_routes.HTML_CSP_PROFILES["default"]
    assert "webapi.amap.com" not in csp
    assert no_store is False


def test_csp_profile_metadata_selects_relaxed_profile():
    csp, no_store = session_resource_routes._html_content_security_policy(
        stored_resource(metadata={"entrypoint": "index.html", "csp_profile": "amap"}),
        "report.html",
    )
    assert "webapi.amap.com" in csp
    assert no_store is True


def test_unknown_csp_profile_falls_back_to_default():
    csp, no_store = session_resource_routes._html_content_security_policy(
        stored_resource(metadata={"csp_profile": "https://attacker.invalid"}), "report.html"
    )
    assert csp == session_resource_routes.HTML_CSP_PROFILES["default"]
    assert no_store is False


def test_legacy_daily_review_filename_keeps_amap_profile():
    csp, no_store = session_resource_routes._html_content_security_policy(
        stored_resource(), "xuchang_air_quality_daily_review_2026-11-12.html"
    )
    assert "webapi.amap.com" in csp
    assert no_store is True


@pytest.mark.asyncio
async def test_inline_html_content_injects_runtime(monkeypatch, tmp_path):
    document = tmp_path / "index.html"
    document.write_text(_html_document(), encoding="utf-8")
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: tmp_path)
    resource = stored_resource(locator={"path": str(tmp_path)})
    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service(resource)),
    )

    response = await session_resource_routes.get_session_resource_content(
        "session-1", "resource-1", user=object(), catalog=Catalog()
    )

    body = response.body
    assert isinstance(body, bytes)
    assert RUNTIME_MARKER.encode() in body
    assert _html_document().encode() not in body
    assert response.headers["content-type"].startswith("text/html")
    assert "content-security-policy" in response.headers
    assert response.headers["content-security-policy"] == (
        session_resource_routes.HTML_CSP_PROFILES["default"]
    )


@pytest.mark.asyncio
async def test_attachment_html_serves_pristine_file_response(monkeypatch, tmp_path):
    document = tmp_path / "index.html"
    document.write_text(_html_document(), encoding="utf-8")
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: tmp_path)
    resource = stored_resource(
        locator={"path": str(tmp_path)},
        capabilities=["preview", "download"],
    )
    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service(resource)),
    )

    response = await session_resource_routes.get_session_resource_content(
        "session-1", "resource-1", disposition="attachment", user=object(), catalog=Catalog()
    )

    # 下载走 FileResponse 原样字节流，不做注入改写。
    from fastapi.responses import FileResponse

    assert isinstance(response, FileResponse)
    assert RUNTIME_MARKER not in document.read_text(encoding="utf-8")
