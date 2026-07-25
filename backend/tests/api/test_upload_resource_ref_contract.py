from datetime import UTC, datetime
from inspect import signature
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import ResourceBatchResult, StoredResource
from app.api import session_routes, upload_routes


class _ResourceService:
    def __init__(self):
        self.stored: StoredResource | None = None

    async def upsert_run_resources(
        self,
        session_id: str,
        run_id: str,
        resources: list[ResourceDeclaration],
        *,
        turn_sequence: int = 0,
    ) -> ResourceBatchResult:
        self.stored = StoredResource.from_declaration(
            session_id,
            run_id,
            resources[0],
            turn_sequence=turn_sequence,
        )
        return ResourceBatchResult(version=1, resources=[self.stored])


class _UploadDatabase:
    def __init__(self):
        self.uploaded_file = None

    def add(self, uploaded_file):
        self.uploaded_file = uploaded_file

    async def commit(self):
        return None

    async def refresh(self, uploaded_file):
        uploaded_file.created_at = datetime.now(UTC)


class _Catalog:
    async def claim_web_draft(self, **_kwargs):
        return None

    async def require_read(self, *_args, **_kwargs):
        return None


def test_chat_upload_rejects_an_empty_session_id_at_the_http_boundary():
    session_id_form = signature(upload_routes.upload_chat_file).parameters["session_id"].default

    assert session_id_form.metadata[0].min_length == 1


@pytest.mark.asyncio
async def test_chat_upload_returns_the_persisted_session_resource_ref(tmp_path, monkeypatch):
    resource_service = _ResourceService()
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
        db=_UploadDatabase(),
        user=object(),
        catalog=_Catalog(),
    )

    assert resource_service.stored is not None
    assert result["resource_ref"]["ref_id"] == resource_service.stored.resource_id
    assert result["resource_ref"]["resource_id"] == resource_service.stored.resource_id
    assert result["resource_ref"]["kind"] == "file"
    assert result["resource_ref"]["role"] == "source"
    assert result["resource_ref"]["metadata"]["source"] == "user_upload"


@pytest.mark.asyncio
async def test_session_resource_list_exposes_ref_id_alias(monkeypatch):
    resource_service = _ResourceService()
    declaration = ResourceDeclaration.model_validate(
        {
            "kind": "file",
            "logical_key": "upload:file-1",
            "role": "source",
            "label": "evidence.png",
            "locator": {"path": "/tmp/evidence.png"},
            "metadata": {"file_id": "file-1", "mime_type": "image/png"},
            "tool_name": "upload_chat",
        }
    )
    batch = await resource_service.upsert_run_resources(
        "assistant_session_upload_contract",
        "upload:file-1",
        [declaration],
    )

    class _ListService:
        async def list_resources(self, *_args, **_kwargs):
            return type("Page", (), {"resources": batch.resources, "next_cursor": None})()

    monkeypatch.setattr(
        session_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: _ListService()),
    )

    result = await session_routes.get_session_resources(
        session_id="assistant_session_upload_contract",
        user=object(),
        catalog=_Catalog(),
    )

    resource = result["resources"][0]
    assert resource["ref_id"] == resource["resource_id"]
