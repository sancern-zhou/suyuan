"""
Data Fetching Backend

定时从外部API爬取数据，存入云数据库的后台程序
"""

from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.consultation import ConsultationFileFetcher
from app.fetchers.air_quality_data_quality_monitor import AirQualityDataQualityFetcher
from app.fetchers.city_pollution_event_monitor import CityPollutionEventFetcher

def create_scheduler() -> FetcherScheduler:
    """
    创建并配置Fetcher调度器

    Returns:
        FetcherScheduler实例
    """
    scheduler = FetcherScheduler()

    # 注册所有Fetchers
    scheduler.register(ConsultationFileFetcher())  # 会商文件批量更新
    scheduler.register(AirQualityDataQualityFetcher())  # 空气质量数据质量巡检
    scheduler.register(CityPollutionEventFetcher())  # 城市污染过程告警

    return scheduler


__all__ = ['create_scheduler', 'FetcherScheduler']
