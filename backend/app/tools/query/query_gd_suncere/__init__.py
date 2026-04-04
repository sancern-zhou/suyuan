"""
广东省 Suncere API 数据查询工具

提供基于官方 API 的广东省空气质量数据查询功能

特性：
- LLM 驱动的结构化参数查询
- 城市/站点名称自动映射到编码
- 多城市并发查询
- 区域对比分析
- 综合统计报表查询
- 对比分析报表查询
- 新标准数据查询（HJ 633-2024）
- 旧标准数据查询（十三五/十四五）
- DataSource 参数自动修正
"""
from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_day,
    execute_query_gd_suncere_station_hour,
    execute_query_gd_suncere_station_hour_real,
    execute_query_gd_suncere_regional_comparison,
    execute_query_gd_suncere_report,
    execute_query_gd_suncere_report_compare,
    execute_query_standard_comparison,
    QueryGDSuncereDataTool,
    GeoMappingResolver
)

# 新标准城市日数据查询
from app.tools.query.query_gd_suncere.tool_city_day_new import (
    execute_query_city_day_new_standard
)

# 旧标准城市日数据查询（十三五/十四五）
from app.tools.query.query_gd_suncere.tool_city_day_old_standard import (
    execute_query_city_day_old_standard
)

# Agent 工具包装器
from app.tools.query.query_gd_suncere.tool_wrapper import (
    QueryGDSuncereCityHourTool,
    QueryGDSuncereStationHourTool,
    QueryGDSuncereStationDayTool,
    QueryGDSuncereRegionalComparisonTool,
    QueryGDSuncereCityDayTool,
    QueryGDSuncereReportTool,
    QueryGDSuncereReportCompareTool,
    QueryStandardComparisonTool,
    QueryGDSuncereCityDayNewStandardTool,
    QueryGDSuncereCityDayOldStandardTool
)

__all__ = [
    "execute_query_gd_suncere_city_day",
    "execute_query_gd_suncere_station_day",
    "execute_query_gd_suncere_station_hour",
    "execute_query_gd_suncere_station_hour_real",
    "execute_query_gd_suncere_regional_comparison",
    "execute_query_gd_suncere_report",
    "execute_query_gd_suncere_report_compare",
    "execute_query_standard_comparison",
    "execute_query_city_day_new_standard",
    "execute_query_city_day_old_standard",
    "QueryGDSuncereDataTool",
    "GeoMappingResolver",
    "QueryGDSuncereCityHourTool",
    "QueryGDSuncereStationHourTool",
    "QueryGDSuncereStationDayTool",
    "QueryGDSuncereRegionalComparisonTool",
    "QueryGDSuncereCityDayTool",
    "QueryGDSuncereReportTool",
    "QueryGDSuncereReportCompareTool",
    "QueryStandardComparisonTool",
    "QueryGDSuncereCityDayNewStandardTool",
    "QueryGDSuncereCityDayOldStandardTool"
]
