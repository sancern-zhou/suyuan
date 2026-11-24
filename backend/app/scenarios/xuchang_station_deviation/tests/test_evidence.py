from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.scenarios.xuchang_station_deviation.evidence import (
    XuchangStationDeviationEvidenceCollector,
    _maintenance_qc_review,
)


async def _not_applicable_traffic(alert, event_time):
    return {"status": "not_applicable", "snapshots": []}


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

    def fail_air_quality(start: datetime, end: datetime, alert: dict):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(collector, "_load_air_quality", fail_air_quality)
    monkeypatch.setattr(collector, "_load_traffic", _not_applicable_traffic)
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
    monkeypatch.setattr(collector, "_load_traffic", _not_applicable_traffic)
    monkeypatch.setattr(
        collector,
        "_load_air_quality",
        lambda start, end, alert: {
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


def _minute_row(station_id: str, **marks) -> dict:
    return {"time": "2026-08-05T12:55:00", "station_id": station_id, **marks}


def _hour_row(station_id: str, **marks) -> dict:
    return {"time": "2026-08-05T12:00:00", "station_id": station_id, **marks}


def test_qc_review_matches_alert_station_and_pollutant():
    review = _maintenance_qc_review(
        [
            _minute_row("A", pm25_mark="质控"),
            _minute_row("A", o3_mark="零校准"),  # 同站他因子：不得计入
            _minute_row("B", pm25_mark="质控"),  # 他站：不得计入
        ],
        [_hour_row("A", pm25_mark="零校准")],
        station_id="A",
        field="pm25",
    )

    assert review is not None
    assert [(record["source"], record["time"]) for record in review["records"]] == [
        ("minute", "2026-08-05T12:55:00"),
        ("hour", "2026-08-05T12:00:00"),
    ]
    assert review["station_id"] == "A"
    assert review["pollutant_mark_field"] == "pm25_mark"


def test_qc_review_empty_when_only_other_station_or_other_pollutant_marked():
    assert _maintenance_qc_review(
        [_minute_row("B", pm25_mark="质控"), _minute_row("A", pm10_mark="零校准")],
        [],
        station_id="A",
        field="pm25",
    ) is None


def test_qc_review_ignores_blank_marks_and_hour_only_hits():
    assert _maintenance_qc_review(
        [_minute_row("A", pm25_mark=""), _minute_row("A", pm25_mark=None)],
        [],
        station_id="A",
        field="pm25",
    ) is None

    hour_only = _maintenance_qc_review(
        [],
        [_hour_row("A", no2_mark="质控")],
        station_id="A",
        field="no2",
    )
    assert hour_only is not None
    assert hour_only["records"][0]["source"] == "hour"
