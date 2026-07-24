import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService


def declaration(logical_key: str, path: str, *, presentation_type=None):
    payload = {
        "kind": "file",
        "logical_key": logical_key,
        "role": "output",
        "label": logical_key,
        "locator": {"path": path},
    }
    if presentation_type == "document":
        payload.update({
            "presentation_type": "document",
            "presentation": {
                "format": "html",
                "preview": {"type": "html", "url": "/preview"},
            },
        })
    return ResourceDeclaration.model_validate(payload)


@pytest.mark.asyncio
async def test_upsert_replaces_latest_logical_key_and_keeps_distinct_resources():
    service = SessionResourceService.in_memory()
    first = declaration("report:current", "/tmp/v1.html", presentation_type="document")
    other = declaration("upload:source", "/tmp/source.docx")
    result = await service.upsert_run_resources("session-a", "run-a", [first, other])
    assert result.version == 1
    assert len(result.resources) == 2

    replacement = declaration("report:current", "/tmp/v2.html", presentation_type="document")
    result = await service.upsert_run_resources("session-a", "run-b", [replacement])
    assert result.version == 2
    page = await service.list_resources("session-a")
    assert {item.locator["path"] for item in page.resources} == {"/tmp/v2.html", "/tmp/source.docx"}


@pytest.mark.asyncio
async def test_empty_upsert_does_not_clear_and_filter_counts_are_unified():
    service = SessionResourceService.in_memory()
    await service.upsert_run_resources(
        "session-a", "run-a", [declaration("report:current", "/tmp/report.html", presentation_type="document")]
    )
    result = await service.upsert_run_resources("session-a", "run-b", [])
    assert result.version == 1
    counts = await service.resource_counts("session-a")
    assert counts.total == 1
    assert counts.documents == 1
    filtered = await service.list_resources("session-a", presentation_type="document")
    assert len(filtered.resources) == 1


@pytest.mark.asyncio
async def test_delete_is_idempotent_and_session_isolated():
    service = SessionResourceService.in_memory()
    item = declaration("report:current", "/tmp/report.html", presentation_type="document")
    await service.upsert_run_resources("session-a", "run-a", [item])
    assert await service.delete_resource("session-a", item.resource_key()) is True
    assert await service.delete_resource("session-a", item.resource_key()) is False
    assert (await service.list_resources("session-b")).resources == []
