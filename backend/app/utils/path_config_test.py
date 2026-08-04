from pathlib import Path

import pytest

from app.tools.office.generate_random_doc_tool import GenerateRandomDocTool
from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool
from app.tools.office.read_pptx_tool import ReadPptxTool
from app.tools.office.validate_pptx_tool import ValidatePptxTool
from app.tools.utility import bash_tool, edit_file_tool_v2, glob_tool, list_directory_tool
from app.tools.utility import grep_tool, publish_session_file_tool, read_file_tool, write_file_tool
from app.utils import path_config


def test_agent_relative_and_absolute_path_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    assert path_config.resolve_agent_path("backend/backend_data_registry/uploads/a.png") == (
        tmp_path / "backend/backend_data_registry/uploads/a.png"
    ).resolve()
    absolute = tmp_path / "elsewhere" / "b.png"
    assert path_config.resolve_agent_path(absolute) == absolute.resolve()


def test_agent_path_contract_rejects_blank_and_detects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ValueError, match="path is required"):
        path_config.resolve_agent_path("  ")
    assert path_config.is_path_within(tmp_path / "inside.txt", [tmp_path])
    assert not path_config.is_path_within(tmp_path.parent / "outside.txt", [tmp_path])


def test_core_file_tools_delegate_relative_paths_to_shared_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    expected = (tmp_path / "outputs/report.txt").resolve()
    tools = [
        read_file_tool.ReadFileTool(),
        write_file_tool.WriteFileTool(),
        edit_file_tool_v2.EditFileToolV2(),
        list_directory_tool.ListDirectoryTool(),
        glob_tool.GlobTool(),
        publish_session_file_tool.PublishSessionFileTool(),
    ]
    for tool in tools:
        tool.allowed_dirs = [tmp_path]
        if hasattr(tool, "allowed_extra_paths"):
            tool.working_dir = tmp_path
        assert tool._resolve_path("outputs/report.txt") == expected


def test_bash_working_directory_uses_project_relative_contract(tmp_path, monkeypatch):
    target = tmp_path / "backend" / "jobs"
    target.mkdir(parents=True)
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    tool = bash_tool.BashTool()
    assert tool._resolve_working_dir("backend/jobs") == target.resolve()


def test_office_agent_paths_do_not_depend_on_process_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    expected = (tmp_path / "deliverables/deck.pptx").resolve()
    assert ReadPptxTool()._resolve_path("deliverables/deck.pptx") == expected
    assert ValidatePptxTool()._resolve_path("deliverables/deck.pptx") == expected
    assert GenerateRandomDocTool()._resolve_path("deliverables/deck.pptx") == expected
    assert CreatePptxWithPptMasterTool()._resolve_output_file(
        "deliverables/deck.pptx", "ignored"
    ) == expected


def test_backend_output_paths_keep_backend_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    backend_file = tmp_path / "backend/backend_data_registry/uploads/a.png"
    frontend_file = tmp_path / "frontend/dist/index.html"
    external_file = tmp_path.parent / "external.txt"

    assert path_config.format_agent_path(backend_file) == (
        "backend/backend_data_registry/uploads/a.png"
    )
    assert path_config.format_agent_path(frontend_file) == "frontend/dist/index.html"
    assert path_config.format_agent_path(external_file) == str(external_file.resolve())


@pytest.mark.asyncio
async def test_file_listing_tools_emit_project_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    backend_dir = tmp_path / "backend/outputs"
    backend_dir.mkdir(parents=True)
    backend_file = backend_dir / "report.txt"
    backend_file.write_text("result", encoding="utf-8")

    glob = glob_tool.GlobTool()
    glob.working_dir = tmp_path
    glob.allowed_dirs = [tmp_path]
    result = await glob.execute("*.txt", path="backend/outputs", sort_by_time=False)
    assert result["data"]["files"] == ["backend/outputs/report.txt"]

    listing = list_directory_tool.ListDirectoryTool()
    listing.working_dir = tmp_path
    listing.allowed_dirs = [tmp_path]
    assert listing._create_entry(backend_file, backend_dir)["path"] == (
        "backend/outputs/report.txt"
    )

    assert grep_tool.GrepTool()._to_rel_path(str(backend_file)) == (
        "backend/outputs/report.txt"
    )


def test_production_agent_tools_do_not_reintroduce_cwd_or_install_path_literals():
    tools_root = Path(__file__).resolve().parents[1] / "tools"
    violations = []
    for source in tools_root.rglob("*.py"):
        relative = source.relative_to(tools_root)
        if (
            "examples" in relative.parts
            or source.name.endswith(("_test.py", "_spec.py"))
            or source.name.startswith("test_")
        ):
            continue
        text = source.read_text(encoding="utf-8")
        if "Path.cwd()" in text or "/home/xckj/suyuan" in text:
            violations.append(relative.as_posix())
    assert violations == []
