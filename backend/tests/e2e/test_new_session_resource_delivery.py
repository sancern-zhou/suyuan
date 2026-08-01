from datetime import datetime

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService
from app.api import session_resource_routes, session_routes
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


class Catalog:
    def __init__(self, row):
        self.row = row

    async def require_read(self, session_id, _user):
        assert session_id == self.row.session_id
        return self.row


class Adapters:
    def get(self, _source):
        class Adapter:
            async def restore(self, row, **_options):
                return {
                    "normalized_session": {
                        "session_id": row.session_id,
                        "source": "web",
                        "conversation_history": [
                            {"type": "user", "content": "生成报告"},
                            {"type": "final", "content": "报告已生成"},
                        ],
                    }
                }

        return Adapter()


def declaration(path, **updates):
    payload = {
        "kind": "file",
        "group_key": "report:new-session",
        "resource_key": "docx",
        "relation": "primary",
        "role": "report",
        "label": path.name,
        "locator": {"path": str(path)},
        "format": path.suffix.lstrip("."),
        "media_type": "application/octet-stream",
        "renderer": "file",
        "capabilities": ["preview", "download"],
        "tool_name": "report",
    }
    payload.update(updates)
    return ResourceDeclaration.model_validate(payload)


def contains_preview_payload(value):
    if isinstance(value, dict):
        return any("preview" in str(key).lower() or contains_preview_payload(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_preview_payload(item) for item in value)
    return False


@pytest.mark.asyncio
async def test_new_session_publish_restore_catalog_and_content(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    docx = registry / "report.docx"
    pdf = registry / "report.pdf"
    docx.write_bytes(b"docx")
    pdf.write_bytes(b"%PDF")
    service = SessionResourceService.in_memory()
    published = await service.publish_group(
        "session-new",
        "run-1",
        "report:new-session",
        [
            declaration(docx),
            declaration(
                pdf,
                resource_key="pdf",
                parent_key="docx",
                relation="preview",
                renderer="pdf",
                media_type="application/pdf",
            ),
        ],
    )
    monkeypatch.setattr(
        SessionResourceService,
        "database",
        classmethod(lambda _cls: service),
    )
    monkeypatch.setattr(session_resource_routes, "get_data_registry", lambda: registry)
    row = ConversationCatalogRecord(
        session_id="session-new",
        owner_user_id="u1",
        owner_username="u1",
        owner_display_name="U1",
        source=ConversationSource.WEB,
        mode="assistant",
        title="new",
        created_at=datetime(2026, 8, 2),
        updated_at=datetime(2026, 8, 2),
    )
    catalog_access = Catalog(row)

    restored = await session_routes.restore_session(
        "session-new", user=object(), catalog=catalog_access, adapters=Adapters()
    )
    catalog = await session_resource_routes.get_session_resources(
        "session-new", user=object(), catalog=catalog_access
    )
    delivered = [
        await session_resource_routes.get_session_resource_content(
            "session-new", item.resource_id, user=object(), catalog=catalog_access
        )
        for item in published.resources
    ]

    assert restored["session"]["resource_version"] == 1
    assert restored["session"]["resource_counts"]["total"] == 2
    assert not contains_preview_payload(restored["session"]["conversation_history"])
    assert catalog["resources"][0]["group_id"] == catalog["resources"][1]["group_id"]
    assert all("locator" not in item for item in catalog["resources"])
    assert {response.path for response in delivered} == {docx, pdf}
