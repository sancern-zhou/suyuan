from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from app.agent.resources.resource_service import ResourcePublishResult, StoredResource
from app.api import session_resource_routes


def spreadsheet(**updates):
    values = {
        "resource_id": "sheet-1",
        "session_id": "session-1",
        "group_id": "group-1",
        "parent_resource_id": None,
        "resource_key": "primary:xlsx",
        "relation": "primary",
        "kind": "file",
        "role": "attachment",
        "label": "data.xlsx",
        "locator": {"path": "/registry/data.xlsx"},
        "format": "xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "renderer": "spreadsheet",
        "capabilities": ["preview", "download", "edit"],
        "metadata": {},
        "tool_name": "upload_chat",
        "run_id": "upload-1",
        "turn_sequence": 0,
        "version": 1,
        "status": "active",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(updates)
    return StoredResource(**values)


class Catalog:
    async def require_write(self, session_id, _user):
        assert session_id == "session-1"


def xlsx_bytes(value="edited"):
    output = BytesIO()
    workbook = Workbook()
    workbook.active["A1"] = value
    workbook.save(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_save_spreadsheet_replaces_the_primary_and_returns_catalog_receipt(monkeypatch):
    current = spreadsheet()

    class Service:
        saved = b""

        async def get_resource(self, *_args, **_kwargs):
            return current

        async def replace_primary_file(self, session_id, run_id, resource_id, path):
            assert (session_id, resource_id) == ("session-1", "sheet-1")
            self.saved = path.read_bytes() if hasattr(path, "read_bytes") else open(path, "rb").read()
            next_resource = spreadsheet(resource_id="sheet-2", version=2)
            return ResourcePublishResult(9, 2, [next_resource])

    service = Service()
    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: service),
    )
    edited_bytes = xlsx_bytes()
    upload = UploadFile(filename="data.xlsx", file=BytesIO(edited_bytes))

    result = await session_resource_routes.save_session_resource(
        "session-1", "sheet-1", file=upload, user=object(), catalog=Catalog()
    )

    assert service.saved == edited_bytes
    assert result == {
        "success": True,
        "resource_version": 9,
        "changed_resource_ids": ["sheet-2"],
    }


@pytest.mark.asyncio
async def test_save_spreadsheet_rejects_a_non_editable_resource(monkeypatch):
    class Service:
        async def get_resource(self, *_args, **_kwargs):
            return spreadsheet(renderer="pdf", capabilities=["preview", "download"])

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )
    upload = UploadFile(filename="data.xlsx", file=BytesIO(b"PK\x03\x04edited"))

    with pytest.raises(HTTPException) as exc_info:
        await session_resource_routes.save_session_resource(
            "session-1", "sheet-1", file=upload, user=object(), catalog=Catalog()
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "resource_not_editable"


@pytest.mark.asyncio
async def test_save_spreadsheet_rejects_corrupt_xlsx_before_replacement(monkeypatch):
    class Service:
        async def get_resource(self, *_args, **_kwargs):
            return spreadsheet()

        async def replace_primary_file(self, *_args, **_kwargs):
            raise AssertionError("corrupt workbook must not be published")

    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: Service()),
    )
    upload = UploadFile(
        filename="data.xlsx", file=BytesIO(b"PK\x03\x04not-a-workbook")
    )

    with pytest.raises(HTTPException) as exc_info:
        await session_resource_routes.save_session_resource(
            "session-1", "sheet-1", file=upload, user=object(), catalog=Catalog()
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid_spreadsheet_content"
