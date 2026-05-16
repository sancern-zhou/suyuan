"""
污染溯源报告生成工具模块

将 Expert V3 多专家溯源分析工作流改造为单一工具，
直接生成 qmd 格式报告文档，支持导出为 HTML 和 Word 格式。
"""

from app.tools.reporting.generate_tracing_report.tool import GenerateTracingReportTool


def register_tool(registry):
    """
    注册报告生成工具到全局工具注册表

    Args:
        registry: ToolRegistry 实例
    """
    try:
        tool = GenerateTracingReportTool()
        registry.register(tool, priority=388)
        return tool
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error(
            "register_tracing_report_tool_failed",
            error=str(e),
            exc_info=True
        )
        return None


__all__ = [
    "register_tool",
    "GenerateTracingReportTool"
]
