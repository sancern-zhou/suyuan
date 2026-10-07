"""Hourly station monitoring, enabled only by an explicit deployment config."""
import asyncio

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.station_operation_monitor.runtime import collect, load_config


class StationOperationMonitorFetcher(DataFetcher):
    def __init__(self):
        config = load_config()
        super().__init__(
            name='station_operation_monitor',
            description='站点小时缺数、恢复和回补证据采集',
            schedule=config.get('collection_cron', '25 * * * *'),
        )

    async def fetch_and_store(self):
        result = await asyncio.to_thread(collect)
        if not result['success']:
            raise RuntimeError(f"station collection failed for {len(result['failed_slices'])} slices")
        return result
