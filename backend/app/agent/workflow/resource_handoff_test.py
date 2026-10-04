from types import SimpleNamespace

import pytest

from app.agent.context.execution_context import ExecutionContext
from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService, validate_publication
from app.agent.workflow.resource_handoff import (
    import_workflow_handles,
    result_resource_declarations,
    stored_resource_ref,
)
from app.tools.agent_tools import call_sub_agent as call_sub_agent_module
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


@pytest.mark.asyncio
async def test_dependency_resource_is_registered_in_downstream_session(tmp_path):
    source_file = tmp_path / "source.json"
    source_file.write_text('{"value": 1}', encoding="utf-8")
    service = SessionResourceService.in_memory()
    source = await service.publish_group(
        "source-session",
        "source-run",
        "source-data",
        [ResourceDeclaration.model_validate({
            "kind": "data",
            "group_key": "source-data",
            "resource_key": "primary",
            "relation": "primary",
            "role": "output",
            "label": "source.json",
            "locator": {"path": str(source_file)},
            "format": "json",
            "media_type": "application/json",
            "renderer": "file",
            "capabilities": ["download"],
        })],
    )
    handle = stored_resource_ref(source.resources[0])
    handle["source_task_id"] = "query"

    imported = await import_workflow_handles(
        service,
        target_session_id="downstream-session",
        run_id="downstream-run",
        handles=[handle],
    )

    assert len(imported) == 1
    assert imported[0]["source_session_id"] == "downstream-session"
    assert imported[0]["file_path"] == str(source_file.resolve())
    assert await service.get_resource(
        "downstream-session", imported[0]["resource_id"]
    ) is not None


@pytest.mark.asyncio
async def test_dependency_resource_group_keeps_primary_preview_relationship(tmp_path):
    source_file = tmp_path / "report.qmd"
    preview_file = tmp_path / "report.pdf"
    source_file.write_text("# Report", encoding="utf-8")
    preview_file.write_bytes(b"pdf")
    service = SessionResourceService.in_memory()
    publication = await service.publish_group(
        "source-session",
        "source-run",
        "report:source",
        [
            ResourceDeclaration.model_validate({
                "kind": "file",
                "group_key": "report:source",
                "resource_key": "qmd",
                "relation": "primary",
                "role": "report",
                "label": "report.qmd",
                "locator": {"path": str(source_file)},
                "format": "qmd",
                "media_type": "text/markdown",
                "renderer": "markdown",
                "capabilities": ["download", "render"],
            }),
            ResourceDeclaration.model_validate({
                "kind": "file",
                "group_key": "report:source",
                "resource_key": "pdf",
                "parent_key": "qmd",
                "relation": "preview",
                "role": "report",
                "label": "report.pdf",
                "locator": {"path": str(preview_file)},
                "format": "pdf",
                "media_type": "application/pdf",
                "renderer": "pdf",
                "capabilities": ["preview", "download"],
            }),
        ],
    )
    handles = [stored_resource_ref(item) for item in publication.resources]

    imported = await import_workflow_handles(
        service,
        target_session_id="downstream-session",
        run_id="downstream-run",
        handles=handles,
    )

    assert len(imported) == 2
    assert len({item["group_id"] for item in imported}) == 1
    primary = next(item for item in imported if item["relation"] == "primary")
    preview = next(item for item in imported if item["relation"] == "preview")
    assert preview["parent_resource_id"] == primary["resource_id"]


def test_workflow_result_declarations_keep_resource_groups():
    refs = [
        {
            "resource_id": "source-primary",
            "source_session_id": "child",
            "group_id": "source-group",
            "parent_resource_id": None,
            "resource_key": "qmd",
            "relation": "primary",
            "kind": "file",
            "role": "report",
            "label": "report.qmd",
            "locator": {"path": "/tmp/report.qmd"},
            "format": "qmd",
            "media_type": "text/markdown",
            "renderer": "markdown",
            "capabilities": ["download", "render"],
        },
        {
            "resource_id": "source-preview",
            "source_session_id": "child",
            "group_id": "source-group",
            "parent_resource_id": "source-primary",
            "resource_key": "pdf",
            "relation": "preview",
            "kind": "file",
            "role": "report",
            "label": "report.pdf",
            "locator": {"path": "/tmp/report.pdf"},
            "format": "pdf",
            "media_type": "application/pdf",
            "renderer": "pdf",
            "capabilities": ["preview", "download"],
        },
    ]

    raw = result_resource_declarations(
        "workflow-1",
        {"report": {"data": {"resource_refs": refs}}},
    )
    declarations = [ResourceDeclaration.model_validate(item) for item in raw]

    assert len({item.group_key for item in declarations}) == 1
    by_key = validate_publication(declarations[0].group_key, declarations)
    assert by_key["pdf"].parent_key == "qmd"


@pytest.mark.asyncio
async def test_parent_catalog_data_resource_is_collected_for_child_import(
    tmp_path, monkeypatch
):
    source_file = tmp_path / "parent-data.json"
    source_file.write_text('{"value": 1}', encoding="utf-8")
    service = SessionResourceService.in_memory()
    await service.publish_group(
        "parent-session",
        "parent-run",
        "parent-data",
        [ResourceDeclaration.model_validate({
            "kind": "data",
            "group_key": "parent-data",
            "resource_key": "primary",
            "relation": "primary",
            "role": "attachment",
            "label": "parent-data.json",
            "locator": {"path": str(source_file)},
            "format": "json",
            "media_type": "application/json",
            "renderer": "file",
            "capabilities": ["download"],
        })],
    )
    monkeypatch.setattr(call_sub_agent_module, "get_data_registry", lambda: tmp_path)
    context = SimpleNamespace(tool_executor=SimpleNamespace(
        resource_service=service,
        memory_manager=SimpleNamespace(session_id="parent-session"),
    ))

    handles = await CallSubAgentTool()._collect_parent_resource_handles(context)

    assert len(handles) == 1
    assert handles[0]["kind"] == "data"
    assert handles[0]["source_session_id"] == "parent-session"


def test_authorized_catalog_path_is_registered_for_typed_data_loaders(tmp_path):
    source_file = tmp_path / "source.json"
    source_file.write_text('{"value": 1}', encoding="utf-8")
    session = SimpleNamespace(data_files={})
    data_manager = SimpleNamespace(memory=SimpleNamespace(session=session))
    context = ExecutionContext("downstream", 1, data_manager)

    context.set_authorized_input_paths([str(source_file)])

    resolved = str(source_file.resolve())
    assert context.authorized_input_paths == [resolved]
    assert session.data_files[resolved] == resolved
