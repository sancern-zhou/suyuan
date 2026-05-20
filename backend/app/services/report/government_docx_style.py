"""
Default government-report DOCX styling helpers.

This module keeps report formatting deterministic for both direct
python-docx generation and Quarto/Pandoc DOCX export. User-specific
formatting can still override these defaults in generated code or qmd YAML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


DEFAULT_REFERENCE_DOCX = (
    Path(__file__).resolve().parents[3]
    / "backend_data_registry"
    / "report_templates"
    / "government_report_reference.docx"
)


BODY_FONT = "仿宋_GB2312"
BODY_FONT_FALLBACK = "仿宋"
HEADING_FONT = "黑体"
TITLE_FONT = "方正小标宋_GBK"
TITLE_FONT_FALLBACK = "宋体"
SECOND_LEVEL_FONT = "楷体_GB2312"
SECOND_LEVEL_FONT_FALLBACK = "楷体"

BODY_SIZE_PT = 16
TITLE_SIZE_PT = 22
LINE_SPACING_PT = 28


def set_run_font(
    run,
    font_name: str,
    size_pt: float | None = None,
    bold: bool | None = None,
    color: str | None = None,
) -> None:
    """Set Latin and East Asian font metadata on a run."""
    run.font.name = font_name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def set_paragraph_format(
    paragraph,
    *,
    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    first_line_indent_chars: float = 2,
    line_spacing_pt: float = LINE_SPACING_PT,
    space_before_pt: float = 0,
    space_after_pt: float = 0,
) -> None:
    """Apply common government-report paragraph spacing."""
    fmt = paragraph.paragraph_format
    fmt.alignment = alignment
    fmt.line_spacing = Pt(line_spacing_pt)
    fmt.space_before = Pt(space_before_pt)
    fmt.space_after = Pt(space_after_pt)
    if first_line_indent_chars:
        # Approximate "2 characters" using the current body font size.
        fmt.first_line_indent = Pt(BODY_SIZE_PT * first_line_indent_chars)
    else:
        fmt.first_line_indent = Pt(0)


def _set_style_font(style, font_name: str, size_pt: float, bold: bool = False) -> None:
    style.font.name = font_name
    style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), font_name)
    style.font.size = Pt(size_pt)
    style.font.bold = bold


def _set_style_paragraph(
    style,
    *,
    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    first_line_indent_chars: float = 2,
    line_spacing_pt: float = LINE_SPACING_PT,
    space_before_pt: float = 0,
    space_after_pt: float = 0,
) -> None:
    fmt = style.paragraph_format
    fmt.alignment = alignment
    fmt.line_spacing = Pt(line_spacing_pt)
    fmt.space_before = Pt(space_before_pt)
    fmt.space_after = Pt(space_after_pt)
    if first_line_indent_chars:
        fmt.first_line_indent = Pt(BODY_SIZE_PT * first_line_indent_chars)
    else:
        fmt.first_line_indent = Pt(0)


def _set_table_cell_text(cell, text: str, *, bold: bool = False) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_format(
        paragraph,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        first_line_indent_chars=0,
        line_spacing_pt=20,
        space_before_pt=0,
        space_after_pt=0,
    )
    run = paragraph.add_run(text)
    set_run_font(run, BODY_FONT, 10.5, bold=bold)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)

    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "8")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")


def apply_government_report_style(doc: DocumentObject) -> DocumentObject:
    """
    Apply a default government-report style profile to an existing document.

    Defaults:
    - A4-ish government margins: top 3.7 cm, bottom 3.5 cm, left/right 2.8 cm.
    - Title: centered, 22 pt, 小标宋/宋体 fallback.
    - Body: 仿宋 16 pt, fixed 28 pt line spacing, first-line indent 2 chars.
    - Heading 1: 黑体 16 pt, no first-line indent.
    - Heading 2: 楷体 16 pt, no first-line indent.
    - Heading 3: 仿宋 bold 16 pt, no first-line indent.
    """
    for section in doc.sections:
        section.start_type = WD_SECTION_START.NEW_PAGE
        section.top_margin = Cm(3.7)
        section.bottom_margin = Cm(3.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.8)

    styles = doc.styles

    normal = styles["Normal"]
    _set_style_font(normal, BODY_FONT, BODY_SIZE_PT)
    _set_style_paragraph(normal)

    title = styles["Title"]
    _set_style_font(title, TITLE_FONT, TITLE_SIZE_PT)
    _set_style_paragraph(
        title,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        first_line_indent_chars=0,
        line_spacing_pt=32,
        space_before_pt=0,
        space_after_pt=18,
    )

    heading_1 = styles["Heading 1"]
    _set_style_font(heading_1, HEADING_FONT, BODY_SIZE_PT)
    _set_style_paragraph(
        heading_1,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        first_line_indent_chars=0,
        line_spacing_pt=LINE_SPACING_PT,
        space_before_pt=12,
        space_after_pt=6,
    )

    heading_2 = styles["Heading 2"]
    _set_style_font(heading_2, SECOND_LEVEL_FONT, BODY_SIZE_PT)
    _set_style_paragraph(
        heading_2,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        first_line_indent_chars=0,
        line_spacing_pt=LINE_SPACING_PT,
        space_before_pt=6,
        space_after_pt=6,
    )

    heading_3 = styles["Heading 3"]
    _set_style_font(heading_3, BODY_FONT, BODY_SIZE_PT, bold=True)
    _set_style_paragraph(
        heading_3,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        first_line_indent_chars=0,
        line_spacing_pt=LINE_SPACING_PT,
        space_before_pt=6,
        space_after_pt=6,
    )

    for paragraph in doc.paragraphs:
        if paragraph.style and paragraph.style.name.startswith("Heading"):
            continue
        if paragraph.style and paragraph.style.name == "Title":
            continue
        set_paragraph_format(paragraph)
        for run in paragraph.runs:
            set_run_font(run, BODY_FONT, BODY_SIZE_PT)

    for table in doc.tables:
        format_government_table(table)

    return doc


def add_government_title(doc: DocumentObject, text: str):
    paragraph = doc.add_paragraph(style="Title")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    set_run_font(run, TITLE_FONT, TITLE_SIZE_PT)
    return paragraph


def add_government_paragraph(doc: DocumentObject, text: str = ""):
    paragraph = doc.add_paragraph(text)
    set_paragraph_format(paragraph)
    for run in paragraph.runs:
        set_run_font(run, BODY_FONT, BODY_SIZE_PT)
    return paragraph


def add_government_heading(doc: DocumentObject, text: str, level: int = 1):
    level = min(max(level, 1), 3)
    paragraph = doc.add_heading(text, level=level)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    return paragraph


def format_government_table(table) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table)
    for row_idx, row in enumerate(table.rows):
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cell.paragraphs:
                set_paragraph_format(
                    paragraph,
                    alignment=WD_ALIGN_PARAGRAPH.CENTER,
                    first_line_indent_chars=0,
                    line_spacing_pt=20,
                    space_before_pt=0,
                    space_after_pt=0,
                )
                for run in paragraph.runs:
                    set_run_font(run, BODY_FONT, 10.5, bold=(row_idx == 0))


def add_government_table(
    doc: DocumentObject,
    rows: Iterable[Iterable[object]],
    *,
    header: bool = True,
):
    data = [[str(cell) for cell in row] for row in rows]
    if not data:
        return None
    table = doc.add_table(rows=len(data), cols=len(data[0]))
    for row_idx, row_data in enumerate(data):
        for col_idx, value in enumerate(row_data):
            _set_table_cell_text(table.cell(row_idx, col_idx), value, bold=header and row_idx == 0)
    format_government_table(table)
    return table


def create_government_reference_docx(output_path: str | Path = DEFAULT_REFERENCE_DOCX) -> Path:
    """Create the default Quarto/Pandoc reference DOCX."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    apply_government_report_style(doc)
    add_government_title(doc, "政府报告标题")
    add_government_heading(doc, "一、一级标题", level=1)
    add_government_paragraph(doc, "正文使用仿宋三号，首行缩进两个字符，固定行距二十八磅。")
    add_government_heading(doc, "（一）二级标题", level=2)
    add_government_paragraph(doc, "此段用于为 Pandoc/Quarto 提供默认正文样式。")
    add_government_heading(doc, "1. 三级标题", level=3)
    add_government_table(doc, [["指标", "数值"], ["示例", "100"]])
    doc.save(str(output))
    return output


def ensure_government_reference_docx(
    output_path: str | Path = DEFAULT_REFERENCE_DOCX,
) -> Path:
    """Return the default reference DOCX, creating it when missing."""
    output = Path(output_path)
    if not output.exists():
        create_government_reference_docx(output)
    return output
