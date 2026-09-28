import tempfile
from pathlib import Path

import pytest

from app.tools.utility.edit_file_tool_v2 import EditFileToolV2
from app.tools.utility.file_read_state import reset_file_read_state
from app.tools.utility import edit_file_tool_v2, read_file_tool
from app.utils import path_config


@pytest.fixture
def external_registry(tmp_path, monkeypatch):
    backend = tmp_path / "checkout" / "backend"
    registry = tmp_path / "persistent-data"
    monkeypatch.setattr(path_config, "PROJECT_ROOT", backend.parent)
    monkeypatch.setattr(path_config, "BACKEND_ROOT", backend)
    monkeypatch.setattr(edit_file_tool_v2, "BACKEND_ROOT", backend)
    monkeypatch.setattr(read_file_tool, "PROJECT_ROOT", backend.parent)
    for module in (edit_file_tool_v2, read_file_tool):
        monkeypatch.setattr(module, "get_data_registry", lambda: registry)
        # Do not let the real /tmp permission mask the external-registry case.
        monkeypatch.setattr(module, "TEMP_ROOT", tmp_path / "tool-temp")
    registry.mkdir()
    reset_file_read_state()
    yield registry
    reset_file_read_state()


@pytest.mark.asyncio
async def test_edit_external_memory_after_read(external_registry):
    path = external_registry / "memory" / "assistant" / "MEMORY.md"
    path.parent.mkdir(parents=True)
    path.write_text("original requirement\n", encoding="utf-8")
    tool = EditFileToolV2()

    unread = await tool.execute(
        path=str(path), old_string="original", new_string="revised"
    )
    assert unread["success"] is False
    assert "read_file" in unread["error"]

    read = await read_file_tool.ReadFileTool().execute(path=str(path))
    assert read["success"] is True
    result = await tool.execute(
        path=str(path), old_string="original", new_string="revised"
    )
    assert result["success"] is True
    assert path.read_text(encoding="utf-8") == "revised requirement\n"


def test_external_registry_keeps_path_protections(external_registry):
    tool = EditFileToolV2()
    assert tool._resolve_path(str(external_registry / ".env")) is None
    assert tool._resolve_path(str(path_config.BACKEND_ROOT / "app/main.py")) is None
    outside = external_registry.parent / "persistent-data-other" / "MEMORY.md"
    outside.parent.mkdir()
    outside.write_text("untouched", encoding="utf-8")
    assert tool._resolve_path(str(outside)) is None
    link = external_registry / "escape.md"
    link.symlink_to(outside)
    assert tool._resolve_path(str(link)) is None


@pytest.mark.asyncio
async def test_edit_file_v2_allows_tmp_files_after_read():
    reset_file_read_state()

    with tempfile.TemporaryDirectory(dir="/tmp") as temp_dir:
        path = Path(temp_dir) / "edit-target.txt"
        original = "alpha\nbeta\n"
        path.write_text(original, encoding="utf-8")

        tool = EditFileToolV2()
        resolved_path = path.resolve()
        tool.read_state.set(
            str(resolved_path),
            content=original,
            file_size=len(original),
            encoding="utf-8",
        )

        result = await tool.execute(
            path=str(resolved_path),
            old_string="beta",
            new_string="gamma",
        )

        assert result["success"] is True
        assert result["data"]["path"] == str(resolved_path)
        assert path.read_text(encoding="utf-8") == "alpha\ngamma\n"


@pytest.mark.asyncio
async def test_edit_file_v2_rejects_paths_outside_allowed_dirs():
    reset_file_read_state()
    tool = EditFileToolV2()

    result = await tool.execute(
        path="/etc/hosts",
        old_string="localhost",
        new_string="example",
    )

    assert result["success"] is False
    assert "超出工作目录范围" in result["error"]
