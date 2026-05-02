import pytest

from app.tools.utility.read_file_tool import ReadFileTool


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
