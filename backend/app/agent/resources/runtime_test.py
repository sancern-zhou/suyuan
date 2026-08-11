import asyncio

import pytest
from pathlib import Path
from types import SimpleNamespace

from app.agent.core.executor import ToolExecutor
from app.agent.resources.contracts import ResourceKind, ResourceRole
from app.agent.resources.resource_map import project_agent_resource_map
from app.agent.resources.resource_service import SessionResourceService, StoredResource
from app.tools.utility.list_directory_tool import ListDirectoryTool
from app.tools.utility.read_file_tool import ReadFileTool
from app.tools.utility.read_session_resource_tool import ReadSessionResourceTool
from app.utils.path_config import BACKEND_ROOT
from app.tools.office.validate_pptx_tool import validation_output_resources
from app.tools.resource_declarations import primary_file
from .contracts import ResourceDeclaration
from .contracts import ResourceLocator
from .runtime import (
    RunResourceAccumulator,
    event_turn_sequence,
    persist_tool_result_resources,
)


def _resource():
    return {
        "kind": "file",
        "group_key": "report:current",
        "resource_key": "source",
        "relation": "primary",
        "role": "report",
        "label": "report",
        "locator": {"path": "/tmp/report.html"},
        "format": "html",
        "media_type": "text/html",
        "renderer": "html",
        "capabilities": ["preview", "download"],
    }


def test_accumulator_reads_only_explicit_resource_list():
    accumulator = RunResourceAccumulator(run_id="run-a")
    grouped = accumulator.capture(
        {"type": "tool_result", "data": {"resources": [_resource()]}},
        turn_sequence=2,
    )
    legacy = accumulator.capture(
        {"type": "tool_result", "data": {"file_path": "/tmp/legacy.html"}},
        turn_sequence=3,
    )
    assert list(grouped) == ["report:current"]
    assert grouped["report:current"][0].resource_key == "source"
    assert legacy == {}


def test_accumulator_ignores_transport_document_event():
    accumulator = RunResourceAccumulator(run_id="run-a")
    grouped = accumulator.capture(
        {"type": "tool_result", "data": {"resources": [_resource()]}},
        turn_sequence=2,
    )
    ignored = accumulator.capture(
        {"type": "office_document", "data": {"file_path": "/tmp/report.html"}},
        turn_sequence=2,
    )
    assert list(grouped) == ["report:current"]
    assert ignored == {}


@pytest.mark.asyncio
async def test_tool_result_publication_returns_durable_change():
    class Service:
        async def publish_group(self, session_id, run_id, group_key, resources, *, turn_sequence=0):
            stored = StoredResource.from_declaration(
                session_id,
                run_id,
                "group-id",
                1,
                resources[0],
                turn_sequence=turn_sequence,
            )
            return type(
                "Result",
                (),
                {"catalog_version": 4, "resources": [stored]},
            )()

    result = await persist_tool_result_resources(
        Service(),
        "session-a",
        "run-a",
        {"type": "tool_result", "data": {"resources": [_resource()]}},
        turn_sequence=1,
    )
    assert result.catalog_version == 4
    assert len(result.changed_resource_ids) == 1


@pytest.mark.asyncio
async def test_publish_session_file_requests_frontend_focus():
    class Service:
        async def publish_group(self, session_id, run_id, group_key, resources, *, turn_sequence=0):
            stored = StoredResource.from_declaration(
                session_id,
                run_id,
                "group-id",
                1,
                resources[0],
                turn_sequence=turn_sequence,
            )
            return type("Result", (), {"catalog_version": 5, "resources": [stored]})()

    result = await persist_tool_result_resources(
        Service(),
        "session-a",
        "run-a",
        {
            "type": "tool_result",
            "data": {
                "tool_name": "publish_session_file",
                "result": {"success": True, "resources": [_resource()]},
            },
        },
        turn_sequence=1,
    )

    assert result.focus_resource_id == result.changed_resource_ids[0]
    event = result.changed_event("session-a", "run-a")
    assert event["data"]["focus_resource_id"] == result.changed_resource_ids[0]


@pytest.mark.asyncio
async def test_durably_tracked_publish_session_file_keeps_focus_intent():
    result = await persist_tool_result_resources(
        object(),
        "session-a",
        "run-a",
        {
            "type": "tool_result",
            "data": {
                "tool_name": "publish_session_file",
                "result": {
                    "success": True,
                    "resource_tracking": {
                        "durable": True,
                        "version": 7,
                        "resource_ids": ["primary-id", "preview-id"],
                    },
                },
            },
        },
        turn_sequence=1,
    )

    assert result.catalog_version == 7
    assert result.focus_resource_id == "primary-id"


