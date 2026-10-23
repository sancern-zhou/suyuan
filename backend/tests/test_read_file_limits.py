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
    # _strip_source_path_echo 会剥离顶层 refs 冗余定位（设计行为）
    assert "refs" not in result
    assert result["llm_resume"]["content_preview"] == "line 2\nline 3"
    assert result["llm_resume"]["tool_hint"] == (
        "Use read_file(offset=3, limit=2) on the same resource to continue reading."
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


@pytest.mark.asyncio
async def test_read_text_reports_empty_file_and_allows_edit(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("", encoding="utf-8")

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)

    result = await read_tool.execute(path=str(file_path), encoding="utf-8")

    assert result["success"] is True
    assert result["data"]["content"] == ""
    assert result["data"]["total_lines"] == 0
    assert "内容为空" in result["data"]["note"]
    assert "内容为空" in result["summary"]

    # 空文件读取后应记录读取状态，模型可直接编辑而无需再读一次
    edit_tool = EditFileToolV2()
    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string="",
        new_string="hello",
        encoding="utf-8",
    )
    assert edit_result["success"] is True
    assert file_path.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_read_text_reports_offset_past_eof(tmp_path):
    file_path = tmp_path / "ten_lines.txt"
    file_path.write_text(
        "".join(f"line {i}\n" for i in range(1, 11)), encoding="utf-8"
    )

    tool = ReadFileTool()
    tool.allowed_dirs.append(tmp_path)

    result = await tool.execute(path=str(file_path), offset=50, encoding="utf-8")

    assert result["success"] is True
    assert result["data"]["content"] == ""
    assert result["data"]["line_range"] == []
    assert "超出文件末尾" in result["data"]["note"]
    assert "读取结果为空" in result["summary"]
    assert "offset=9" in result["summary"]


@pytest.mark.asyncio
async def test_read_missing_file_suggests_similar_names(tmp_path):
    (tmp_path / "station_catalog.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "station_catalog_v2.py").write_text("x = 2\n", encoding="utf-8")

    tool = ReadFileTool()
    tool.allowed_dirs.append(tmp_path)

    result = await tool.execute(
        path=str(tmp_path / "station_catlog.py"), encoding="utf-8"
    )

    assert result["success"] is False
    assert result["data"]["suggestions"], "同目录存在近似文件名时应给出建议"
    assert "station_catalog" in result["summary"]


@pytest.mark.asyncio
async def test_edit_preserves_crlf_line_endings(tmp_path):
    file_path = tmp_path / "windows_style.py"
    file_path.write_bytes('value = 1\r\nname = "old"\r\ntail = True\r\n'.encode("utf-8"))

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)
    read_result = await read_tool.execute(path=str(file_path), encoding="utf-8")
    assert read_result["success"] is True

    edit_tool = EditFileToolV2()
    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string='name = "old"',
        new_string='name = "new"',
        encoding="utf-8",
    )

    assert edit_result["success"] is True
    # 行尾风格保持 CRLF，且只有目标行被修改
    assert file_path.read_bytes() == b'value = 1\r\nname = "new"\r\ntail = True\r\n'
    assert "无需 read_file 重读" in edit_result["summary"]


@pytest.mark.asyncio
async def test_edit_normalizes_crlf_in_model_strings(tmp_path):
    file_path = tmp_path / "multi_line.txt"
    file_path.write_bytes(b"alpha\r\nbeta\r\n")

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)
    read_result = await read_tool.execute(path=str(file_path), encoding="utf-8")
    assert read_result["success"] is True

    edit_tool = EditFileToolV2()
    # 模型把换行写成 \r\n 时也应正常匹配，且写回后文件保持 CRLF
    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string="alpha\r\nbeta",
        new_string="alpha\r\ngamma",
        encoding="utf-8",
    )

    assert edit_result["success"] is True
    assert file_path.read_bytes() == b"alpha\r\ngamma\r\n"


@pytest.mark.asyncio
async def test_edit_keeps_lf_line_endings_unchanged(tmp_path):
    file_path = tmp_path / "unix_style.py"
    file_path.write_bytes(b"value = 1\nname = 'old'\n")

    read_tool = ReadFileTool()
    read_tool.allowed_dirs.append(tmp_path)
    await read_tool.execute(path=str(file_path), encoding="utf-8")

    edit_tool = EditFileToolV2()
    edit_result = await edit_tool.execute(
        path=str(file_path),
        old_string="name = 'old'",
        new_string="name = 'new'",
        encoding="utf-8",
    )

    assert edit_result["success"] is True
    assert file_path.read_bytes() == b"value = 1\nname = 'new'\n"
