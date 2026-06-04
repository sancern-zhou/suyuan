"""
Database package for meteorological data storage.
"""
from app.db.database import engine, async_session, get_db
# 导入所有模型（从models包）
from app.db.models import (
    Base,
    ERA5ReanalysisData,
    ObservedWeatherData,
    WeatherStation,
    WeatherDataCache,
    FireHotspot,
    DustForecast,
    DustEvent,
    ReportTemplate,
    ReportGenerationHistory,
)

__all__ = [
    "engine",
    "async_session",
    "get_db",
    "Base",
    "ERA5ReanalysisData",
    "ObservedWeatherData",
    "WeatherStation",
    "WeatherDataCache",
    "FireHotspot",
    "DustForecast",
    "DustEvent",
    "ReportTemplate",
    "ReportGenerationHistory",
]

