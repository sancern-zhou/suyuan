import json
from datetime import datetime

import pytest

from app.fetchers.yuncheng_trial.yuncheng_trial_fetcher import YunchengTrialFetcher
from app.scenarios.yuncheng_trial.collect_tracing_context import (
    build_context_manifest,
    collect_required_assets,
    create_air_quality_24h_forecast_payload,
)
from app.scenarios.yuncheng_trial.fetch_and_alert import write_alert_evidence
from app.scenarios.yuncheng_trial.paths import build_evidence_run_paths
from app.tools.query.get_platform_weather_image.tool import build_weather_image_url


def test_build_evidence_run_paths_uses_month_and_capture_timestamp(tmp_path):
    captured_at = datetime(2026, 7, 8, 21, 0, 2)

    paths = build_evidence_run_paths(tmp_path, captured_at)

    assert paths.run_dir == tmp_path / "scenarios" / "yuncheng_trial" / "202607" / "20260708_210002"
    assert paths.alert_path == paths.run_dir / "20260708_210002_alert.json"


def test_write_alert_evidence_writes_named_alert_json_without_global_status_file(tmp_path):
    state = {
        "city": "运城市",
        "checked_at": "2026-07-08T21:00:02+08:00",
        "has_alert": False,
        "status": "silent",
        "summary": "未发现需要推送的告警。",
    }

    alert_path = write_alert_evidence(tmp_path, state)

    assert alert_path.name == "20260708_210002_alert.json"
    assert alert_path.parent.name == "20260708_210002"
    assert alert_path.parent.parent.name == "202607"
    assert len(list((tmp_path / "scenarios" / "yuncheng_trial").glob("*.json"))) == 0
    assert json.loads(alert_path.read_text(encoding="utf-8"))["status"] == "silent"


@pytest.mark.asyncio
async def test_fetcher_keeps_no_alert_evidence_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.fetchers.yuncheng_trial.yuncheng_trial_fetcher.fetch_target_city_hourly_rows",
        lambda **kwargs: [
            {"time": "2026-07-08 18:00:00", "O3": 80, "PM2.5": 20, "PM10": 40, "CO": 0.8, "NO2": 20, "AQI": 40},
            {"time": "2026-07-08 19:00:00", "O3": 78, "PM2.5": 21, "PM10": 41, "CO": 0.8, "NO2": 19, "AQI": 41},
            {"time": "2026-07-08 20:00:00", "O3": 75, "PM2.5": 20, "PM10": 39, "CO": 0.7, "NO2": 18, "AQI": 39},
            {"time": "2026-07-08 21:00:00", "O3": 76, "PM2.5": 19, "PM10": 38, "CO": 0.7, "NO2": 18, "AQI": 38},
        ],
    )

    fetcher = YunchengTrialFetcher(registry_root=tmp_path)
    result = await fetcher.fetch_and_store()

    alert_path = tmp_path / result["alert_path"]
    assert result["has_alert"] is False
    assert result["status"] == "silent"
    assert result["manifest_path"] is None
    assert alert_path.exists()
    assert alert_path.name.endswith("_alert.json")


def test_context_manifest_adds_business_weather_images_with_valid_product_times():
    alert = {
        "alert_id": "yuncheng-20260709-1500-o3",
        "city": "运城市",
        "target_pollutant": "O3",
        "target_time": "2026-07-09 15:00:00",
        "lookback_hours": 6,
    }

    manifest = build_context_manifest(alert)
    assets = manifest["assets"]
    requests = manifest["asset_requests"]

    expected_assets = {
        "visibility_image": "visibility.png",
        "rainfall_24h_image": "rainfall_24h.png",
        "radar_mosaic_image": "radar_mosaic.png",
        "radar_composite_reflectivity_image": "radar_composite_reflectivity_003.png",
        "precipitable_water_image": "precipitable_water_000.png",
        "hourly_precipitation_forecast_image": "hourly_precipitation_forecast.png",
        "national_min_temperature_forecast_image": "national_tmin_forecast.png",
    }
    for asset_name, filename in expected_assets.items():
        assert assets[asset_name] == filename
        request = requests[asset_name]
        assert request["kind"] == "image"
        assert request["tool"] == "get_platform_weather_image"
        build_weather_image_url(
            request["product"],
            date=request["date"],
            time=request["time"],
        )


def test_context_manifest_includes_fire_hotspots_request():
    alert = {
        "alert_id": "yuncheng-20260709-1500-o3",
        "target_time": "2026-07-09 15:00:00",
        "target_pollutant": "O3",
        "lookback_hours": 12,
    }

    manifest = build_context_manifest(alert)
    request = manifest["asset_requests"]["fire_hotspots"]

    assert manifest["assets"]["fire_hotspots"] == "fire_hotspots.json"
    assert manifest["assets"]["fire_hotspots_summary"] == "fire_hotspots_summary.json"
    assert manifest["assets"]["fire_hotspots_map_image"] == "fire_hotspots_map.png"
    assert request["tool"] == "get_fire_hotspots"
    assert request["min_confidence"] == 50
    assert manifest["analysis_window"]["start"] == "2026-07-09 03:00:00"
    assert request["start_time"] == "2026-07-09 09:00:00"
    assert request["end_time"] == "2026-07-09 15:00:00"
    assert request["region"] == {
        "min_lat": 33.5,
        "max_lat": 36.6,
        "min_lon": 109.3,
        "max_lon": 112.7,
    }


