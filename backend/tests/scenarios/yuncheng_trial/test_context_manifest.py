import json
from datetime import datetime
from pathlib import Path

import pytest

from app.scenarios.yuncheng_trial.collect_tracing_context import (
    REQUIRED_ASSETS,
    build_context_manifest,
    collect_required_assets,
    create_tool_request,
    default_tool_runner,
)
from app.scenarios.yuncheng_trial.config import YUNCHENG_TRIAL_CONFIG
from app.scenarios.yuncheng_trial.paths import build_alert_run_dir


def test_yuncheng_config_has_target_and_nearby_cities():
    assert YUNCHENG_TRIAL_CONFIG.city == "运城市"
    assert "临汾市" in YUNCHENG_TRIAL_CONFIG.nearby_cities
    assert "三门峡市" in YUNCHENG_TRIAL_CONFIG.nearby_cities
    assert YUNCHENG_TRIAL_CONFIG.default_lookback_hours == 6
    assert YUNCHENG_TRIAL_CONFIG.fetch_station_data_first_version is False
    assert YUNCHENG_TRIAL_CONFIG.o3_watch_level == 160.0
    assert YUNCHENG_TRIAL_CONFIG.lat == 35.0228
    assert YUNCHENG_TRIAL_CONFIG.lon == 111.0075
    assert len(YUNCHENG_TRIAL_CONFIG.weather_city_code) == 9


def test_build_alert_run_dir_uses_date_and_hour():
    root = Path("/tmp/registry")
    result = build_alert_run_dir(root, "2026-07-07 09:00:00")
    assert result == root / "scenarios" / "yuncheng_trial" / "20260707" / "0900"


def test_build_context_manifest_lists_required_assets():
    alert = {
        "alert_id": "yuncheng-20260707-0900-o3-rise",
        "city": "运城市",
        "target_pollutant": "O3",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    }

    manifest = build_context_manifest(alert)

    assert manifest["alert_id"] == "yuncheng-20260707-0900-o3-rise"
    assert manifest["analysis_window"]["start"] == "2026-07-07 03:00:00"
    assert manifest["analysis_window"]["end"] == "2026-07-07 09:00:00"
    assert set(REQUIRED_ASSETS).issubset(manifest["assets"])
    assert manifest["fetch_errors"] == []
    assert manifest["suggested_evidence_gaps"] == []
    assert manifest["limitations"]


def test_create_tool_request_maps_assets_to_existing_tools():
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-o3-rise",
        "city": "运城市",
        "target_pollutant": "O3",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })

    target_request = create_tool_request(manifest, "target_city_pollutants")
    nearby_request = create_tool_request(manifest, "nearby_city_pollutants")
    trajectory_request = create_tool_request(manifest, "trajectory_analysis")
    forecast_request = create_tool_request(manifest, "forecast_meteorology")
    meteorology_request = create_tool_request(manifest, "meteorology_history")
    wind_request = create_tool_request(manifest, "hourly_wind_field_image")
    precip_request = create_tool_request(manifest, "precipitation_forecast_image")
    wind_forecast_24h_request = create_tool_request(manifest, "wind_forecast_24h_image")
    precip_forecast_24h_request = create_tool_request(manifest, "precipitation_forecast_24h_image")

    assert target_request["tool"] == "query_xcai_city_history"
    assert target_request["cities"] == ["运城市"]
    assert nearby_request["cities"] == YUNCHENG_TRIAL_CONFIG.nearby_cities
    assert trajectory_request["tool"] == "meteorological_trajectory_analysis"
    assert trajectory_request["kind"] == "trajectory_analysis"
    assert trajectory_request["lat"] == YUNCHENG_TRIAL_CONFIG.lat
    assert trajectory_request["lon"] == YUNCHENG_TRIAL_CONFIG.lon
    assert trajectory_request["start_time"] == "2026-07-07 09:00:00"
    assert trajectory_request["hours"] == 72
    assert trajectory_request["heights"] == [10, 500, 1000]
    assert trajectory_request["direction"] == "Backward"
    assert meteorology_request["tool"] == "get_weather_forecast"
    assert meteorology_request["past_days"] == 1
    assert meteorology_request["forecast_days"] == 1
    assert wind_request["date"] == "20260707"
    assert wind_request["time"] == "01"
    assert precip_request["date"] == "20260706"
    assert precip_request["time"] == "025"
    assert wind_forecast_24h_request["product"] == "max_10m_wind_speed_24h"
    assert wind_forecast_24h_request["date"] == "20260706"
    assert wind_forecast_24h_request["time"] == "024"
    assert precip_forecast_24h_request["product"] == "precip_forecast_24h"
    assert precip_forecast_24h_request["date"] == "20260706"
    assert precip_forecast_24h_request["time"] == "024"
    assert forecast_request["tool"] == "get_weather_forecast"
    assert forecast_request["forecast_days"] == 5


