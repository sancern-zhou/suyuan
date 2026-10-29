"""
Weather Data Fetchers

气象数据获取后台
"""
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher

__all__ = [
    "ObservedWeatherFetcher",
    "NMCObservedWeatherFetcher",
]
