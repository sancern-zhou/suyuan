"""validate_office 工具测试：xlsx 读回校验直跑；docx 结构检查（渲染链 mock）。"""
from pathlib import Path

import pytest

from app.tools.office.validate_office_tool import ValidateOfficeTool


@pytest.fixture
def tool():
    return ValidateOfficeTool()


def _write_xlsx(path: Path, sheets: dict):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title=title)
        for row in rows:
            sheet.append(row)
    workbook.save(path)
    return path


@pytest.mark.asyncio
async def test_good_xlsx_passes_gate(tool, tmp_path):
    path = _write_xlsx(tmp_path / "good.xlsx", {"站点明细": [["站点", "浓度"], ["图书馆", 34.2]]})

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    assert result["success"] is True
    assert result["data"]["gate"]["status"] == "passed"
    assert result["data"]["structured_issues"] == []


@pytest.mark.asyncio
async def test_xlsx_error_values_are_blocking(tool, tmp_path):
    path = _write_xlsx(tmp_path / "bad.xlsx", {"明细": [["站点", "均值"], ["A站", "#REF!"], ["B站", "#DIV/0!"]]})

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert "xlsx_error_value" in issues
    assert result["data"]["gate"]["status"] == "needs_revision"
    assert result["data"]["gate"]["blocking"] is True


@pytest.mark.asyncio
async def test_xlsx_empty_sheet_and_missing_freeze(tool, tmp_path):
    # 明细 16 行数据触发冻结窗格检查；"空表" 触发 empty_sheet
    rows = [["站点", "值"]] + [[f"站点{i:02d}", i] for i in range(16)]
    path = _write_xlsx(tmp_path / "mixed.xlsx", {"明细": rows, "空表": []})

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert "xlsx_empty_sheet" in issues
    assert "xlsx_no_freeze_panes" in issues


@pytest.mark.asyncio
async def test_xlsx_column_overflow_with_default_width(tool, tmp_path):
    long_text = "超长站点名称" * 6  # 显示宽 36 > 20，且未设列宽（默认 8.43）
    path = _write_xlsx(tmp_path / "wide.xlsx", {"明细": [["站点", "备注"], ["A", long_text]]})

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert "xlsx_column_overflow" in issues


def _write_docx(path: Path, blocks):
    from docx import Document

    doc = Document()
    for kind, value in blocks:
        if kind == "heading":
            doc.add_heading(value, level=1)
        elif kind == "heading3":
            doc.add_heading(value, level=3)
        else:
            doc.add_paragraph(value)
    doc.save(path)
    return path


@pytest.mark.asyncio
async def test_docx_no_heading_is_flagged(tool, tmp_path, monkeypatch):
    def _no_render(self, file_path, qa_dir, dpi):
        raise RuntimeError("soffice unavailable in test")

    monkeypatch.setattr(ValidateOfficeTool, "_render_docx", _no_render)
    path = _write_docx(tmp_path / "plain.docx", [("para", "正文内容" * 10)])

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert "docx_no_heading" in issues
    # 渲染不可用 + 结构问题 → needs_revision（存在非运行时类问题）
    assert result["data"]["gate"]["status"] == "needs_revision"


@pytest.mark.asyncio
async def test_docx_heading_level_jump_is_flagged(tool, tmp_path, monkeypatch):
    def _no_render(self, file_path, qa_dir, dpi):
        raise RuntimeError("soffice unavailable in test")

    monkeypatch.setattr(ValidateOfficeTool, "_render_docx", _no_render)
    path = _write_docx(
        tmp_path / "jump.docx",
        [("heading", "第一章"), ("heading3", "小节（跳级 H1→H3）"), ("para", "正文")],
    )

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert "docx_heading_level_jump" in issues


@pytest.mark.asyncio
async def test_docx_render_failure_alone_is_qa_failed(tool, tmp_path, monkeypatch):
    def _no_render(self, file_path, qa_dir, dpi):
        raise RuntimeError("soffice unavailable in test")

    monkeypatch.setattr(ValidateOfficeTool, "_render_docx", _no_render)
    path = _write_docx(
        tmp_path / "ok.docx", [("heading", "标题"), ("para", "正文内容" * 5)]
    )

    result = await tool.execute(path=str(path), output_dir=str(tmp_path / "qa"))

    issues = {i["type"] for i in result["data"]["structured_issues"]}
    assert issues == {"rendered_qa_unavailable"}
    assert result["data"]["gate"]["status"] == "qa_failed"


@pytest.mark.asyncio
async def test_unsupported_suffix_is_rejected(tool, tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("x", encoding="utf-8")

    result = await tool.execute(path=str(path))

    assert result["success"] is False
    assert "只支持" in result["data"]["error"]