def test_platform_weather_image_requests_use_published_utc_time_slots():
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260708-1000-o3",
        "city": "运城市",
        "target_pollutant": "O3",
        "target_time": "2026-07-08 10:00:00",
        "lookback_hours": 6,
    })

    wind_request = create_tool_request(manifest, "hourly_wind_field_image")
    precip_request = create_tool_request(manifest, "precipitation_forecast_image")
    wind_forecast_requests = [
        create_tool_request(manifest, "wind_forecast_24h_image"),
        create_tool_request(manifest, "wind_forecast_48h_image"),
        create_tool_request(manifest, "wind_forecast_72h_image"),
    ]
    precip_forecast_requests = [
        create_tool_request(manifest, "precipitation_forecast_24h_image"),
        create_tool_request(manifest, "precipitation_forecast_48h_image"),
        create_tool_request(manifest, "precipitation_forecast_72h_image"),
    ]

    assert wind_request["date"] == "20260708"
    assert wind_request["time"] == "02"
    assert precip_request["date"] == "20260707"
    assert precip_request["time"] == "026"
    assert [request["product"] for request in wind_forecast_requests] == [
        "max_10m_wind_speed_24h",
        "max_10m_wind_speed_24h",
        "max_10m_wind_speed_24h",
    ]
    assert [request["date"] for request in wind_forecast_requests] == [
        "20260707",
        "20260707",
        "20260707",
    ]
    assert [request["time"] for request in wind_forecast_requests] == ["024", "048", "072"]
    assert [request["product"] for request in precip_forecast_requests] == [
        "precip_forecast_24h",
        "precip_forecast_24h",
        "precip_forecast_24h",
    ]
    assert [request["date"] for request in precip_forecast_requests] == [
        "20260707",
        "20260707",
        "20260707",
    ]
    assert [request["time"] for request in precip_forecast_requests] == ["024", "048", "072"]


def test_default_tool_runner_is_importable():
    assert callable(default_tool_runner)


@pytest.mark.asyncio
async def test_collect_required_assets_records_missing_sources(tmp_path):
    source_trajectory = tmp_path / "source_trajectory.png"
    source_trajectory.write_bytes(b"TRAJECTORYPNG")
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-o3-rise",
        "city": "运城市",
        "target_pollutant": "O3",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })

    async def fake_tool_runner(asset_name, request):
        if asset_name == "hourly_wind_field_image":
            return {"success": False, "error": "tool returned no file"}
        if asset_name == "trajectory_analysis":
            return {
                "success": True,
                "data": {"asset": asset_name, "request": request},
                "visuals": [{"payload": {"local_path": str(source_trajectory)}}],
            }
        if request["kind"] == "image":
            return {"success": True, "content": b"PNGDATA"}
        return {"success": True, "data": {"asset": asset_name, "request": request}}

    manifest_path = await collect_required_assets(
        manifest=manifest,
        output_dir=tmp_path,
        tool_runner=fake_tool_runner,
    )

    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (tmp_path / "target_city_pollutants.json").exists()
    assert (tmp_path / "trajectory.png").exists()
    assert "hourly_wind_field_image" in saved_manifest["missing_assets"]
    assert saved_manifest["fetch_errors"][0]["source"] == "hourly_wind_field_image"
    assert saved_manifest["suggested_evidence_gaps"][0]["evidence"] == "hourly_wind_field_image"


