"""
报告工具模块

提供报告生成相关的工具，包括：
- read_docx: 读取DOCX文档
- generate_report: 生成DOCX报告
"""

from app.tools.report.read_docx.tool import ReadDocxTool
from app.tools.report.generate_report.tool import GenerateReportTool

__all__ = [
    "ReadDocxTool",
    "GenerateReportTool",
]
