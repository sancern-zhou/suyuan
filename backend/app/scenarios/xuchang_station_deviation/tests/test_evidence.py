from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.scenarios.xuchang_station_deviation.evidence import (
    XuchangStationDeviationEvidenceCollector,
)


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
async def test_collect_records_partial_evidence_without_losing_source_screening(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
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