@pytest.mark.asyncio
async def test_collect_required_assets_serializes_datetime_payloads(tmp_path):
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-aqi",
        "city": "运城市",
        "target_pollutant": "AQI",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })
    manifest["assets"] = {"forecast_meteorology": "forecast_meteorology.json"}
    manifest["asset_requests"] = {
        "forecast_meteorology": {
            "kind": "json",
            "tool": "get_weather_forecast",
        }
    }

    async def fake_tool_runner(asset_name, request):
        return {
            "success": True,
            "data": [{"timestamp": datetime(2026, 7, 7, 9), "temperature": 30.0}],
        }

    await collect_required_assets(
        manifest=manifest,
        output_dir=tmp_path,
        tool_runner=fake_tool_runner,
    )

    payload = json.loads((tmp_path / "forecast_meteorology.json").read_text(encoding="utf-8"))
    assert payload[0]["timestamp"] == "2026-07-07T09:00:00"


@pytest.mark.asyncio
async def test_collect_required_assets_persists_full_context_data_when_tool_returns_preview(tmp_path):
    full_records = [{"timestamp": f"2026-07-07 {hour:02d}:00:00", "city": "临汾市"} for hour in range(35)]
    preview_records = full_records[:24]
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-aqi",
        "city": "运城市",
        "target_pollutant": "AQI",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })
    manifest["assets"] = {"nearby_city_pollutants": "nearby_city_pollutants.json"}
    manifest["asset_requests"] = {
        "nearby_city_pollutants": {
            "kind": "json",
            "tool": "query_xcai_city_history",
        }
    }

    async def fake_tool_runner(asset_name, request):
        return {
            "success": True,
            "data": preview_records,
            "metadata": {
                "data_id": "full-nearby-city-data",
                "total_records": len(full_records),
                "returned_records": len(preview_records),
            },
        }

    class FakeContext:
        def get_data(self, data_id):
            assert data_id == "full-nearby-city-data"
            return full_records

    await collect_required_assets(
        manifest=manifest,
        output_dir=tmp_path,
        tool_runner=fake_tool_runner,
        data_context=FakeContext(),
    )

    payload = json.loads((tmp_path / "nearby_city_pollutants.json").read_text(encoding="utf-8"))
    assert len(payload) == 35
    assert payload == full_records


