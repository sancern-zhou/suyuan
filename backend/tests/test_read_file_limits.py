import pytest

from app.tools.utility.edit_file_tool_v2 import EditFileToolV2
from app.tools.utility.file_read_state import get_file_read_state
from app.tools.utility.read_file_tool import ReadFileTool


@pytest.fixture(autouse=True)
def clear_read_state():
    state = get_file_read_state()
    state.clear()
    yield
    state.clear()


@pytest.mark.asyncio
async def test_read_text_rejects_large_file_without_limit(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    tool = ReadFileTool()
    tool.allowed_dirs.append(tmp_path)

    result = await tool.execute(
        path=str(file_path),
        max_size=10,
        encoding="utf-8",
    )

    assert result["success"] is False
    assert "超过最大允许大小" in result["data"]["error"]
    assert "offset=0,limit=1000" in result["summary"]
    assert "content" not in result["data"]


@pytest.mark.asyncio
async def test_read_text_allows_large_file_when_limit_is_explicit(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("line 1\nline 2\nline 3\nline 4\n", encoding="utf-8")

    tool = ReadFileTool()
    tool.allowed_dirs.append(tmp_path)

    result = await tool.execute(
        path=str(file_path),
        offset=1,
        limit=2,
        max_size=10,
        encoding="utf-8",
    )

    assert result["success"] is True
    assert result["data"]["content"] == "line 2\nline 3"
    assert result["data"]["line_range"] == [2, 3]
    assert result["data"]["total_lines"] == 4
    assert result["data"]["is_truncated"] is True
    assert result["refs"]["files"] == [
        {
            "path": str(file_path),
            "type": "text",
            "format": "txt",
            "size": file_path.stat().st_size,
            "line_range": [2, 3],
            "total_lines": 4,
            "is_truncated": True,
            "usage": "read_file",
        }
    ]
    assert result["llm_resume"]["content_preview"] == "line 2\nline 3"
    assert result["llm_resume"]["tool_hint"] == (
        f"Use read_file(path='{file_path}', offset=3, limit=2) to continue reading."
    )


@pytest.mark.asyncio
async def test_edit_allows_old_string_from_partial_read(tmp_path):
    file_path = tmp_path / "partial_edit.txt"
    file_path.write_text(
        "line 1\nline 2\ntarget line\nline 4\nunread target\n",
        encoding="utf-8",
    )

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)
    edit_tool = EditFileToolV2()
    edit_tool.working_dir = tmp_path

    read_result = await read_tool.execute(
        path=str(file_path),
        offset=1,
        limit=3,
        encoding="utf-8",
    )
    assert read_result["success"] is True
    assert read_result["data"]["is_truncated"] is True

    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string="target line",
        new_string="updated line",
        encoding="utf-8",
    )

    assert edit_result["success"] is True
    assert "updated line" in file_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_rejects_old_string_outside_partial_read(tmp_path):
    file_path = tmp_path / "partial_edit.txt"
    file_path.write_text(
        "line 1\nline 2\ntarget line\nline 4\nunread target\n",
        encoding="utf-8",
    )

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)
    edit_tool = EditFileToolV2()
    edit_tool.working_dir = tmp_path

    read_result = await read_tool.execute(
        path=str(file_path),
        offset=0,
        limit=2,
        encoding="utf-8",
    )
    assert read_result["success"] is True

    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string="unread target",
        new_string="updated target",
        encoding="utf-8",
    )

    assert edit_result["success"] is False
    assert "old_string 不在已读取片段中" in edit_result["summary"]
    assert "unread target" in file_path.read_text(encoding="utf-8")
