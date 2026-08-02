from datetime import UTC, datetime
from inspect import signature
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.agent.resources.resource_service import (
    ResourceCounts,
    ResourcePublishResult,
    StoredResource,
    stable_group_id,
)
from app.api import session_routes, upload_routes


class ResourceService:
    def __init__(self):
        self.stored: StoredResource | None = None
        self.group_key: str | None = None

    async def publish_group(
        self,
        session_id,
        run_id,
        group_key,
        resources,
        *,
        turn_sequence=0,
    ):
        self.group_key = group_key
        self.stored = StoredResource.from_declaration(
            session_id,
            run_id,
            stable_group_id(session_id, group_key),
            1,
            resources[0],
            turn_sequence=turn_sequence,
        )
        return ResourcePublishResult(1, 1, [self.stored])


class UploadDatabase:
    def __init__(self):
        self.uploaded_file = None

    def add(self, uploaded_file):
        self.uploaded_file = uploaded_file

    async def commit(self):
        return None

    async def refresh(self, uploaded_file):
        uploaded_file.created_at = datetime.now(UTC)


class Catalog:
    async def claim_web_draft(self, **_kwargs):
        return None

    async def require_read(self, *_args, **_kwargs):
        return None


def test_chat_upload_rejects_an_empty_session_id_at_the_http_boundary():
    session_id_form = signature(upload_routes.upload_chat_file).parameters[
        "session_id"
    ].default
    assert session_id_form.metadata[0].min_length == 1


@pytest.mark.parametrize(
    ("mime_type", "filename", "renderer"),
    [
        ("application/pdf", "report.pdf", "pdf"),
        ("text/markdown", "notes.md", "markdown"),
        ("text/csv", "data.csv", "spreadsheet"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data.xlsx", "spreadsheet"),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "report.docx", "file"),
    ],
)
def test_attachment_renderer_uses_supported_unified_previewers(mime_type, filename, renderer):
    assert upload_routes._attachment_renderer(mime_type, filename) == renderer


@pytest.mark.asyncio
async def test_chat_upload_publishes_an_attachment_resource_group(tmp_path, monkeypatch):
    resource_service = ResourceService()
    monkeypatch.setattr(upload_routes, "UPLOAD_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(
        upload_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: resource_service),
    )
    upload = UploadFile(
        file=BytesIO(b"png-bytes"),
        filename="evidence.png",
        headers=Headers({"content-type": "image/png"}),
    )

    result = await upload_routes.upload_chat_file(
        file=upload,
        session_id="assistant_session_upload_contract",
        mode="assistant",
        db=UploadDatabase(),
        user=object(),
        catalog=Catalog(),
    )

    stored = resource_service.stored
    assert stored is not None
    assert resource_service.group_key == f"upload:{result['file_id']}"
    assert stored.role == "attachment"
    assert stored.relation == "primary"
    assert stored.renderer == "image"
    assert stored.capabilities == ["download", "preview"]
    assert result["resource_ref"]["resource_id"] == stored.resource_id
    assert result["resource_ref"]["group_id"] == stored.group_id
    assert "metadata" not in result["resource_ref"]
    assert str(tmp_path) not in str(result["resource_ref"])


@pytest.mark.asyncio
async def test_social_restore_exposes_unified_resource_counts(monkeypatch):
    class RestoreCatalog:
        async def require_read(self, *_args, **_kwargs):
            return type("Row", (), {"source": "social"})()

    class Adapter:
        async def restore(self, *_args, **_kwargs):
            return {"normalized_session": {"session_id": "social-session"}}

    class Adapters:
        def get(self, _source):
            return Adapter()

    class CountService:
        async def catalog_version(self, _session_id):
            return 1

        async def resource_counts(self, _session_id):
            return ResourceCounts(total=1, files=1)

    monkeypatch.setattr(
        session_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: CountService()),
    )

    result = await session_routes.restore_session(
        session_id="social-session",
        user=object(),
        catalog=RestoreCatalog(),
        adapters=Adapters(),
    )

    assert result["session"]["resource_counts"]["files"] == 1
