"""
Fetchers Base Infrastructure

数据获取后台的基础设施
"""
from app.fetchers.base.fetcher_interface import DataFetcher, FetcherStatus
from app.fetchers.base.scheduler import FetcherScheduler

__all__ = ["DataFetcher", "FetcherStatus", "FetcherScheduler"]
