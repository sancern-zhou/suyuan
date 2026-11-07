"""
Validate DOCX/XLSX deliverables: render-level QA for docx, read-back QA for xlsx.

docx: soffice→pdf→png 渲染链（复用 slides_qa 通用实现）+ 空白页/字体检测 +
      python-docx 结构检查（标题层级/表格图片计数）。
xlsx: openpyxl 双读回校验（错误值/空表/表名/列宽/冻结窗格），不做渲染
      （前端 SheetJS 即预览，xlsx→pdf 分页不可控）。
issue 词汇与 gate 三态（passed/needs_revision/qa_failed）对齐 validate_pptx。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.slides_qa.detect_fonts import detect_pdf_fonts
from app.tools.office.slides_qa.detect_overflow import inspect_rendered_pages
from app.tools.office.slides_qa.render_pptx import render_pdf_to_pngs, render_pptx_to_pdf
from app.tools.resource_declarations import derivative_file, primary_file
from app.utils.path_config import get_data_registry, resolve_agent_path

logger = structlog.get_logger()

DEFAULT_EXPECTED_FONTS = ["Noto Sans CJK SC"]

# xlsx 错误值（Excel 缓存显示值，data_only 读回可见）
XLSX_ERROR_VALUES = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NULL!", "#NUM!", "#N/A"}
# openpyxl 默认列宽（字符单位）；无显式列宽且内容明显超宽时提示
XLSX_DEFAULT_COLUMN_WIDTH = 8.43

DOCX_ISSUE_SEVERITY = {
    "validation_error": "high",
    "rendered_blank_page": "high",
    "docx_empty_document": "high",
    "docx_no_heading": "medium",
    "docx_heading_level_jump": "low",
    "expected_font_missing": "medium",
    "font_detection_unavailable": "low",
    "rendered_qa_unavailable": "low",
}

XLSX_ISSUE_SEVERITY = {
    "validation_error": "high",
    "xlsx_error_value": "high",
    "xlsx_sheet_name_invalid": "high",
    "xlsx_empty_sheet": "medium",
    "xlsx_column_overflow": "medium",
    "xlsx_no_freeze_panes": "low",
    "xlsx_missing_header": "low",
}

DOCX_ISSUE_MESSAGES = {
    "validation_error": "DOCX 验证流程执行异常。",
    "rendered_blank_page": "渲染结果为空白页。",
    "docx_empty_document": "文档没有正文内容。",
    "docx_no_heading": "文档缺少标题样式（Heading/标题），导航与目录无法建立。",
    "docx_heading_level_jump": "标题层级跳级（如 H1 直接到 H3），目录结构混乱。",
    "expected_font_missing": "PDF 字体检测未发现期望字体，中文可能未设置 eastasia 字体。",
    "font_detection_unavailable": "字体检测不可用。",
    "rendered_qa_unavailable": "渲染级 QA 不可用（不影响结构检查结果）。",
}

XLSX_ISSUE_MESSAGES = {
    "validation_error": "XLSX 验证流程执行异常。",
    "xlsx_error_value": "单元格存在公式错误值。",
    "xlsx_sheet_name_invalid": "工作表名称非法（>31 字符或含 \\ / * ? : [ ]）。",
    "xlsx_empty_sheet": "工作表为空。",
    "xlsx_column_overflow": "列宽不足以显示内容（中文按 2 字符宽计）。",
    "xlsx_no_freeze_panes": "未设置冻结窗格，长表滚动时表头不可见。",
    "xlsx_missing_header": "首个工作表首行为空，缺少表头。",
}

# 仅运行时不可用类问题 → qa_failed；其余有问题 → needs_revision
QA_FAILED_ONLY_TYPES = {"rendered_qa_unavailable", "font_detection_unavailable", "validation_error"}


def _display_width(value: Any) -> int:
    """中文等全角字符按 2 个字符宽度估算。"""
    text = str(value or "")
    return sum(2 if ord(char) > 127 else 1 for char in text)


def _structure_issues(issues: List[Dict[str, Any]], severity_map: Dict[str, str]) -> List[Dict[str, Any]]:
    structured = []
    for index, issue in enumerate(issues, start=1):
        issue_type = str(issue.get("type") or "unknown")
        structured.append(
            {
                "id": f"officeqa-{index:03d}",
                "type": issue_type,
                "severity": severity_map.get(issue_type, "low"),
                "message": issue.get("message") or issue_type,
                **{key: value for key, value in issue.items() if key not in ("type", "message")},
            }
        )
    return structured


class ValidateOfficeTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="validate_office",
            description=(
                "校验 DOCX/XLSX 交付文件：docx 渲染页检（空白页/字体）+ 标题层级结构检查；"
                "xlsx 读回校验（公式错误值/空表/表名/列宽/冻结窗格）。"
                "返回 structured_issues 与 gate（passed/needs_revision/qa_failed）。"
                "生成前先 view_skill: docx_authoring / xlsx_authoring。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )
        self.default_qa_root = get_data_registry() / "documents" / "qa"

    async def execute(
        self,
        path: str,
        expected_fonts: Optional[List[str]] = None,
        dpi: int = 144,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            file_path = resolve_agent_path(path)
            if not file_path.exists():
                return self._failure(f"文件不存在: {file_path}")
            suffix = file_path.suffix.lower()
            if suffix not in {".docx", ".xlsx"}:
                return self._failure(f"只支持 .docx/.xlsx，当前格式: {suffix or '(无后缀)'}")

            qa_dir = self._resolve_output_dir(output_dir, file_path)
            qa_dir.mkdir(parents=True, exist_ok=True)

            if suffix == ".docx":
                report = await self._inspect_docx(file_path, qa_dir, expected_fonts, dpi)
            else:
                report = self._inspect_xlsx(file_path)

            structured = _structure_issues(
                report["issues"],
                DOCX_ISSUE_SEVERITY if suffix == ".docx" else XLSX_ISSUE_SEVERITY,
            )
            issue_types = {issue["type"] for issue in structured}
            blocking_count = sum(1 for issue in structured if issue["severity"] == "high")
            if structured and issue_types <= QA_FAILED_ONLY_TYPES:
                status = "qa_failed"
            elif structured:
                status = "needs_revision"
            else:
                status = "passed"
            report["structured_issues"] = structured
            report["issue_summary"] = dict(sorted(Counter(i["type"] for i in structured).items()))
            report["gate"] = {
                "status": status,
                "passed": status == "passed",
                "blocking": status == "qa_failed" or blocking_count > 0,
                "blocking_issue_count": blocking_count,
                "issue_count": len(structured),
            }

            report_path = qa_dir / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(report_path)

            summary = (
                f"{suffix.upper()} 验证完成：{file_path.name}，发现 {len(structured)} 个问题"
                if structured
                else f"{suffix.upper()} 验证通过：{file_path.name}"
            )
            return {
                "success": True,
                "data": report,
                "resources": self._declare_resources(file_path, report),
                "summary": summary,
            }
        except Exception as e:
            logger.error("validate_office_failed", path=path, error=str(e), exc_info=True)
            return self._failure(str(e))

    # ------------------------------------------------------------------ docx

    async def _inspect_docx(
        self, file_path: Path, qa_dir: Path, expected_fonts: Optional[List[str]], dpi: int
    ) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        render: Dict[str, Any] = {"enabled": False, "page_count": 0}
        fonts: Dict[str, Any] = {"fonts": [], "issues": [], "missing_expected_fonts": []}
        try:
            pdf_path, png_paths = await asyncio.to_thread(self._render_docx, file_path, qa_dir, dpi)
            render = {"enabled": True, "pdf_path": str(pdf_path), "page_count": len(png_paths),
                      "page_pngs": [str(p) for p in png_paths]}
            rendered = inspect_rendered_pages(png_paths)
            for issue in rendered.get("issues", []):
                issues.append({"type": "rendered_blank_page", "page": issue.get("slide"), "message": None})
            fonts = detect_pdf_fonts(pdf_path, expected_fonts=expected_fonts or DEFAULT_EXPECTED_FONTS)
            for issue in fonts.get("issues", []):
                issues.append({"type": issue["type"], "message": issue.get("message")})
        except Exception as render_error:
            issues.append({"type": "rendered_qa_unavailable", "message": str(render_error)[:200]})

        issues.extend(self._inspect_docx_structure(file_path))
        return {"file_path": str(file_path), "qa_dir": str(qa_dir), "render": render, "fonts": fonts, "issues": issues}

    def _render_docx(self, file_path: Path, qa_dir: Path, dpi: int):
        # render_pptx_to_pdf 的 soffice 转换是通用的（docx→pdf 直接可用）
        pdf_path = render_pptx_to_pdf(file_path, qa_dir)
        png_paths = render_pdf_to_pngs(pdf_path, qa_dir / "pages", dpi=dpi)
        return pdf_path, png_paths

    def _inspect_docx_structure(self, file_path: Path) -> List[Dict[str, Any]]:
        try:
            from docx import Document
        except ImportError:
            return [{"type": "rendered_qa_unavailable", "message": "python-docx 未安装"}]

        document = Document(str(file_path))
        issues: List[Dict[str, Any]] = []
        heading_levels: List[int] = []
        body_chars = 0
        for paragraph in document.paragraphs:
            text = (paragraph.text or "").strip()
            body_chars += len(text)
            style_name = (getattr(paragraph.style, "name", "") or "")
            if style_name.startswith("Heading") or style_name.startswith("标题"):
                digits = "".join(char for char in style_name if char.isdigit())
                if digits:
                    heading_levels.append(int(digits))
        if body_chars == 0 and not document.tables:
            issues.append({"type": "docx_empty_document"})
        if not heading_levels:
            if body_chars:
                issues.append({"type": "docx_no_heading"})
        else:
            for previous, current in zip(heading_levels, heading_levels[1:]):
                if current - previous > 1:
                    issues.append({"type": "docx_heading_level_jump", "from_level": previous, "to_level": current})
                    break
        return issues

    # ------------------------------------------------------------------ xlsx

    def _inspect_xlsx(self, file_path: Path) -> Dict[str, Any]:
        try:
            from openpyxl import load_workbook
        except ImportError:
            return {"file_path": str(file_path), "issues": [
                {"type": "validation_error", "message": "openpyxl 未安装"}
            ]}

        issues: List[Dict[str, Any]] = []
        sheets_meta: List[Dict[str, Any]] = []
        workbook = load_workbook(str(file_path), data_only=False)
        values_view = load_workbook(str(file_path), data_only=True)

        invalid_chars = set('\\/*?:[]')
        for sheet in workbook.worksheets:
            values = values_view[sheet.title]
            max_col = sheet.max_column or 0
            filled_rows = 0
            error_cells: List[str] = []
            overflow_columns: List[str] = []
            header_missing = True

            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if any(value is not None and str(value).strip() != "" for value in row):
                    filled_rows += 1
                if row_index == 1 and any(value is not None and str(value).strip() != "" for value in row):
                    header_missing = False

            for row in values.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.strip() in XLSX_ERROR_VALUES:
                        if len(error_cells) < 10:
                            error_cells.append(cell.coordinate)

            # 列宽 vs 内容：显式列宽不足，或默认列宽下内容明显超宽（>20 显示宽）
            column_needs: Dict[int, int] = {}
            for row in sheet.iter_rows(values_only=True):
                for col_index, value in enumerate(row, start=1):
                    if value is not None:
                        column_needs[col_index] = max(column_needs.get(col_index, 0), _display_width(value))
            for col_index, needed in column_needs.items():
                if needed <= 20:
                    continue
                letter = sheet.cell(row=1, column=col_index).column_letter
                dimension = sheet.column_dimensions.get(letter)
                width = dimension.width if dimension and dimension.width else XLSX_DEFAULT_COLUMN_WIDTH
                if width < needed * 0.9:
                    overflow_columns.append(letter)

            if len(sheet.title) > 31 or invalid_chars & set(sheet.title):
                issues.append({"type": "xlsx_sheet_name_invalid", "sheet": sheet.title})
            if filled_rows == 0:
                issues.append({"type": "xlsx_empty_sheet", "sheet": sheet.title})
            if error_cells:
                issues.append({"type": "xlsx_error_value", "sheet": sheet.title, "cells": error_cells})
            if overflow_columns:
                issues.append({"type": "xlsx_column_overflow", "sheet": sheet.title, "columns": overflow_columns})
            if not sheet.freeze_panes and filled_rows > 15:
                issues.append({"type": "xlsx_no_freeze_panes", "sheet": sheet.title})
            if header_missing and filled_rows:
                issues.append({"type": "xlsx_missing_header", "sheet": sheet.title})

            sheets_meta.append({
                "sheet": sheet.title, "filled_rows": filled_rows, "max_col": max_col,
                "error_cells": error_cells, "overflow_columns": overflow_columns,
            })

        return {"file_path": str(file_path), "sheets": sheets_meta, "issues": issues}

    # ------------------------------------------------------------------ 声明

    def _declare_resources(self, file_path: Path, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        slot = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:16]
        suffix = file_path.suffix.lower().lstrip(".")
        group_key = f"office:{slot}"
        primary = primary_file(
            file_path,
            group_key=group_key,
            tool_name="validate_office",
            renderer="spreadsheet" if suffix == "xlsx" else "file",
            capabilities=("preview", "download", "edit"),
        )
        primary["resource_key"] = suffix
        members = [primary]
        report_path = report.get("report_path")
        if report_path and Path(report_path).is_file():
            members.append(derivative_file(
                Path(report_path), group_key=group_key, parent_key=suffix,
                tool_name="validate_office", relation="attachment", renderer="file",
            ))
        render = report.get("render") or {}
        pdf_path = render.get("pdf_path")
        if pdf_path and Path(pdf_path).is_file():
            members.append(derivative_file(
                Path(pdf_path), group_key=group_key, parent_key=suffix,
                tool_name="validate_office", relation="preview", renderer="pdf",
            ))
        for png in render.get("page_pngs", [])[:30]:
            if Path(png).is_file():
                members.append(derivative_file(
                    Path(png), group_key=group_key, parent_key=suffix,
                    tool_name="validate_office", relation="attachment", renderer="image",
                ))
        return members

    def _resolve_output_dir(self, output_dir: Optional[str], file_path: Path) -> Path:
        if output_dir:
            return resolve_agent_path(output_dir)
        return (self.default_qa_root / f"{file_path.stem}_{uuid.uuid4().hex[:8]}").resolve()

    def _failure(self, message: str) -> Dict[str, Any]:
        return {"success": False, "data": {"error": message}, "summary": f"文档验证失败：{message[:80]}"}

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "validate_office",
            "description": (
                "校验 DOCX/XLSX 交付文件并返回 structured_issues 与 gate。"
                "docx：渲染页检（空白页/字体）+ 标题层级；xlsx：公式错误值/空表/表名/列宽/冻结窗格。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "DOCX/XLSX 文件路径"},
                    "expected_fonts": {
                        "type": "array", "items": {"type": "string"},
                        "description": "docx 期望字体列表，默认 [Noto Sans CJK SC]，可选",
                    },
                    "dpi": {"type": "integer", "description": "docx 页图渲染 DPI，默认 144"},
                    "output_dir": {"type": "string", "description": "QA 输出目录，可选"},
                },
                "required": ["path"],
            },
        }

    def is_available(self) -> bool:
        return True


tool = ValidateOfficeTool()
