"""
数据库模型包
导出所有数据库模型
"""
# 导入原始气象模型
from .weather_models import (
    Base,
    ERA5ReanalysisData,
    ObservedWeatherData,
    WeatherStation,
    WeatherDataCache,
    FireHotspot,
    DustForecast,
    DustEvent,
    AirQualityForecast,
    CityAQIPublishHistory,
)

# 导入报告模板模型
from .report_template import ReportTemplate, ReportGenerationHistory
from app.db.report_package_model import ReportPackageDB

# 导入快速溯源模型（暂时注释，文件不存在）
# from .quick_trace_models import QuickTraceAnalysis

__all__ = [
    "Base",
    "ERA5ReanalysisData",
    "ObservedWeatherData",
    "WeatherStation",
    "WeatherDataCache",
    "FireHotspot",
    "DustForecast",
    "DustEvent",
    "AirQualityForecast",
    "CityAQIPublishHistory",
    "ReportTemplate",
    "ReportPackageDB",
    "ReportGenerationHistory",
    # "QuickTraceAnalysis",  # 暂时注释，文件不存在
]


