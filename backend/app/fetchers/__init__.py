"""
Data Fetching Backend

定时从外部API爬取数据，存入云数据库的后台程序
"""

from app.fetchers.air_quality_data_quality_monitor import AirQualityDataQualityFetcher
from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.city_pollution_event_monitor import CityPollutionEventFetcher
from app.fetchers.consultation import ConsultationFileFetcher
from app.fetchers.consultation.annual_ytd import AnnualYtdConsultationFileFetcher
from app.fetchers.consultation.monthly import MonthlyConsultationFileFetcher
from app.fetchers.consultation.monthly_supplement_fetchers import (
    MonthlyDistrictPollutantRankingFetcher,
    MonthlyMeteorologySupportFetcher,
    MonthlyPollutionEventsComponentsFetcher,
    MonthlyStationHighValuesFetcher,
)
from app.fetchers.fault_diagnosis import FaultDiagnosisFetcher
from app.fetchers.quick_trace import JiningQuickTraceFetcher
from app.fetchers.tenders import TenderInformationFetcher
from app.fetchers.weather.city_air_quality_forecast_fetcher import (
    CityAirQualityForecastFetcher,
)
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.nmc_weather_chart_fetcher import NMCWeatherChartFetcher
from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    OpenMeteoAirQualityForecastFetcher,
)
from app.fetchers.yuncheng_trial import YunchengTrialFetcher


def create_scheduler() -> FetcherScheduler:
    """
    创建并配置Fetcher调度器

    Returns:
        FetcherScheduler实例
    """
    scheduler = FetcherScheduler()

    # Keep manual/API scheduler creation consistent with lifecycle startup.
    from app.project_config.loader import load_project_context
    from app.services.lifecycle_manager import _configured_fetchers
    from config.settings import settings

    context = load_project_context(settings.project_id)
    for fetcher in _configured_fetchers(context):
        scheduler.register(fetcher)

    return scheduler


__all__ = ['create_scheduler', 'FetcherScheduler']
