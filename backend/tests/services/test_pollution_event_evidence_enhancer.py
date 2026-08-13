from datetime import datetime

import pytest

from app.services.pollution_event_evidence_enhancer import PollutionEventEvidenceEnhancer


class RecordingRunner:
    def __init__(self):
        self.calls = []

    async def __call__(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return {
            "success": True,
            "data_id": f"{name}:data-id",
            "summary": f"{name} completed",
            "data": {"name": name},
        }


class UpwindRunner:
    def __init__(self):
        self.calls = []

    async def __call__(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == "analyze_upwind_enterprises":
            enterprises = [
                {
                    "name": f"企业{i}",
                    "industry": "机动车燃油零售",
                    "distance_km": i / 10,
                    "lat": 23.1 + i / 1000,
                    "lng": 113.2 + i / 1000,
                    "hit_ratio": 1 - i / 20,
                    "score_sum": 100 - i,
                    "emissions": {"VOCs": 10 - i / 10, "NOx": i / 10},
                }
                for i in range(1, 13)
            ]
            return {
                "success": True,
                "summary": "upwind completed",
                "visuals": [
                    {
                        "payload": {
                            "data": {
                                "station": {"name": "广雅中学"},
                                "enterprises": enterprises,
                                "map_url": "http://example.test/static-link/upwind-map",
                                "map_local_path": "/tmp/upwind_enterprises_1.png",
                                "local_path": "/tmp/upwind_enterprises_1.png",
                            }
                        }
                    }
                ],
                "map_images": [
                    {
                        "station_name": "广雅中学",
                        "map_url": "http://example.test/static-link/upwind-map",
                        "local_path": "/tmp/upwind_enterprises_1.png",
                        "visual_id": "upwind-test",
                    }
                ],
            }
        return {
            "success": True,
            "summary": f"{name} completed",
            "data": {"name": name},
        }


class SynopticWeatherRunner(RecordingRunner):
    async def __call__(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == "get_platform_weather_image":
            product = kwargs["product"]
            date = kwargs["date"]
            time = kwargs["time"]
            return {
                "success": True,
                "summary": f"{product} {date} {time} completed",
                "data": {
                    "product": product,
                    "product_name": f"{product}中文名",
                    "date": date,
                    "time_key": str(time),
                    "local_path": f"/tmp/weather/{product}_{date}_{time}.png",
                    "image_url": f"/api/image/{product}_{date}_{time}",
                    "downloaded": True,
                },
                "visuals": [
                    {
                        "type": "image",
                        "local_path": f"/tmp/weather/{product}_{date}_{time}.png",
                        "image_url": f"/api/image/{product}_{date}_{time}",
                    }
                ],
            }
        return await super().__call__(name, **kwargs)


class SavingContext:
    def __init__(self):
        self.saved = []

    def save_data(self, data, schema, metadata=None):
        self.saved.append((data, schema, metadata))
        return "saved-weather-data"


def _station_records():
    return [
        {
            "station_name": "低值站",
            "time": "2026-07-04 09:00:00",
            "measurements": {"PM2_5": 42.0, "O3_8h": 90.0},
            "lat": 23.1,
            "lon": 113.1,
        },
        {
            "station_name": "高值站",
            "time": "2026-07-04 10:00:00",
            "measurements": {"PM2_5": 118.0, "O3_8h": 120.0},
            "lat": 23.2,
            "lon": 113.2,
        },
    ]


def _station_records_without_coordinates():
    return [
        {
            "station_name": "广雅中学",
            "time": "2026-07-04 09:00:00",
            "measurements": {"O3": 63.0, "O3_8h": 0},
        },
        {
            "station_name": "从化天湖",
            "time": "2026-07-04 10:00:00",
            "measurements": {"O3": 87.0, "O3_8h": 0},
        },
    ]


def _shenzhen_station_records_without_coordinates():
    return [
        {
            "station_name": "观澜",
            "time": "2026-07-05 04:00:00",
            "measurements": {"NO2": 25.0},
        }
    ]


@pytest.mark.asyncio
async def test_pm_event_uses_pm_branch_and_highest_station(tmp_path):
    runner = RecordingRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_pm", "main_pollutant": "PM2_5"},
        event_dir=tmp_path,
        station_records=_station_records(),
        weather_records=[{"weather_data_id": "weather-data", "time": "2026-07-04 10:00:00", "wind_speed_10m": 1.2, "wind_direction_10m": 90}],
        component_results={"data_refs": {"pm25_components_data_id": "pm-components"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["main_pollutant_branch"] == "pm"
    assert result["target_station"]["station_name"] == "高值站"
    assert result["trajectory"]["status"] == "success"
    assert result["upwind_enterprises"]["status"] == "success"
    output_names = [item["name"] for item in result["component_analysis"]["outputs"]]
    assert "calculate_pm_pmf" in output_names
    assert "calculate_reconstruction" in output_names
    call_names = [name for name, _ in runner.calls]
    assert call_names[:4] == [
        "meteorological_trajectory_analysis",
        "analyze_upwind_enterprises",
        "calculate_pm_pmf",
        "calculate_reconstruction",
    ]
    assert "get_platform_weather_image" in call_names
    pmf_call = [kwargs for name, kwargs in runner.calls if name == "calculate_pm_pmf"][0]
    assert pmf_call["station_name"] == "高值站"
    assert pmf_call["pollutant_type"] == "PM2.5"


class FailingRunner:
    async def __call__(self, name, **kwargs):
        raise RuntimeError(f"{name} exploded")


@pytest.mark.asyncio
async def test_o3_event_uses_vocs_branch(tmp_path):
    runner = RecordingRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="深圳",
        event={"event_id": "evt_o3", "main_pollutant": "O3_8h"},
        event_dir=tmp_path,
        station_records=_station_records(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["main_pollutant_branch"] == "o3"
    output_names = [item["name"] for item in result["component_analysis"]["outputs"]]
    assert output_names == ["calculate_vocs_pmf"]
    vocs_call = [kwargs for name, kwargs in runner.calls if name == "calculate_vocs_pmf"][0]
    assert vocs_call["station_name"] == "高值站"


@pytest.mark.asyncio
async def test_target_station_backfills_coordinates_from_geo_matcher_for_trajectory(tmp_path):
    runner = RecordingRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_o3", "main_pollutant": "O3_8h"},
        event_dir=tmp_path,
        station_records=_station_records_without_coordinates(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["target_station"]["station_name"] == "从化天湖"
    assert result["target_station"]["selection_reason"] == "highest_station_peak_geo_backfill"
    assert result["target_station"]["lat"] == pytest.approx(23.650278)
    assert result["target_station"]["lon"] == pytest.approx(113.624443)
    assert result["trajectory"]["status"] == "success"
    trajectory_call = [kwargs for name, kwargs in runner.calls if name == "meteorological_trajectory_analysis"][0]
    assert trajectory_call["lat"] == pytest.approx(23.650278)
    assert trajectory_call["lon"] == pytest.approx(113.624443)


@pytest.mark.asyncio
async def test_target_station_backfills_latitude_longitude_coordinate_keys(tmp_path):
    runner = RecordingRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="深圳",
        event={"event_id": "evt_no2", "main_pollutant": "NO2"},
        event_dir=tmp_path,
        station_records=_shenzhen_station_records_without_coordinates(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {}},
        fetch_start=datetime(2026, 7, 5, 1),
        fetch_end=datetime(2026, 7, 5, 4),
    )

    assert result["target_station"]["station_name"] == "观澜"
    assert result["target_station"]["selection_reason"] == "highest_station_peak_geo_backfill"
    assert result["target_station"]["lat"] == pytest.approx(22.75)
    assert result["target_station"]["lon"] == pytest.approx(114.085)
    assert result["trajectory"]["status"] == "success"


@pytest.mark.asyncio
async def test_upwind_result_exposes_top_ten_enterprises(tmp_path):
    runner = UpwindRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_o3", "main_pollutant": "O3_8h"},
        event_dir=tmp_path,
        station_records=_station_records_without_coordinates(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    top_enterprises = result["upwind_enterprises"]["top_enterprises"]
    assert len(top_enterprises) == 10
    assert top_enterprises[0] == {
        "rank": 1,
        "station_name": "广雅中学",
        "name": "企业1",
        "industry": "机动车燃油零售",
        "distance_km": 0.1,
        "lat": 23.101,
        "lng": 113.201,
        "hit_ratio": 0.95,
        "score_sum": 99,
        "emissions": {"VOCs": 9.9, "NOx": 0.1},
    }


@pytest.mark.asyncio
async def test_upwind_map_images_are_exposed_from_tool_result(tmp_path):
    runner = UpwindRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_o3", "main_pollutant": "O3_8h"},
        event_dir=tmp_path,
        station_records=_station_records_without_coordinates(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    map_images = result["upwind_enterprises"]["map_images"]
    assert map_images == [
        {
            "station_name": "广雅中学",
            "map_url": "http://example.test/static-link/upwind-map",
            "local_path": "/tmp/upwind_enterprises_1.png",
            "visual_id": "upwind-test",
        }
    ]
    upwind_call = [kwargs for name, kwargs in runner.calls if name == "analyze_upwind_enterprises"][0]
    assert upwind_call["output_dir"] == str(tmp_path / "assets" / "images")


@pytest.mark.asyncio
async def test_enhance_collects_synoptic_weather_images(tmp_path):
    runner = SynopticWeatherRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_o3", "main_pollutant": "O3_8h"},
        event_dir=tmp_path,
        station_records=_station_records_without_coordinates(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 5, 14),
        fetch_end=datetime(2026, 7, 5, 21),
    )

    synoptic = result["synoptic_weather"]
    assert synoptic["status"] == "success"
    assert len(synoptic["images"]) >= 6
    assert {item["analysis_role"] for item in synoptic["images"]} >= {"historical_context", "forecast_outlook"}
    assert all(item["local_path"].endswith(".png") for item in synoptic["images"])
    weather_calls = [kwargs for name, kwargs in runner.calls if name == "get_platform_weather_image"]
    assert {"product": "hourly_wind_field", "date": "20260705", "time": "07", "download": True} in weather_calls
    assert {"product": "precip_forecast_24h", "date": "20260705", "time": "024", "download": True} in weather_calls
    assert (tmp_path / "synoptic_weather_images.json").exists()


@pytest.mark.asyncio
async def test_gas_event_skips_component_models(tmp_path):
    runner = RecordingRunner()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=object(),
        city="佛山",
        event={"event_id": "evt_no2", "main_pollutant": "NO2"},
        event_dir=tmp_path,
        station_records=_station_records(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"pm25_components_data_id": "pm-components", "vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["main_pollutant_branch"] == "gas"
    assert result["component_analysis"]["status"] == "skipped"
    call_names = [name for name, _ in runner.calls]
    assert "calculate_pm_pmf" not in call_names
    assert "calculate_vocs_pmf" not in call_names


@pytest.mark.asyncio
async def test_missing_station_location_records_warning(tmp_path):
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=RecordingRunner())

    result = await enhancer.enhance(
        context=object(),
        city="东莞",
        event={"event_id": "evt_missing", "main_pollutant": "PM10"},
        event_dir=tmp_path,
        station_records=[{"station_name": "无坐标站", "measurements": {"PM10": 200}}],
        weather_records=[],
        component_results={"data_refs": {}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["trajectory"]["status"] == "skipped"
    codes = [item["code"] for item in result["analysis_errors"]]
    assert "missing_station_location" in codes
    assert "missing_weather_data_id" in codes


@pytest.mark.asyncio
async def test_tool_failure_isolated_in_result(tmp_path):
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=FailingRunner())

    result = await enhancer.enhance(
        context=object(),
        city="广州",
        event={"event_id": "evt_fail", "main_pollutant": "O3"},
        event_dir=tmp_path,
        station_records=_station_records(),
        weather_records=[{"weather_data_id": "weather-data"}],
        component_results={"data_refs": {"vocs_components_data_id": "vocs-data"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["trajectory"]["status"] == "failed"
    assert result["upwind_enterprises"]["status"] == "failed"
    assert result["component_analysis"]["status"] == "failed"
    assert result["synoptic_weather"]["status"] == "failed"


def test_real_runner_declares_supported_tool_names():
    enhancer = PollutionEventEvidenceEnhancer()

    assert set(enhancer.supported_tool_names()) >= {
        "meteorological_trajectory_analysis",
        "analyze_upwind_enterprises",
        "calculate_pm_pmf",
        "calculate_reconstruction",
        "calculate_vocs_pmf",
        "get_platform_weather_image",
    }


@pytest.mark.asyncio
async def test_upwind_uses_saved_weather_data_when_records_have_no_data_id(tmp_path):
    runner = RecordingRunner()
    context = SavingContext()
    enhancer = PollutionEventEvidenceEnhancer(tool_runner=runner)

    result = await enhancer.enhance(
        context=context,
        city="广州",
        event={"event_id": "evt_pm", "main_pollutant": "PM2_5"},
        event_dir=tmp_path,
        station_records=_station_records(),
        weather_records=[{"time": "2026-07-04 10:00:00", "wind_speed_10m": 1.2, "wind_direction_10m": 90}],
        component_results={"data_refs": {"pm25_components_data_id": "pm-components"}},
        fetch_start=datetime(2026, 7, 4, 8),
        fetch_end=datetime(2026, 7, 4, 12),
    )

    assert result["upwind_enterprises"]["status"] == "success"
    assert context.saved[0][1] == "pollution_event_weather"
    upwind_call = [kwargs for name, kwargs in runner.calls if name == "analyze_upwind_enterprises"][0]
    assert upwind_call["weather_data_id"] == "saved-weather-data"