@pytest.mark.asyncio
async def test_collect_required_assets_copies_image_from_tool_data_local_path(tmp_path):
    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"PNGDATA")
    output_dir = tmp_path / "context"
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-aqi",
        "city": "运城市",
        "target_pollutant": "AQI",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })
    manifest["assets"] = {"hourly_wind_field_image": "wind_field.png"}
    manifest["asset_requests"] = {
        "hourly_wind_field_image": {
            "kind": "image",
            "tool": "get_platform_weather_image",
        }
    }

    async def fake_tool_runner(asset_name, request):
        return {
            "success": True,
            "data": {
                "local_path": str(source_image),
            },
        }

    await collect_required_assets(
        manifest=manifest,
        output_dir=output_dir,
        tool_runner=fake_tool_runner,
    )

    assert (output_dir / "wind_field.png").read_bytes() == b"PNGDATA"
    saved_manifest = json.loads((output_dir / "tracing_context_manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["missing_assets"] == []


@pytest.mark.asyncio
async def test_collect_required_assets_saves_local_trajectory_analysis_and_image(tmp_path):
    source_image = tmp_path / "source_trajectory.png"
    source_image.write_bytes(b"TRAJECTORYPNG")
    manifest = build_context_manifest({
        "alert_id": "yuncheng-20260707-0900-aqi",
        "city": "运城市",
        "target_pollutant": "AQI",
        "target_time": "2026-07-07 09:00:00",
        "lookback_hours": 6,
    })
    manifest["assets"] = {
        "trajectory_analysis": "trajectory_analysis.json",
        "trajectory_image": "trajectory.png",
    }
    manifest["asset_requests"] = {
        "trajectory_analysis": {
            "kind": "trajectory_analysis",
            "tool": "meteorological_trajectory_analysis",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "start_time": "2026-07-07 09:00:00",
            "hours": 72,
            "heights": [10, 500, 1000],
            "direction": "Backward",
        },
        "trajectory_image": {
            "kind": "sidecar",
            "source_asset": "trajectory_analysis",
        },
    }

    async def fake_tool_runner(asset_name, request):
        return {
            "success": True,
            "summary": "trajectory ok",
            "dominant_direction": "西南",
            "trajectory_data": {"endpoints": [{"lat": 35.0, "lon": 111.0}]},
            "visuals": [
                {
                    "payload": {
                        "local_path": str(source_image),
                    }
                }
            ],
        }

    await collect_required_assets(
        manifest=manifest,
        output_dir=tmp_path / "context",
        tool_runner=fake_tool_runner,
    )

    analysis = json.loads((tmp_path / "context" / "trajectory_analysis.json").read_text(encoding="utf-8"))
    assert analysis["dominant_direction"] == "西南"
    assert (tmp_path / "context" / "trajectory.png").read_bytes() == b"TRAJECTORYPNG"
    saved_manifest = json.loads((tmp_path / "context" / "tracing_context_manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["missing_assets"] == []


@pytest.mark.asyncio
async def test_default_tool_runner_runs_local_backward_trajectory(monkeypatch):
    calls = []

    class FakeMeteorologicalTrajectoryAnalysisTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {"success": True, "data": [], "visuals": []}

    import app.tools.analysis.meteorological_trajectory_analysis.tool as trajectory_tool

    monkeypatch.setattr(
        trajectory_tool,
        "MeteorologicalTrajectoryAnalysisTool",
        FakeMeteorologicalTrajectoryAnalysisTool,
    )

    await default_tool_runner(
        "trajectory_analysis",
        {
            "tool": "meteorological_trajectory_analysis",
            "lat": YUNCHENG_TRIAL_CONFIG.lat,
            "lon": YUNCHENG_TRIAL_CONFIG.lon,
            "start_time": "2026-07-07 09:00:00",
            "hours": 72,
            "heights": [10, 500, 1000],
            "direction": "Backward",
        },
    )

    assert calls[0]["lat"] == YUNCHENG_TRIAL_CONFIG.lat
    assert calls[0]["lon"] == YUNCHENG_TRIAL_CONFIG.lon
    assert calls[0]["start_time"] == "2026-07-07 09:00:00"
    assert calls[0]["hours"] == 72
    assert calls[0]["heights"] == [10, 500, 1000]
    assert calls[0]["direction"] == "Backward"


@pytest.mark.asyncio
async def test_default_tool_runner_queries_air_quality_24h_forecast(monkeypatch):
    calls = []

    class FakeExecuteSQLQueryTool:
        async def execute(self, context, sql, database, limit):
            calls.append({
                "context": context,
                "sql": sql,
                "database": database,
                "limit": limit,
            })
            return {"success": True, "data": []}

    import app.tools.query.execute_sql_query.tool as execute_sql_tool

    monkeypatch.setattr(execute_sql_tool, "ExecuteSQLQueryTool", FakeExecuteSQLQueryTool)

    await default_tool_runner(
        "air_quality_24h_forecast",
        {
            "tool": "execute_sql_query",
            "sql": (
                "SELECT forecast_time, city_name, city_code, aqi, primary_pollutant, "
                "pm25, pm10, o3, no2, co "
                "FROM dbo.OpenMeteoAirQualityForecast72h "
                "WHERE city_code = N'140800' "
                "AND forecast_time > '2026-07-07 09:00:00' "
                "AND forecast_time <= '2026-07-08 09:00:00' "
                "ORDER BY forecast_time"
            ),
            "database": "XcAiDb",
            "limit": 100,
        },
    )

    assert calls[0]["database"] == "XcAiDb"
    assert calls[0]["limit"] == 100
    assert "dbo.OpenMeteoAirQualityForecast72h" in calls[0]["sql"]
    assert "city_code = N'140800'" in calls[0]["sql"]
    assert "forecast_time > '2026-07-07 09:00:00'" in calls[0]["sql"]
    assert "forecast_time <= '2026-07-08 09:00:00'" in calls[0]["sql"]
