import tempfile
from pathlib import Path

import pytest

from app.tools.utility.edit_file_tool_v2 import EditFileToolV2
from app.tools.utility.file_read_state import reset_file_read_state


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
