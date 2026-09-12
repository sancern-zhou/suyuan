"""
数据库模型包
导出所有数据库模型
"""
# 导入原始气象模型
from .weather_models import (
    Base,
    ERA5ReanalysisData,
    ObservedWeatherData,
    JiangsuNMCObservedWeatherData,
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

# 导入任务审核模型
from .task_review_db import TaskReviewDB

# 导入智能事件模型
from .smart_event_db import SmartEventDB, SmartEventTaskDB

__all__ = [
    "Base",
    "ERA5ReanalysisData",
    "ObservedWeatherData",
    "JiangsuNMCObservedWeatherData",
    "WeatherStation",
    "WeatherDataCache",
    "FireHotspot",
    "DustForecast",
    "DustEvent",
    "AirQualityForecast",
    "CityAQIPublishHistory",
    "ReportTemplate",
    "ReportGenerationHistory",
    "TaskReviewDB",
    "SmartEventDB",
    "SmartEventTaskDB",
]

