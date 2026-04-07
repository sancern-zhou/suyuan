"""
Data Fetching Backend

定时从外部API爬取数据，存入云数据库的后台程序
"""

from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.city_statistics import CityStatisticsFetcher, ProvinceStatisticsFetcher

def create_scheduler() -> FetcherScheduler:
    """
    创建并配置Fetcher调度器

    Returns:
        FetcherScheduler实例
    """
    scheduler = FetcherScheduler()

    # 注册所有Fetchers
    scheduler.register(CityStatisticsFetcher())
    scheduler.register(ProvinceStatisticsFetcher())

    return scheduler


__all__ = ['create_scheduler', 'FetcherScheduler']
