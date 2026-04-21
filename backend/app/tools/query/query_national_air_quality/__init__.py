"""
全国省份空气质量数据查询工具包

从参考项目 GDQFWS_SYS 获取全国各省份的六参数均值、AQI达标率和综合指数
"""
from .tool import (
    NationalAirQualityQueryTool,
    get_national_air_quality_tool,
    query_province_air_quality,
    query_city_air_quality
)
from .tool_wrapper import (
    QueryNationalProvinceAirQualityTool,
    QueryNationalCityAirQualityTool
)

__all__ = [
    'NationalAirQualityQueryTool',
    'get_national_air_quality_tool',
    'query_province_air_quality',
    'query_city_air_quality',
    'QueryNationalProvinceAirQualityTool',
    'QueryNationalCityAirQualityTool'
]
