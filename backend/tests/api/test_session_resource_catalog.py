from datetime import UTC, datetime
from inspect import signature
from urllib.parse import parse_qs, urlparse

import pytest

from app.agent.resources.resource_service import ResourcePage, StoredResource
from app.api import session_resource_routes


def stored_resource(**updates) -> StoredResource:
    values = {
        "resource_id": "resource-1",
        "session_id": "session-1",
        "group_id": "group-1",
        "parent_resource_id": None,
        "resource_key": "report",
        "relation": "primary",
        "kind": "file",
        "role": "output",
        "label": "Air report.pdf",
        "locator": {"path": "/tmp/private/air-report.pdf"},
        "format": "pdf",
        "media_type": "application/pdf",
        "renderer": "pdf",
        "capabilities": ["preview", "download"],
        "metadata": {"private_path": "/tmp/private/other"},
        "tool_name": "report",
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


@pytest.mark.asyncio
async def test_catalog_exposes_delivery_contract_without_physical_locator(monkeypatch):
    resource = stored_resource()

    class Service:
        async def list_resources(self, *_args, **_kwargs):
            return ResourcePage([resource])

        async def catalog_version(self, session_id):
            assert session_id == "session-1"
            return 7

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )

    response = await session_resource_routes.get_session_resources(
        "session-1", user=object(), catalog=Catalog()
    )

    item = response["resources"][0]
    assert response["resource_version"] == 7
    assert item["resource_id"] == "resource-1"
    assert item["ref_id"] == "resource-1"
    assert item["group_id"] == "group-1"
    assert item["relation"] == "primary"
    assert item["renderer"] == "pdf"
    parsed = urlparse(item["content_url"])
    assert parsed.path.endswith("/resource-1/content")
    assert parse_qs(parsed.query)["preview_ticket"]
    download = urlparse(item["download_url"])
    assert parse_qs(download.query)["preview_ticket"]
    assert parse_qs(download.query)["disposition"] == ["attachment"]
    assert "locator" not in item
    assert "metadata" not in item
    assert "file_path" not in item
    assert "/tmp/" not in str(response)


@pytest.mark.asyncio
async def test_catalog_does_not_project_agent_internal_sources_data_or_urls(monkeypatch):
    resources = [
        stored_resource(resource_id="attachment", role="attachment"),
        stored_resource(resource_id="source", role="source"),
        stored_resource(resource_id="data", kind="data"),
        stored_resource(resource_id="url", kind="url"),
    ]

    class Service:
        async def list_resources(self, *_args, **_kwargs):
            return ResourcePage(resources)

        async def catalog_version(self, _session_id):
            return 4

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )

    response = await session_resource_routes.get_session_resources(
        "session-1", user=object(), catalog=Catalog()
    )

    assert [item["resource_id"] for item in response["resources"]] == ["attachment"]


def test_catalog_uses_group_renderer_filters_and_has_no_presentation_type():
    parameters = signature(session_resource_routes.get_session_resources).parameters
    assert {"kind", "role", "renderer", "group_id", "status", "cursor"} <= set(parameters)
    assert "presentation_type" not in parameters


def test_directory_artifact_content_url_has_trailing_slash():
    item = session_resource_routes.resource_dto(
        "session-1",
        stored_resource(
            kind="artifact",
            format="html",
            renderer="html",
            metadata={"entrypoint": "index.html"},
        ),
    )
    parsed = urlparse(item["content_url"])
    assert parsed.path.endswith("/resource-1/content/")
    assert parse_qs(parsed.query)["preview_ticket"]


def test_action_links_ignore_untrusted_metadata_urls_and_unsupported_capabilities():
    item = session_resource_routes.resource_dto(
        "session-1",
        stored_resource(
            capabilities=["edit", "share"],
            metadata={
                "preview_url": "https://attacker.invalid/preview",
                "edit_url": "https://attacker.invalid/edit",
            },
        ),
    )
    assert item["actions"] == {}
    assert item["download_url"] is None
    assert "attacker.invalid" not in str(item)


def test_editable_spreadsheet_exposes_only_resource_scoped_save_action():
    item = session_resource_routes.resource_dto(
        "session-1",
        stored_resource(
            format="xlsx",
            renderer="spreadsheet",
            capabilities=["preview", "download", "edit"],
        ),
    )

    assert item["actions"]["save"].endswith(
        "/sessions/session-1/resources/resource-1/save"
    )
    assert "/office/" not in str(item)


def test_csv_spreadsheet_does_not_expose_the_excel_save_action():
    item = session_resource_routes.resource_dto(
        "session-1",
        stored_resource(
            format="csv",
            renderer="spreadsheet",
            capabilities=["preview", "download", "edit"],
        ),
    )

    assert "save" not in item["actions"]
