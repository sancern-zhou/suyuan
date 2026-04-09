"""
新标准统计报表查询工具

基于 HJ 633-2026 新标准的空气质量统计报表查询工具
"""

from app.tools.query.query_new_standard_report.tool import (
    QueryNewStandardReportTool,
    execute_query_new_standard_report
)

__all__ = [
    "QueryNewStandardReportTool",
    "execute_query_new_standard_report"
]
