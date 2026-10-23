"""read_file 结果可见性与重复读取去重测试。

对齐 ZCode Read 工具的三个机制：
1. file_unchanged：相同 (offset, limit) 且文件未变化的重复读取返回零正文存根，
   避免模型在结果被会话层降级为预览后反复重读（实测单会话重读同一文件 121 次）。
2. 分页读取的 metadata.read_state 回显不再携带正文：会话恢复只接受完整读取
   （restore_read_state_from_history），分页正文回显与 data.content 重复，
   会把结果体积翻倍推过 24KB 降级悬崖。
3. 预览诚实化：content_preview 只有 2000 字符，当请求范围超出预览可容纳的
   行数时，summary/tool_hint 必须给出模型实际可见的行范围与续读 offset，
   而不是虚报"已返回全部请求行"。
"""
import asyncio
import os

import pytest

from app.tools.utility.file_read_state import reset_file_read_state
from app.tools.utility.read_file_tool import ReadFileTool


@pytest.fixture(autouse=True)
def _clean_read_state():
    reset_file_read_state()
    yield
    reset_file_read_state()


def _make_tool(tmp_path):
    tool = ReadFileTool()
    tool.allowed_dirs.append(tmp_path)
    return tool


@pytest.mark.asyncio
async def test_repeated_read_same_range_returns_unchanged_stub(tmp_path):
    file_path = tmp_path / "svc.py"
    file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    first = await tool.execute(path=str(file_path), offset=0, limit=2, encoding="utf-8")
    assert first["success"] is True
    assert first["data"]["content"] == "alpha\nbeta"

    second = await tool.execute(path=str(file_path), offset=0, limit=2, encoding="utf-8")
    assert second["success"] is True
    assert second["data"]["file_unchanged"] is True
    assert "content" not in second["data"]
    assert "第1-2行" in second["summary"]
    assert "上一次" in second["summary"]


@pytest.mark.asyncio
async def test_read_different_offset_bypasses_unchanged_stub(tmp_path):
    file_path = tmp_path / "svc.py"
    file_path.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    await tool.execute(path=str(file_path), offset=0, limit=2, encoding="utf-8")
    second = await tool.execute(path=str(file_path), offset=2, limit=2, encoding="utf-8")

    assert second["success"] is True
    assert "file_unchanged" not in second["data"]
    assert second["data"]["content"] == "gamma\ndelta"


@pytest.mark.asyncio
async def test_modified_file_bypasses_unchanged_stub(tmp_path):
    file_path = tmp_path / "svc.py"
    file_path.write_text("alpha\nbeta\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    await tool.execute(path=str(file_path), offset=0, limit=5, encoding="utf-8")
    os.utime(file_path, ns=(0, 0))
    file_path.write_text("alpha\nbeta\nNEW LINE\n", encoding="utf-8")

    second = await tool.execute(path=str(file_path), offset=0, limit=5, encoding="utf-8")
    assert second["success"] is True
    assert "file_unchanged" not in second["data"]
    assert "NEW LINE" in second["data"]["content"]


@pytest.mark.asyncio
async def test_paged_read_read_state_echo_has_no_content(tmp_path):
    file_path = tmp_path / "svc.py"
    file_path.write_text("l1\nl2\nl3\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    result = await tool.execute(path=str(file_path), offset=1, limit=1, encoding="utf-8")

    echo = result["metadata"]["read_state"]
    assert echo["is_partial_view"] is True
    assert echo["content"] == ""
    assert result["data"]["content"] == "l2"


@pytest.mark.asyncio
async def test_full_read_read_state_echo_keeps_content_for_edit_restore(tmp_path):
    file_path = tmp_path / "svc.py"
    file_path.write_text("l1\nl2\nl3\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    result = await tool.execute(path=str(file_path), encoding="utf-8")

    echo = result["metadata"]["read_state"]
    assert echo["is_partial_view"] is False
    assert echo["content"] == "l1\nl2\nl3\n"


@pytest.mark.asyncio
async def test_preview_clipped_reports_visible_range_and_next_offset(tmp_path):
    # 3 行超长行：2000 字符预览装不下 3 行，模型实际只看得见前几行
    long_line = "x" * 1500
    file_path = tmp_path / "wide.py"
    file_path.write_text(f"{long_line}\n{long_line}\n{long_line}\n", encoding="utf-8")
    tool = _make_tool(tmp_path)

    result = await tool.execute(path=str(file_path), offset=0, limit=3, encoding="utf-8")

    assert result["success"] is True
    data = result["data"]
    assert data["line_range"] == [1, 3]
    visible = data["visible_line_range"]
    assert visible[1] < 3  # 预览只容纳了部分行

    hint = result["llm_resume"]["tool_hint"]
    assert f"仅展示第1-{visible[1]}行" in hint
    # read_file 的 offset 是 0 起始行号：1-based 末行号 N 的续读 offset 就是 N
    assert f"offset={visible[1]}," in hint

    assert f"仅向模型展示第 1-{visible[1]} 行" in result["summary"]
