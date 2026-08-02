import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService


def declaration(
    group_key: str,
    resource_key: str,
    path: str,
    *,
    relation: str = "primary",
    parent_key: str | None = None,
    renderer: str = "file",
    role: str = "output",
) -> ResourceDeclaration:
    return ResourceDeclaration.model_validate(
        {
            "kind": "file",
            "group_key": group_key,
            "resource_key": resource_key,
            "parent_key": parent_key,
            "relation": relation,
            "role": role,
            "label": resource_key,
            "locator": {"path": path},
            "format": path.rsplit(".", 1)[-1],
            "media_type": "application/pdf" if path.endswith(".pdf") else "application/octet-stream",
            "renderer": renderer,
            "capabilities": ["preview", "download"],
            "tool_name": "test_tool",
        }
    )


def report(group_key: str, version: str) -> list[ResourceDeclaration]:
    primary_key = f"source:{version}"
    return [
        declaration(group_key, primary_key, f"/tmp/{version}.docx"),
        declaration(
            group_key,
            f"preview:{version}",
            f"/tmp/{version}.pdf",
            relation="preview",
            parent_key=primary_key,
            renderer="pdf",
        ),
    ]


@pytest.mark.asyncio
async def test_publish_group_keeps_versions_and_binds_children():
    service = SessionResourceService.in_memory()
    first = await service.publish_group("s1", "run-1", "report:air", report("report:air", "v1"))
    second = await service.publish_group("s1", "run-2", "report:air", report("report:air", "v2"))

    assert first.catalog_version == 1
    assert first.group_version == 1
    assert second.catalog_version == 2
    assert second.group_version == 2

    current = await service.list_resources("s1", status="active")
    history = await service.list_resources("s1", status=None)
    assert {resource.version for resource in current.resources} == {2}
    assert {resource.version for resource in history.resources} == {1, 2}
    preview = next(resource for resource in current.resources if resource.relation == "preview")
    primary = next(resource for resource in current.resources if resource.relation == "primary")
    assert preview.parent_resource_id == primary.resource_id


@pytest.mark.asyncio
async def test_attach_derivatives_uses_parent_group_version():
    service = SessionResourceService.in_memory()
    primary_declaration = declaration("report:air", "source:v1", "/tmp/v1.docx")
    published = await service.publish_group("s1", "run-1", "report:air", [primary_declaration])
    primary = published.resources[0]
    preview = declaration(
        "report:air",
        "preview:v1",
        "/tmp/v1.pdf",
        relation="preview",
        parent_key="source:v1",
        renderer="pdf",
    )

    attached = await service.attach_resources("s1", "render-1", primary.resource_id, [preview])

    assert attached.catalog_version == 2
    assert attached.group_version == primary.version
    assert attached.resources[0].group_id == primary.group_id
    assert attached.resources[0].version == primary.version
    assert attached.resources[0].parent_resource_id == primary.resource_id


@pytest.mark.asyncio
async def test_failed_publication_is_atomic_and_does_not_increment_versions():
    service = SessionResourceService.in_memory()
    published = await service.publish_group("s1", "run-1", "report:air", report("report:air", "v1"))
    invalid = [
        declaration("report:air", "source:v2", "/tmp/v2.docx"),
        declaration(
            "report:air",
            "preview:v2",
            "/tmp/v2.pdf",
            relation="preview",
            parent_key="missing",
            renderer="pdf",
        ),
    ]

    with pytest.raises(ValueError, match="parent"):
        await service.publish_group("s1", "run-2", "report:air", invalid)

    assert await service.catalog_version("s1") == published.catalog_version
    current = await service.list_resources("s1")
    assert {resource.version for resource in current.resources} == {1}


@pytest.mark.asyncio
async def test_catalog_filters_and_counts_use_renderer_contract():
    service = SessionResourceService.in_memory()
    await service.publish_group("s1", "run-1", "report:air", report("report:air", "v1"))

    pdfs = await service.list_resources("s1", renderer="pdf")
    assert [resource.renderer for resource in pdfs.resources] == ["pdf"]
    counts = await service.resource_counts("s1")
    assert counts.total == 2
    assert counts.documents == 1
    assert counts.files == 2


@pytest.mark.asyncio
async def test_get_and_delete_are_scoped_to_session_and_resource_id():
    service = SessionResourceService.in_memory()
    published = await service.publish_group(
        "s1", "run-1", "upload:image", [declaration("upload:image", "source", "/tmp/image.jpg")]
    )
    resource_id = published.resources[0].resource_id

    assert (await service.get_resource("s1", resource_id)).resource_id == resource_id
    assert await service.get_resource("s2", resource_id) is None
    assert await service.delete_resource("s2", resource_id) is False
    assert await service.delete_resource("s1", resource_id) is True
    assert await service.delete_resource("s1", resource_id) is False


@pytest.mark.asyncio
async def test_publication_materializes_external_file_into_session_storage(tmp_path):
    source = tmp_path / "outside" / "result.md"
    source.parent.mkdir()
    source.write_text("result", encoding="utf-8")
    storage = tmp_path / "registry" / "sessions" / "resource_content"
    service = SessionResourceService(storage_root=storage)

    published = await service.publish_group(
        "session-a",
        "run-a",
        "write:file",
        [declaration("write:file", "primary:md", str(source), renderer="markdown")],
    )

    copied = published.resources[0].locator["path"]
    assert copied != str(source.resolve())
    assert copied.startswith(str(storage.resolve()))
    assert open(copied, encoding="utf-8").read() == "result"

    source.write_text("new result", encoding="utf-8")
    second = await service.publish_group(
        "session-a",
        "run-b",
        "write:file",
        [declaration("write:file", "primary:md", str(source), renderer="markdown")],
    )
    second_copy = second.resources[0].locator["path"]
    assert second_copy != copied
    assert open(copied, encoding="utf-8").read() == "result"
    assert open(second_copy, encoding="utf-8").read() == "new result"


@pytest.mark.asyncio
async def test_replace_primary_file_publishes_next_version_in_same_group(tmp_path):
    original = tmp_path / "original.xlsx"
    original.write_bytes(b"original")
    edited = tmp_path / "edited.xlsx"
    edited.write_bytes(b"edited")
    spreadsheet = ResourceDeclaration.model_validate(
        {
            **declaration(
                "upload:sheet",
                "primary:xlsx",
                str(original),
                renderer="spreadsheet",
                role="attachment",
            ).model_dump(),
            "capabilities": ["preview", "download", "edit"],
        }
    )
    service = SessionResourceService.in_memory()
    published = await service.publish_group(
        "session-a", "upload-1", "upload:sheet", [spreadsheet]
    )
    previous = published.resources[0]

    replacement = await service.replace_primary_file(
        "session-a", "edit-1", previous.resource_id, edited
    )

    current = replacement.resources[0]
    history = await service.list_resources("session-a", status=None)
    assert replacement.catalog_version == 2
    assert replacement.group_version == 2
    assert current.group_id == previous.group_id
    assert current.resource_id != previous.resource_id
    assert current.version == 2
    assert current.locator["path"] == str(edited.resolve())
    assert current.metadata["size"] == len(b"edited")
    assert {item.status for item in history.resources} == {"active", "superseded"}
