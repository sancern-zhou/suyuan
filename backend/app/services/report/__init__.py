"""
报告服务模块

提供报告生成相关的服务：
- report_template_parser: 模板解析器
- report_data_matcher: 数据匹配器
- report_docx_builder: DOCX构建器
"""

from app.services.report.report_template_parser import ReportTemplateParser
from app.services.report.report_data_matcher import ReportDataMatcher
from app.services.report.report_docx_builder import ReportDocxBuilder
from app.services.report.government_docx_style import (
    DEFAULT_REFERENCE_DOCX,
    add_government_heading,
    add_government_paragraph,
    add_government_table,
    add_government_title,
    apply_government_report_style,
    ensure_government_reference_docx,
    format_government_table,
    set_paragraph_format,
    set_run_font,
)

__all__ = [
    "ReportTemplateParser",
    "ReportDataMatcher",
    "ReportDocxBuilder",
    "DEFAULT_REFERENCE_DOCX",
    "add_government_heading",
    "add_government_paragraph",
    "add_government_table",
    "add_government_title",
    "apply_government_report_style",
    "ensure_government_reference_docx",
    "format_government_table",
    "set_paragraph_format",
    "set_run_font",
]