@pytest.mark.asyncio
async def test_durably_tracked_visual_requests_frontend_focus():
    result = await persist_tool_result_resources(
        object(),
        "session-a",
        "run-a",
        {
            "type": "tool_result",
            "data": {
                "tool_name": "execute_python",
                "result": {
                    "success": True,
                    "visuals": [{"id": "chart-id", "type": "image"}],
                    "resource_tracking": {
                        "durable": True,
                        "version": 8,
                        "resource_ids": ["chart-resource", "image-resource"],
                    },
                },
            },
        },
        turn_sequence=1,
    )

    assert result.focus_resource_id == "chart-resource"


def test_malformed_iteration_falls_back_to_zero():
    assert event_turn_sequence({"iteration": "not-a-number"}) == 0


@pytest.mark.asyncio
async def test_executor_persists_resources_before_returning_result(tmp_path):
    preview = tmp_path / "previews"
    preview.mkdir()
    generated = preview / "page-001.png"
    generated.write_bytes(b"png")

    async def tool(**_):
        return {
            "success": True,
            "data": {"preview_dir": str(preview)},
            "resources": [
                primary_file(
                    generated,
                    group_key="render:preview",
                    tool_name="render",
                    renderer="image",
                    capabilities=("preview", "download"),
                )
            ],
        }

    service = SessionResourceService.in_memory()
    executor = ToolExecutor(tool_registry={"render": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-a")
    context_builder = SimpleNamespace(session_resource_context="")
    executor.configure_resource_tracking(
        service=service,
        context_builder=context_builder,
        query="preview",
    )
    executor.resource_run_id = "run-a"
    from app.agent.runtime.ownership import run_ownership_registry
    await run_ownership_registry.register("session-a", "run-a")

    result = await executor.execute_tool("render", {}, iteration=3)
    page = await service.list_resources("session-a")

    assert result["resource_tracking"]["durable"] is True
    assert page.resources[0].locator["path"] == str(generated.resolve())
    assert page.resources[0].turn_sequence == 3
    assert f"path={generated.resolve()}" in context_builder.session_resource_context
    await run_ownership_registry.complete("session-a", "run-a")


@pytest.mark.asyncio
async def test_executor_does_not_report_success_when_resource_publication_fails(tmp_path):
    generated = tmp_path / "page.html"
    generated.write_text("<h1>page</h1>", encoding="utf-8")

    async def tool(**_):
        declaration = primary_file(
            generated,
            group_key="html-artifact:broken",
            tool_name="create_html_artifact",
            renderer="html",
            capabilities=("preview", "download"),
        )
        return {"success": True, "resources": [declaration, dict(declaration)]}

    executor = ToolExecutor(tool_registry={"create_html_artifact": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-broken")
    executor.configure_resource_tracking(
        service=SessionResourceService.in_memory(),
        context_builder=SimpleNamespace(session_resource_context=""),
    )

    result = await executor.execute_tool("create_html_artifact", {}, iteration=1)

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error"] == "resource_persistence_failed"
    assert "资源发布失败" in result["summary"]


@pytest.mark.asyncio
async def test_executor_rejects_resources_from_superseded_run(tmp_path):
    generated = tmp_path / "stale.txt"
    generated.write_text("stale", encoding="utf-8")

    async def tool(**_):
        return {
            "success": True,
            "resources": [
                primary_file(
                    generated,
                    group_key="file:stale",
                    tool_name="write_file",
                )
            ],
        }

    from app.agent.runtime.ownership import run_ownership_registry

    service = SessionResourceService.in_memory()
    executor = ToolExecutor(tool_registry={"write_file": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-stale")
    executor.configure_resource_tracking(
        service=service,
        context_builder=SimpleNamespace(session_resource_context=""),
    )
    executor.resource_run_id = "run-old"
    await run_ownership_registry.register("session-stale", "run-old")
    await run_ownership_registry.register("session-stale", "run-new")

    result = await executor.execute_tool("write_file", {}, iteration=1)

    assert result["resource_tracking"] == {
        "durable": False,
        "rejected": ["stale_run_write_skipped"],
    }
    assert (await service.list_resources("session-stale")).resources == []
    await run_ownership_registry.complete("session-stale", "run-new")


@pytest.mark.asyncio
async def test_ownership_transition_waits_for_resource_commit(tmp_path):
    generated = tmp_path / "linearized.txt"
    generated.write_text("content", encoding="utf-8")
    commit_started = asyncio.Event()
    allow_commit = asyncio.Event()

    class BlockingService:
        async def publish_group(self, *_args, **_kwargs):
            commit_started.set()
            await allow_commit.wait()
            return SimpleNamespace(
                catalog_version=1,
                resources=[SimpleNamespace(resource_id="resource-a")],
            )

    async def tool(**_):
        return {
            "success": True,
            "resources": [
                primary_file(
                    generated,
                    group_key="file:linearized",
                    tool_name="write_file",
                )
            ],
        }

    from app.agent.runtime.ownership import run_ownership_registry

    executor = ToolExecutor(tool_registry={"write_file": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-linearized")
    executor.configure_resource_tracking(
        service=BlockingService(),
        context_builder=None,
    )
    executor.resource_run_id = "run-old"
    await run_ownership_registry.register("session-linearized", "run-old")

    execution = asyncio.create_task(executor.execute_tool("write_file", {}, iteration=1))
    await commit_started.wait()
    ownership_change = asyncio.create_task(
        run_ownership_registry.register("session-linearized", "run-new")
    )
    await asyncio.sleep(0)
    assert not ownership_change.done()

    allow_commit.set()
    result = await execution
    await ownership_change

    assert result["resource_tracking"]["durable"] is True
    assert await run_ownership_registry.current_run_id("session-linearized") == "run-new"
    await run_ownership_registry.complete("session-linearized", "run-new")


@pytest.mark.asyncio
async def test_executor_does_not_guess_outputs_from_result_fields(tmp_path):
    generated = tmp_path / "generated.txt"
    generated.write_text("content", encoding="utf-8")

    async def tool(**_):
        return {
            "success": True,
            "data": {
                "file_path": str(generated),
                "files": [str(generated)],
                "preview_dir": str(tmp_path),
            },
        }

    service = SessionResourceService.in_memory()
    executor = ToolExecutor(tool_registry={"bulk_result": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-a")
    executor.configure_resource_tracking(
        service=service,
        context_builder=SimpleNamespace(session_resource_context=""),
    )

    result = await executor.execute_tool("bulk_result", {}, iteration=1)
    page = await service.list_resources("session-a")

    assert "resource_tracking" not in result
    assert page.resources == []


@pytest.mark.asyncio
async def test_executor_declares_files_created_by_save_data_api(tmp_path, monkeypatch):
    from config.settings import settings

    data_root = tmp_path / "data-root"
    data_root.mkdir()
    data_file = data_root / "analysis.json"
    data_file.write_text('[{"value": 1}]', encoding="utf-8")
    monkeypatch.setattr(settings, "data_registry_dir", str(data_root))

    async def tool(**_):
        return {"success": True, "data": {"count": 2}}

    service = SessionResourceService.in_memory()
    executor = ToolExecutor(tool_registry={"analysis": tool})
    executor.memory_manager = SimpleNamespace(session_id="session-a")
    executor._create_execution_context = lambda _iteration: SimpleNamespace(
        available_file_paths=[str(data_file)]
    )
    executor.configure_resource_tracking(
        service=service,
        context_builder=SimpleNamespace(session_resource_context=""),
    )

    result = await executor.execute_tool("analysis", {}, iteration=2)
    page = await service.list_resources("session-a")

    assert result["resources"][0]["locator"]["path"] == str(data_file)
    assert page.resources[0].locator["path"] == str(data_file)


@pytest.mark.asyncio
async def test_read_file_does_not_echo_text_source_path(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("# Notes\nbody\n", encoding="utf-8")

    result = await ReadFileTool().execute(path=str(source))

    assert result["success"] is True
    assert "path" not in result["data"]
    assert "file_path" not in result["data"].get("markdown_preview", {})
    assert "refs" not in result
    assert str(source) not in result.get("llm_resume", {}).get("tool_hint", "")


@pytest.mark.asyncio
async def test_read_file_keeps_runtime_multimodal_attachment_path(tmp_path):
    source = tmp_path / "pixel.png"
    source.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    )

    result = await ReadFileTool().execute(
        path=str(source), as_multimodal_attachment=True
    )

    assert result["attachments"][0]["local_path"] == str(source)


def test_read_file_resolves_current_project_data_registry_from_backend_root():
    tool = ReadFileTool()
    relative_path = "backend_data_registry/xuchang_attainment_predictions/annual/latest.json"
    expected_path = (BACKEND_ROOT / relative_path).resolve()

    assert tool._resolve_path(relative_path) == expected_path
    assert tool._resolve_path(str(expected_path)) == expected_path
    assert tool._resolve_path(str(Path("/etc/passwd"))) is None


def _stored(declaration: ResourceDeclaration) -> StoredResource:
    return StoredResource.from_declaration("session", "run", "group", 1, declaration)


def _file_declaration(path: Path, **updates) -> ResourceDeclaration:
    values = {
        "kind": ResourceKind.FILE,
        "group_key": "test:resource",
        "resource_key": "source",
        "label": path.name,
        "locator": ResourceLocator(path=str(path)),
        "format": path.suffix.lstrip(".") or "file",
        "media_type": "application/octet-stream",
    }
    values.update(updates)
    return ResourceDeclaration(**values)


def test_agent_resource_map_is_bounded_and_includes_actionable_path(tmp_path):
    path = str((tmp_path / "secret.txt").resolve())
    (tmp_path / "secret.txt").write_text("content", encoding="utf-8")
    declaration = _file_declaration(
        Path(path),
        metadata={"summary": "short note", "mime_type": "text/plain"},
    )
    stored = _stored(declaration)
    projected = project_agent_resource_map([stored], max_chars=500)

    assert stored.resource_id in projected
    assert f"path={path}" in projected
    assert len(projected) <= 500


def test_agent_resource_map_uses_canonical_absolute_paths():
    source = Path(__file__).resolve()
    declaration = _file_declaration(
        source,
        metadata={"mime_type": "text/x-python"},
    )
    stored = _stored(declaration)

    projected = project_agent_resource_map([stored])

    assert f"path={source}" in projected


def test_agent_resource_map_collapses_same_locator_but_reports_all_roles(tmp_path):
    source = tmp_path / "reference.png"
    source.write_bytes(b"png")
    declarations = [
        _file_declaration(
            source,
            group_key="test:upload",
            resource_key="upload",
            role=ResourceRole.ATTACHMENT,
            label="original-name.svg",
        ),
        _file_declaration(
            source,
            group_key="test:read",
            resource_key="read",
            role=ResourceRole.SOURCE,
            label="reference.png",
        ),
    ]
    stored = [_stored(item) for item in declarations]

    projected = project_agent_resource_map(stored)

    assert projected.count(f"path={source}") == 1
    assert "roles=attachment,source" in projected


def test_agent_resource_map_hides_legacy_bulk_discovery_rows(tmp_path):
    directory = tmp_path / "runtime"
    directory.mkdir()
    declaration = _file_declaration(
        directory,
        role=ResourceRole.SOURCE,
        tool_name="list_directory",
    )
    stored = _stored(declaration)

    assert project_agent_resource_map([stored]) == ""


def test_ppt_validation_outputs_use_stable_slots_for_same_deck(tmp_path):
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"pptx")
    qa_dir = tmp_path / "qa"
    qa_dir.mkdir()
    first = qa_dir / "montage.png"
    first.write_bytes(b"first")

    slot = __import__("hashlib").sha256(str(pptx).encode("utf-8")).hexdigest()[:16]
    resource = validation_output_resources(pptx, [first])[0]

    assert resource["group_key"] == f"presentation:{slot}"
    assert resource["resource_key"] == "pptx"


@pytest.mark.asyncio
async def test_new_ppt_validation_output_replaces_previous_qa_path(tmp_path):
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"pptx")
    first = tmp_path / "qa-1" / "montage.png"
    second = tmp_path / "qa-2" / "montage.png"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    service = SessionResourceService.in_memory()

    first_declarations = [
        ResourceDeclaration.model_validate(item)
        for item in validation_output_resources(pptx, [first])
    ]
    second_declarations = [
        ResourceDeclaration.model_validate(item)
        for item in validation_output_resources(pptx, [second])
    ]
    await service.publish_group(
        "session",
        "run-1",
        first_declarations[0].group_key,
        first_declarations,
    )
    await service.publish_group(
        "session",
        "run-2",
        second_declarations[0].group_key,
        second_declarations,
    )

    page = await service.list_resources("session")
    montage = next(item for item in page.resources if item.resource_key == "montage")
    assert montage.locator["path"] == str(second.resolve())
    assert {item.version for item in page.resources} == {2}


@pytest.mark.asyncio
async def test_explicit_build_directory_can_be_listed(tmp_path):
    build = tmp_path / "build" / "preview"
    build.mkdir(parents=True)
    (build / "page-001.png").write_bytes(b"png")
    tool = ListDirectoryTool()
    tool.allowed_dirs.append(tmp_path)

    result = await tool.execute(str(build))

    assert result["success"] is True
    assert [item["name"] for item in result["data"]["entries"]] == ["page-001.png"]


@pytest.mark.asyncio
async def test_session_resource_can_be_read_without_exposing_path_in_prompt(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("resource content", encoding="utf-8")
    service = SessionResourceService.in_memory()
    declaration = _file_declaration(source)
    stored = (
        await service.publish_group(
            "session-a", "run-a", declaration.group_key, [declaration]
        )
    ).resources[0]

    result = await ReadSessionResourceTool(service=service).execute(
        context=SimpleNamespace(session_id="session-a"),
        resource_id=stored.resource_id,
    )

    assert result["success"] is True
    assert "resource content" in str(result["data"])
