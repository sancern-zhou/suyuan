import json
from pathlib import Path

import pytest

from app.fetchers.consultation.monthly_pollution_events_components import (
    MonthlyPollutionEventsComponents,
)


class FakeWeatherImageTool:
    def __init__(self):
        self.calls = []

    async def execute(self, product, date=None, time=None, download=True):
        self.calls.append({
            "product": product,
            "date": date,
            "time": time,
            "download": download,
        })
        local_path = f"/tmp/fake-weather/{product}/{date}/{str(time).replace(',', '_')}.png"
        return {
            "success": True,
            "data": {
                "product": product,
                "product_name": product,
                "date": date,
                "time_key": str(time).replace(",", "_"),
                "source_url": f"http://example.test/{product}/{date}/{time}",
                "local_path": local_path,
                "downloaded": True,
                "source": "环境大数据管理云平台",
            },
        }


@pytest.fixture
def generator(tmp_path, monkeypatch):
    instance = MonthlyPollutionEventsComponents(2026, 5)
    instance.output_dir = tmp_path
    instance.fetch_hourly_pollutants = lambda event: []
    instance.fetch_component_dataset = lambda event, component_type: []
    fake_tool = FakeWeatherImageTool()
    instance.weather_image_tool = fake_tool
    return instance, fake_tool


def test_component_manifest_includes_sparse_weather_images_for_pollution_events(generator):
    instance, fake_tool = generator
    events = [
        {
            "city": "东莞",
            "station": "东莞",
            "date": "2026-05-29",
            "aqi": 116,
            "primary_pollutant": "O3",
        },
        {
            "city": "东莞",
            "station": "南城元岭",
            "date": "2026-05-29",
            "aqi": 108,
            "primary_pollutant": "O3",
        },
    ]

    manifest_path = instance.generate_component_files(events)

    calls = fake_tool.calls
    assert calls.count({
        "product": "backward_trajectory",
        "date": "20260529",
        "time": "东莞,20260529",
        "download": True,
    }) == 1
    assert {"product": "rainfall_24h", "date": "20260529", "time": "12", "download": True} in calls
    assert {"product": "hourly_wind_field", "date": "20260529", "time": "00", "download": True} in calls
    assert {"product": "hourly_wind_field", "date": "20260529", "time": "06", "download": True} in calls
    assert not any(call["product"] == "radar_mosaic" for call in calls)

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    process_images = manifest["weather_images"]["pollution_process_images"]
    assert manifest["weather_images"]["source"] == "环境大数据管理云平台"
    assert process_images["usage_stage"] == "污染过程气象背景"
    assert len(process_images["items"]) == 4
    assert all(item["available"] is True for item in process_images["items"])


def test_component_manifest_adds_next_month_outlook_forecast_images_without_events(generator):
    instance, fake_tool = generator

    manifest_path = instance.generate_component_files([])

    calls = fake_tool.calls
    assert {"product": "national_max_temperature_forecast", "date": "20260601", "time": "024", "download": True} in calls
    assert {"product": "national_max_temperature_forecast", "date": "20260601", "time": "072", "download": True} in calls
    assert {"product": "national_precip_forecast", "date": "20260601", "time": "024", "download": True} in calls
    assert {"product": "max_10m_wind_speed_24h", "date": "20260601", "time": "072", "download": True} in calls
    assert not any(call["product"] == "backward_trajectory" for call in calls)

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    outlook_images = manifest["weather_images"]["next_month_outlook_images"]
    assert outlook_images["usage_stage"] == "下月污染形势研判"
    assert outlook_images["forecast_base_date"] == "20260601"
    assert len(outlook_images["items"]) == 6
    assert all(item["available"] is True for item in outlook_images["items"])


@pytest.mark.asyncio
async def test_weather_image_manifest_can_run_inside_existing_event_loop(generator):
    instance, fake_tool = generator

    manifest = instance.generate_weather_image_manifest([])

    assert manifest["next_month_outlook_images"]["items"]
    assert fake_tool.calls
