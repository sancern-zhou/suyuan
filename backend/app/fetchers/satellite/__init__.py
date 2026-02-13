"""
Satellite data fetchers package.

包含卫星遥感数据采集后台：
- NASA FIRMS 火点数据
"""
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher

__all__ = ["NASAFirmsFetcher"]
