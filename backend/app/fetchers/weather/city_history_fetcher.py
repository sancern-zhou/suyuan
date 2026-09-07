"""Collect configured city points and drain durable history repairs."""

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.weather_history import WeatherHistoryService


class CityHistoryFetcher(DataFetcher):
    def __init__(self, config, project_id):
        super().__init__(
            name="city_weather_history_fetcher",
            description="City historical weather and boundary-layer height backfills",
            schedule="*/5 * * * *",
        )
        self.history = WeatherHistoryService(config, project_id=project_id)

    async def fetch_and_store(self):
        self.history.schedule_collection()
        await self.history.run_pending()
