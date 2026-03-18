"""
广东省 Suncere API 数据查询工具

提供基于官方 API 的广东省空气质量数据查询功能

特性：
- LLM 驱动的结构化参数查询
- 城市/站点名称自动映射到编码
- 多城市并发查询
- 区域对比分析
- DataSource 参数自动修正
"""
from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour,
    execute_query_gd_suncere_regional_comparison,
    QueryGDSuncereDataTool,
    GeoMappingResolver
)

# Agent 工具包装器
from app.tools.query.query_gd_suncere.tool_wrapper import (
    QueryGDSuncereCityHourTool,
    QueryGDSuncereRegionalComparisonTool
)

__all__ = [
    "execute_query_gd_suncere_city_day",
    "execute_query_gd_suncere_station_hour",
    "execute_query_gd_suncere_regional_comparison",
    "QueryGDSuncereDataTool",
    "GeoMappingResolver",
    "QueryGDSuncereCityHourTool",
    "QueryGDSuncereRegionalComparisonTool"
]
