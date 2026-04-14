"""
City Statistics Fetcher Module

168城市空气质量统计数据抓取器模块
"""

from app.fetchers.city_statistics.city_statistics_fetcher import CityStatisticsFetcher
from app.fetchers.city_statistics.city_statistics_old_standard_fetcher import CityStatisticsOldStandardFetcher
from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceStatisticsFetcher
from app.fetchers.city_statistics.province_statistics_old_standard_fetcher import ProvinceStatisticsOldStandardFetcher

__all__ = [
    'CityStatisticsFetcher',
    'CityStatisticsOldStandardFetcher',
    'ProvinceStatisticsFetcher',
    'ProvinceStatisticsOldStandardFetcher'
]
