import pytest
from datetime import timezone

from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher


class FakeFirmsClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_recent_fires(self, *, region: str, satellite: str, days: int):
        self.calls.append(satellite)
        return [
            {
                "latitude": 35.1,
                "longitude": 111.2,
                "brightness": 334.3,
                "scan": 0.61,
                "track": 0.53,
                "acq_date": "2026-07-08",
                "acq_time": "0342",
                "satellite": satellite,
                "confidence": 70,
                "version": "2.0NRT",
                "bright_t31": 299.19,
                "frp": 4.37,
                "daynight": "D",
            }
        ]


class FakeSatelliteRepo:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save_fire_hotspots(self, hotspots):
        self.saved.extend(hotspots)
        return len(hotspots)


@pytest.mark.asyncio
async def test_fetcher_collects_multiple_firms_sources() -> None:
    fetcher = NASAFirmsFetcher()
    fetcher.client = FakeFirmsClient()
    fetcher.repo = FakeSatelliteRepo()

    result = await fetcher.fetch_and_store()

    assert fetcher.client.calls == [
        "VIIRS_SNPP_NRT",
        "VIIRS_NOAA20_NRT",
        "VIIRS_NOAA21_NRT",
        "MODIS_NRT",
    ]
    assert len(fetcher.repo.saved) == 4
    assert result["saved"] == 4


def test_clean_fire_data_keeps_firms_time_in_utc() -> None:
    cleaned = NASAFirmsFetcher()._clean_fire_data([
        {
            "latitude": 35.1,
            "longitude": 111.2,
            "brightness": 334.3,
            "scan": 0.61,
            "track": 0.53,
            "acq_date": "2026-07-08",
            "acq_time": "0342",
            "satellite": "N20",
            "confidence": 70,
            "version": "2.0NRT",
            "bright_t31": 299.19,
            "frp": 4.37,
            "daynight": "D",
        }
    ])

    assert cleaned[0]["acq_datetime"].tzinfo is timezone.utc
    assert cleaned[0]["acq_datetime"].isoformat() == "2026-07-08T03:42:00+00:00"
