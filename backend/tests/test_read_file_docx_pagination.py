from docx import Document
import pytest

from app.tools.utility.read_file_tool import ReadFileTool


@pytest.fixture
def five_paragraph_docx(tmp_path, monkeypatch):
    file_path = tmp_path / "five-paragraphs.docx"
    document = Document()
    for number in range(1, 6):
        document.add_paragraph(f"Paragraph {number}")
    document.save(file_path)

    monkeypatch.setattr(
        "app.tools.report.read_docx.tool.get_pdf_converter",
        lambda: None,
    )
    return file_path


def _tool_for(file_path):
    tool = ReadFileTool()
    tool.allowed_dirs.append(file_path.parent)
    return tool


@pytest.mark.asyncio
async def test_docx_reads_requested_paragraph_page(five_paragraph_docx):
    result = await _tool_for(five_paragraph_docx).execute(
        path=str(five_paragraph_docx),
        offset=1,
        limit=2,
        enable_preview=False,
    )

    assert result["success"] is True
    assert result["data"]["content"] == "Paragraph 2\n\nParagraph 3"
    assert result["data"]["offset"] == 1
    assert result["data"]["limit"] == 2
    assert result["data"]["next_offset"] == 3
    assert result["data"]["is_truncated"] is True
    assert result["data"]["total_paragraphs"] == 5


@pytest.mark.asyncio
async def test_docx_tail_page_has_no_next_offset(five_paragraph_docx):
    result = await _tool_for(five_paragraph_docx).execute(
        path=str(five_paragraph_docx),
        offset=4,
        limit=2,
        enable_preview=False,
    )

    assert result["success"] is True
    assert result["data"]["content"] == "Paragraph 5"
    assert result["data"]["next_offset"] is None
    assert result["data"]["is_truncated"] is False
    assert result["data"]["total_paragraphs"] == 5


@pytest.mark.asyncio
async def test_docx_offset_at_end_returns_empty_page(five_paragraph_docx):
    result = await _tool_for(five_paragraph_docx).execute(
        path=str(five_paragraph_docx),
        offset=5,
        limit=2,
        enable_preview=False,
    )

    assert result["success"] is True
    assert result["data"]["content"] == ""
    assert result["data"]["paragraph_count"] == 0
    assert result["data"]["next_offset"] is None
    assert result["data"]["is_truncated"] is False
    assert result["data"]["total_paragraphs"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("offset", "limit"),
    [(-1, 2), (0, 0), (0, -1)],
)
async def test_docx_rejects_invalid_pagination(
    five_paragraph_docx,
    offset,
    limit,
):
    result = await _tool_for(five_paragraph_docx).execute(
        path=str(five_paragraph_docx),
        offset=offset,
        limit=limit,
        enable_preview=False,
    )

    assert result["success"] is False
    assert "DOCX分页参数无效" in result["summary"]
