"""Fetch the latest NMC China surface weather chart image."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.data_registry import DataRegistryService, data_registry
from app.services.image_cache import ImageCache, get_image_cache

logger = structlog.get_logger()

NMC_WEATHER_CHART_PAGE = "https://www.nmc.cn/publish/observations/china/dm/weatherchart-h000.htm"
NMC_IMAGE_HOST = "https://image.nmc.cn"
_IMAGE_PATTERN = re.compile(
    r'data-img=(?P<quote>["\'])(?P<url>[^"\']+)(?P=quote)'
)
_TIME_PATTERN = re.compile(r'data-time=(?P<quote>["\'])(?P<time>[^"\']+)(?P=quote)')


@dataclass(frozen=True)
class NMCWeatherChart:
    image_url: str
    display_time: str


def parse_nmc_weather_charts(html: str) -> list[NMCWeatherChart]:
    """Parse chart image URLs and their displayed production times from NMC HTML."""
    charts: list[NMCWeatherChart] = []
    for image_match in _IMAGE_PATTERN.finditer(html):
        image_url = urljoin(NMC_IMAGE_HOST, image_match.group("url"))
        tag_start = html.rfind("<", 0, image_match.start())
        tag_end = html.find(">", image_match.end())
        tag = html[tag_start : tag_end + 1] if tag_start >= 0 and tag_end >= 0 else ""
        time_match = _TIME_PATTERN.search(tag)
        display_time = time_match.group("time").strip() if time_match else ""
        if image_url not in {chart.image_url for chart in charts}:
            charts.append(NMCWeatherChart(image_url=image_url, display_time=display_time))
    return charts


class NMCWeatherChartClient:
    def __init__(
        self,
        page_url: str = NMC_WEATHER_CHART_PAGE,
        session: requests.Session | None = None,
    ) -> None:
        self.page_url = page_url
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch_latest_chart(self) -> tuple[NMCWeatherChart, bytes]:
        page_response = self.session.get(self.page_url, timeout=30)
        page_response.raise_for_status()
        charts = parse_nmc_weather_charts(page_response.text)
        if not charts:
            raise RuntimeError("No NMC weather chart image found in page")

        chart = charts[0]
        image_response = self.session.get(chart.image_url, timeout=60)
        image_response.raise_for_status()
        if not image_response.content:
            raise RuntimeError(f"NMC weather chart image is empty: {chart.image_url}")
        return chart, image_response.content


class NMCWeatherChartFetcher(DataFetcher):
    """Cache and register the latest three-hourly NMC surface weather chart."""

    def __init__(
        self,
        client: NMCWeatherChartClient | None = None,
        registry: DataRegistryService | None = None,
        image_cache: ImageCache | None = None,
    ) -> None:
        super().__init__(
            name="nmc_weather_chart_fetcher",
            description="国家气象中心中国地面天气形势图抓取",
            schedule="5 */3 * * *",
            version="1.0.0",
        )
        self.client = client or NMCWeatherChartClient()
        self.registry = registry or data_registry
        self.image_cache = image_cache or get_image_cache()
        self.state_path = self.registry.base_dir / "weather" / "nmc_weather_chart_latest.json"
        self.image_dir = self.registry.base_dir / "weather" / "charts"
        Path(self.image_cache.cache_dir).mkdir(parents=True, exist_ok=True)

    async def fetch_and_store(self) -> dict[str, Any]:
        chart, image_bytes = self.client.fetch_latest_chart()
        previous = self._load_state()
        if previous.get("image_url") == chart.image_url:
            return {"fetched": 1, "changed": False, "image_url": chart.image_url}

        timestamp = self._image_timestamp(chart.image_url) or datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"nmc_weather_chart_{timestamp}.jpg"
        source_path = self.image_dir / filename
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(image_bytes)

        image_id = f"nmc_weather_chart_{timestamp}"
        image = self.image_cache.save(base64.b64encode(image_bytes).decode("ascii"), chart_id=image_id)
        payload = {
            "source": "国家气象中心（NMC）",
            "page_url": self.client.page_url,
            "image_url": chart.image_url,
            "display_time": chart.display_time,
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "local_path": str(source_path),
            "image": image,
            "product": "中国地面基本天气分析",
        }
        entry = self.registry.register_payload(
            schema="nmc_weather_chart",
            version="v1",
            payload=payload,
            metadata={"source": "NMC", "region": "china", "level": "surface"},
        )
        self._save_state({"image_url": chart.image_url, "data_id": entry.data_id})
        return {
            "fetched": 1,
            "changed": True,
            "data_id": entry.data_id,
            "image_id": image_id,
            "image_url": chart.image_url,
            "display_time": chart.display_time,
        }

    @staticmethod
    def _image_timestamp(image_url: str) -> str | None:
        match = re.search(r"_(\d{14})\d{3}\.JPG(?:\?|$)", image_url, re.IGNORECASE)
        return match.group(1) if match else None

    def _load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
