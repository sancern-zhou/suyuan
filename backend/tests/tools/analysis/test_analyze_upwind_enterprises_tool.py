from pathlib import Path

import pytest

from app.tools.analysis.analyze_upwind_enterprises import tool as upwind_tool_module
from app.tools.analysis.analyze_upwind_enterprises.tool import AnalyzeUpwindEnterprisesTool


class FakeContext:
    def get_raw_data(self, data_id):
        assert data_id == "weather-data"
        return [
            {
                "timestamp": "2026-07-06 09:00:00",
                "measurements": {
                    "wind_direction_10m": 150,
                    "wind_speed_10m": 2.4,
                },
            }
        ]


class FakeUpwindAPI:
    async def analyze_upwind_enterprises(self, **kwargs):
        return {
            "status": "success",
            "public_url": "http://example.test/static-link/upwind-map",
            "filtered": [
                {
                    "name": "测试企业",
                    "industry": "包装装潢及其他印刷",
                    "distance_km": 1.2,
                    "lat": 23.03,
                    "lng": 113.15,
                    "hit_ratio": 1.0,
                    "score_sum": 3.5,
                    "emissions": {"VOCs": 1.2, "NOx": 0.3},
                }
            ],
            "meta": {
                "station": {
                    "name": kwargs["station_name"],
                    "lat": 23.0467,
                    "lng": 113.144,
                }
            },
        }


@pytest.mark.asyncio
async def test_tool_returns_remote_and_local_map_image(monkeypatch, tmp_path):
    monkeypatch.setattr(upwind_tool_module, "upwind_api", FakeUpwindAPI())

    class DownloadingTool(AnalyzeUpwindEnterprisesTool):
        async def _download_url_to_file(self, url, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-amap-image")
            return output_path

    result = await DownloadingTool().execute(
        context=FakeContext(),
        weather_data_id="weather-data",
        city_name="佛山",
        station_name="南海气象局",
        output_dir=str(tmp_path),
    )

    assert result["success"] is True
    assert result["map_images"] == [
        {
            "station_name": "南海气象局",
            "map_url": "http://example.test/static-link/upwind-map",
            "local_path": str(tmp_path / "upwind_enterprises_1.png"),
            "visual_id": "upwind_佛山_南海气象局_0",
        }
    ]
    assert (tmp_path / "upwind_enterprises_1.png").read_bytes() == b"fake-amap-image"
    visual_data = result["visuals"][0]["payload"]["data"]
    assert visual_data["map_url"] == "http://example.test/static-link/upwind-map"
    assert visual_data["map_local_path"] == str(tmp_path / "upwind_enterprises_1.png")
    assert visual_data["local_path"] == str(tmp_path / "upwind_enterprises_1.png")


@pytest.mark.asyncio
async def test_tool_downloads_static_map_from_amap_static_api(monkeypatch, tmp_path):
    monkeypatch.setattr(upwind_tool_module, "upwind_api", FakeUpwindAPI())
    monkeypatch.setattr(upwind_tool_module.settings, "amap_public_key", "test-amap-key")
    downloaded_urls = []

    class DownloadingTool(AnalyzeUpwindEnterprisesTool):
        async def _download_url_to_file(self, url, output_path):
            downloaded_urls.append(url)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-amap-image")
            return output_path

    result = await DownloadingTool().execute(
        context=FakeContext(),
        weather_data_id="weather-data",
        city_name="佛山",
        station_name="南海气象局",
        output_dir=str(tmp_path),
    )

    assert result["success"] is True
    assert downloaded_urls
    assert downloaded_urls[0].startswith("https://restapi.amap.com/v3/staticmap?")
    assert "key=test-amap-key" in downloaded_urls[0]
    assert "location=113.144,23.0467" in downloaded_urls[0]
    assert "http://example.test/static-link/upwind-map" not in downloaded_urls[0]
    assert result["map_images"][0]["local_path"] == str(tmp_path / "upwind_enterprises_1.png")


@pytest.mark.asyncio
async def test_tool_accepts_direct_weather_records_without_context(monkeypatch, tmp_path):
    monkeypatch.setattr(upwind_tool_module, "upwind_api", FakeUpwindAPI())

    class DownloadingTool(AnalyzeUpwindEnterprisesTool):
        async def _download_url_to_file(self, url, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake-amap-image")
            return output_path

    result = await DownloadingTool().execute(
        context=None,
        weather_records=[
            {
                "timestamp": "2026-07-06 09:00:00",
                "measurements": {
                    "wind_direction_10m": 150,
                    "wind_speed_10m": 2.4,
                },
            }
        ],
        city_name="佛山",
        station_name="南海气象局",
        output_dir=str(tmp_path),
    )

    assert result["success"] is True
    assert result["metadata"]["record_count"] == 1
    assert result["map_images"][0]["local_path"] == str(tmp_path / "upwind_enterprises_1.png")
