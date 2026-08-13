import base64

import pytest

from app.fetchers.weather.nmc_weather_chart_fetcher import (
    NMCWeatherChartClient,
    NMCWeatherChartFetcher,
    parse_nmc_weather_charts,
)
from app.services.data_registry import DataRegistryService
from app.services.image_cache import ImageCache

HTML = '''
<img id="imgpath" data-time="08/08 20:00"
  src="https://image.nmc.cn/product/current.JPG"
  data-img="https://image.nmc.cn/product/2026/08/08/WESA/chart_20260808120000000.JPG?v=1">
<div class="time" data-img="/product/2026/08/08/WESA/chart_20260808090000000.JPG?v=2"
  data-time="08/08 17:00"></div>
'''


def test_parse_nmc_weather_charts_reads_latest_first_and_resolves_relative_urls():
    charts = parse_nmc_weather_charts(HTML)

    assert len(charts) == 2
    assert charts[0].display_time == "08/08 20:00"
    assert charts[0].image_url.endswith("chart_20260808120000000.JPG?v=1")
    assert charts[1].image_url.startswith("https://image.nmc.cn/product/")


class FakeResponse:
    def __init__(self, *, text="", content=b"", status=200):
        self.text = text
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("weatherchart-h000.htm"):
            return FakeResponse(text=HTML)
        return FakeResponse(content=b"fake-jpeg-bytes")


@pytest.mark.asyncio
async def test_fetcher_downloads_registers_and_deduplicates_chart(tmp_path):
    session = FakeSession()
    client = NMCWeatherChartClient(session=session)
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    image_cache = ImageCache(cache_dir=str(tmp_path / "images"))
    fetcher = NMCWeatherChartFetcher(client=client, registry=registry, image_cache=image_cache)

    first = await fetcher.fetch_and_store()
    second = await fetcher.fetch_and_store()

    assert first["changed"] is True
    assert first["display_time"] == "08/08 20:00"
    assert second == {"fetched": 1, "changed": False, "image_url": first["image_url"]}
    assert len(session.calls) == 4
    payload = registry.load_dataset(first["data_id"])
    assert payload["product"] == "中国地面基本天气分析"
    assert base64.b64decode(image_cache.get(first["image_id"])) == b"fake-jpeg-bytes"