def test_context_manifest_requests_open_meteo_air_quality_24h_forecast_without_run_id_filter():
    alert = {
        "alert_id": "yuncheng-20260709-1500-o3",
        "target_time": "2026-07-09 15:00:00",
        "target_pollutant": "O3",
        "lookback_hours": 6,
        "rule_hits": [
            {
                "rule_id": "o3_3h_rising",
                "message": "O3连续3小时上升。",
            }
        ],
    }

    manifest = build_context_manifest(alert)
    request = manifest["asset_requests"]["air_quality_24h_forecast"]
    sql = request["sql"]

    assert manifest["assets"]["air_quality_24h_forecast"] == "air_quality_24h_forecast.json"
    assert request["tool"] == "execute_sql_query"
    assert request["city_code"] == "140800"
    assert request["start_time"] == "2026-07-09 15:00:00"
    assert request["end_time"] == "2026-07-10 15:00:00"
    assert request["triggered_pollutants"] == ["o3"]
    assert "dbo.OpenMeteoAirQualityForecast72h" in sql
    assert "run_id" not in sql.lower()
    assert "forecast_time > '2026-07-09 15:00:00'" in sql
    assert "forecast_time <= '2026-07-10 15:00:00'" in sql
    assert "city_code = N'140800'" in sql


def test_air_quality_24h_payload_keeps_aqi_triggered_pollutants_and_future_threshold_exceedances():
    request = {
        "city": "运城市",
        "city_code": "140800",
        "start_time": "2026-07-09 15:00:00",
        "end_time": "2026-07-10 15:00:00",
        "triggered_pollutants": ["o3"],
        "pollutant_thresholds": {
            "pm25": 75.0,
            "pm10": 150.0,
            "o3": 160.0,
            "no2": 100.0,
            "co": 2.0,
        },
    }
    result = {
        "data": [
            {
                "forecast_time": "2026-07-09 16:00:00",
                "city_name": "运城市",
                "city_code": "140800",
                "aqi": 96,
                "primary_pollutant": "O3",
                "pm25": 30.0,
                "pm10": 80.0,
                "o3": 155.0,
                "no2": 40.0,
                "co": 0.8,
            },
            {
                "forecast_time": "2026-07-09 17:00:00",
                "city_name": "运城市",
                "city_code": "140800",
                "aqi": 118,
                "primary_pollutant": "PM2.5",
                "pm25": 76.0,
                "pm10": 90.0,
                "o3": 150.0,
                "no2": 42.0,
                "co": 0.9,
            },
        ]
    }

    payload = create_air_quality_24h_forecast_payload(result, request)

    assert payload["base_fields"] == ["forecast_time", "city_name", "city_code", "aqi", "primary_pollutant"]
    assert payload["pollutant_fields"] == ["o3", "pm25"]
    assert payload["selection_basis"]["triggered_pollutants"] == ["o3"]
    assert payload["selection_basis"]["threshold_exceeded_pollutants"] == ["pm25"]
    assert payload["rows"] == [
        {
            "forecast_time": "2026-07-09 16:00:00",
            "city_name": "运城市",
            "city_code": "140800",
            "aqi": 96,
            "primary_pollutant": "O3",
            "o3": 155.0,
            "pm25": 30.0,
        },
        {
            "forecast_time": "2026-07-09 17:00:00",
            "city_name": "运城市",
            "city_code": "140800",
            "aqi": 118,
            "primary_pollutant": "PM2.5",
            "o3": 150.0,
            "pm25": 76.0,
        },
    ]


@pytest.mark.asyncio
async def test_collect_required_assets_writes_fire_hotspot_summary_and_map(tmp_path):
    manifest = {
        "assets": {
            "fire_hotspots": "fire_hotspots.json",
            "fire_hotspots_summary": "fire_hotspots_summary.json",
            "fire_hotspots_map_image": "fire_hotspots_map.png",
        },
        "asset_requests": {
            "fire_hotspots": {
                "kind": "json",
                "tool": "get_fire_hotspots",
                "region": {
                    "min_lat": 33.5,
                    "max_lat": 36.6,
                    "min_lon": 109.3,
                    "max_lon": 112.7,
                },
                "start_time": "2026-07-09 09:00:00",
                "end_time": "2026-07-09 15:00:00",
                "min_confidence": 50,
            },
            "fire_hotspots_summary": {
                "kind": "sidecar",
                "source_asset": "fire_hotspots",
            },
            "fire_hotspots_map_image": {
                "kind": "sidecar",
                "source_asset": "fire_hotspots",
            },
        },
        "missing_assets": [],
        "fetch_errors": [],
        "suggested_evidence_gaps": [],
    }

    async def tool_runner(asset_name, request):
        assert asset_name == "fire_hotspots"
        return {
            "success": True,
            "count": 1,
            "hotspots": [
                {
                    "lat": 35.0,
                    "lon": 112.0,
                    "frp": 9.0,
                    "confidence": 70,
                    "acquisition_time": "2026-07-09T13:30:00",
                    "satellite": "N20",
                    "day_night": "D",
                }
            ],
        }

    await collect_required_assets(manifest, tmp_path, tool_runner)

    summary = json.loads((tmp_path / "fire_hotspots_summary.json").read_text(encoding="utf-8"))
    assert (tmp_path / "fire_hotspots.json").exists()
    assert summary["count"] == 1
    assert summary["top_hotspots"][0]["direction"] == "E"
    assert (tmp_path / "fire_hotspots_map.png").stat().st_size > 10_000
