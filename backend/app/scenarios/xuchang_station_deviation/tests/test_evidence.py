from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.scenarios.xuchang_station_deviation.evidence import (
    XuchangStationDeviationEvidenceCollector,
)


class _ForecastClient:
    async def fetch_forecast(self, **kwargs):
        return {
            "hourly": {
                "time": [
                    "2026-08-05T04:00:00+00:00",
                    "2026-08-05T05:00:00+00:00",
                    "2026-08-06T05:00:00+00:00",
                    "2026-08-06T06:00:00+00:00",
                ],
                "wind_speed_10m": [1.0, 2.0, 3.0, 4.0],
                "boundary_layer_height": [300, 500, 900, 1000],
            },
            "hourly_units": {"wind_speed_10m": "km/h"},
            "daily": {"time": ["2026-08-05", "2026-08-06"]},
            "daily_units": {},
        }


class _WeatherRepo:
    async def get_observed_data(self, station_id, start_time, end_time):
        return [
            SimpleNamespace(
                time=start_time + timedelta(hours=hour),
                station_id=station_id,
                station_name={"ZzMTA": "许昌", "HFqwM": "禹州", "sHlBF": "长葛"}[station_id],
                lat=34.07,
                lon=113.92,
                temperature_2m=28 + hour,
                relative_humidity_2m=85 - hour,
                wind_speed_10m=1.0 + hour,
                wind_direction_10m=90,
                surface_pressure=1000,
                precipitation=0.1,
                data_source="NMC",
                data_quality="good",
            )
            for hour in range(2)
        ]


def _alert():
    return {
        "event_id": "event-1",
        "occurred_at": "2026-08-05T13:00:00+08:00",
        "lat": 34.07,
        "lon": 113.92,
        "station_id": "A",
        "station_name": "测试站",
        "target_pollutant": "PM2.5",
    }


@pytest.mark.asyncio
async def test_collect_combines_source_air_weather_and_precomputed_indicators(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
        forecast_client=_ForecastClient(),
        weather_repo=_WeatherRepo(),
    )
    event_time = "2026-08-05T13:00:00+08:00"
    previous_time = "2026-08-05T12:00:00+08:00"
    monkeypatch.setattr(
        collector,
        "_load_air_quality",
        lambda start, end: {
            "status": "success",
            "target_city_hour_records": [
                {"time": previous_time, "city": "许昌市", "pm25": 40},
                {"time": event_time, "city": "许昌市", "pm25": 50},
            ],
            "nearby_city_hour_records": [
                {"time": previous_time, "city": "郑州市", "pm25": 30},
                {"time": event_time, "city": "郑州市", "pm25": 35},
            ],
            "local_station_hour_records": [
                {"time": previous_time, "station_id": "A", "pm25": 60, "pm10": 100},
                {"time": previous_time, "station_id": "B", "pm25": 40, "pm10": 80},
                {
                    "time": event_time, "station_id": "A", "pm25": 100, "pm10": 160,
                    "no2": 20, "o3": 100, "so2": 10, "co": 1,
                },
                {"time": event_time, "station_id": "B", "pm25": 50, "pm10": 90},
            ],
        },
    )

    result = await collector.collect(
        alert=_alert(),
        source_screening={"status": "success", "data": {"candidates": [{"name": "企业A"}]}},
    )

    assert result["collection"]["status"] == "complete"
    assert result["schema_version"].endswith("/v2")
    assert result["source_screening"]["data"]["candidates"][0]["name"] == "企业A"
    assert result["observed_meteorology"]["record_count"] == 6
    station_process = result["computed_indicators"]["station_process"]
    assert station_process["changes"][0]["absolute_change"] == 40.0
    assert station_process["target_peer_hourly_comparison"][-1]["deviation_percent"] == 100.0
    assert station_process["current_pollutant_ratios"]["pm25_pm10"] == 0.625
    assert result["collection"]["excluded_data"]["city_air_quality_forecast"].startswith("not_collected")
    assert [row["time"] for row in result["forecast_meteorology"]["hourly"]] == [
        "2026-08-05T13:00:00+08:00",
        "2026-08-06T13:00:00+08:00",
    ]


@pytest.mark.asyncio
async def test_collect_records_partial_evidence_without_losing_source_screening(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
        forecast_client=_ForecastClient(),
        weather_repo=_WeatherRepo(),
    )

    def fail_air_quality(start: datetime, end: datetime):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(collector, "_load_air_quality", fail_air_quality)
    source_screening = {"status": "insufficient_meteorology", "data": {"hourly_meteorology": []}}

    result = await collector.collect(alert=_alert(), source_screening=source_screening)

    assert result["collection"]["status"] == "partial"
    assert result["collection"]["errors"] == [
        {"asset": "air_quality_context", "error": "database unavailable"},
        {
            "asset": "source_screening",
            "error": "source_screening_insufficient_meteorology",
        },
    ]
    assert result["air_quality_context"]["status"] == "failed"
    assert result["source_screening"] == source_screening


@pytest.mark.asyncio
async def test_collect_marks_failed_source_screening_as_partial(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
        forecast_client=_ForecastClient(),
        weather_repo=_WeatherRepo(),
    )
    monkeypatch.setattr(
        collector,
        "_load_air_quality",
        lambda start, end: {
            "status": "success",
            "target_city_hour_records": [],
            "nearby_city_hour_records": [],
            "local_station_hour_records": [],
        },
    )

    result = await collector.collect(
        alert=_alert(),
        source_screening={"status": "failed", "error": "permit coordinate mapping missing"},
    )

    assert result["collection"]["status"] == "partial"
    assert result["collection"]["errors"] == [
        {"asset": "source_screening", "error": "permit coordinate mapping missing"}
    ]
