"""
质控例行检查记录查询工具

轻量级查询工具，直接从 SQL Server 数据库获取质控数据，
无需本地存储，适合 Agent 问数模式。
"""

from app.tools.query.get_quality_control_records.tool import GetQualityControlRecordsTool

__all__ = ['GetQualityControlRecordsTool']
