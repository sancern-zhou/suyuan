"""
Weather Data Fetchers

气象数据获取后台
"""
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher

__all__ = [
    "NMCObservedWeatherFetcher",
]
