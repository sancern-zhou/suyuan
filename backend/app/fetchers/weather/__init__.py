"""
Weather Data Fetchers

气象数据获取后台
"""
from app.fetchers.weather.era5_fetcher import ERA5Fetcher
from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher
from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    OpenMeteoAirQualityForecastFetcher,
)

__all__ = [
    "ERA5Fetcher",
    "ObservedWeatherFetcher",
    "JiningERA5Fetcher",
    "NMCObservedWeatherFetcher",
    "OpenMeteoAirQualityForecastFetcher",
]
