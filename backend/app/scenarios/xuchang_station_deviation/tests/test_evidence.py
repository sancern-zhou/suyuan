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


def _patch_forecast(monkeypatch, collector, *, status="success", nearest=None):
    monkeypatch.setattr(
        collector,
        "_load_forecast_weather",
        lambda event_time: {
            "status": status,
            "source": "XcAiDb.dbo.XuchangNmcHourlyWeatherForecast (NMC 3小时间隔城市预报)",
            "event_time": event_time.isoformat(),
            "nearest_forecast": nearest,
        },
    )


@pytest.mark.asyncio
async def test_collect_combines_source_air_weather_and_precomputed_indicators(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
        forecast_client=_ForecastClient(),
        weather_repo=_WeatherRepo(),
    )
    _patch_forecast(
        monkeypatch,
        collector,
        nearest={"forecast_time": "2026-08-05T14:00:00", "offset_minutes": 60, "wind_speed": 3.3},
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
    assert result["schema_version"].endswith("/v3")
    assert result["source_screening"]["data"]["candidates"][0]["name"] == "企业A"
    assert result["observed_meteorology"]["record_count"] == 2
    assert result["forecast_meteorology"]["status"] == "success"
    assert result["forecast_meteorology"]["nearest_forecast"]["offset_minutes"] == 60
    station_process = result["computed_indicators"]["station_process"]
    assert station_process["changes"][0]["absolute_change"] == 40.0
    assert station_process["target_peer_hourly_comparison"][-1]["deviation_percent"] == 100.0
    assert station_process["current_pollutant_ratios"]["pm25_pm10"] == 0.625
    assert result["collection"]["excluded_data"]["city_air_quality_forecast"].startswith("not_collected")


@pytest.mark.asyncio
async def test_collect_records_partial_evidence_without_losing_source_screening(monkeypatch):
    collector = XuchangStationDeviationEvidenceCollector(
        forecast_client=_ForecastClient(),
        weather_repo=_WeatherRepo(),
    )

    def fail_air_quality(start: datetime, end: datetime):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(collector, "_load_air_quality", fail_air_quality)
    _patch_forecast(monkeypatch, collector)
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
    _patch_forecast(monkeypatch, collector)

    result = await collector.collect(
        alert=_alert(),
        source_screening={"status": "failed", "error": "permit coordinate mapping missing"},
    )

    assert result["collection"]["status"] == "partial"
    assert result["collection"]["errors"] == [
        {"asset": "source_screening", "error": "permit coordinate mapping missing"}
    ]


class _ForecastCursor:
    def __init__(self, rows):
        self.statements = []
        self.parameters = []
        self.description = [
            ("station_id",), ("city_code",), ("city_name",), ("forecast_time",),
            ("publish_time",), ("temperature",), ("humidity",), ("pressure",),
            ("wind_speed",), ("wind_direction",), ("wind_direction_degrees",),
            ("precipitation_probability",), ("precipitation_text",),
            ("weather_code",), ("weather_text",), ("offset_minutes",),
        ]
        self._rows = rows

    def execute(self, statement, params):
        self.statements.append(statement)
        self.parameters.append(params)

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class _ForecastConnection:
    def __init__(self, rows):
        self.cursor_instance = _ForecastCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_collect_loads_nearest_nmc_forecast_row(monkeypatch):
    connection = _ForecastConnection([
        (
            "ZzMTA", "411000", "许昌市",
            datetime(2026, 8, 5, 14, 0), datetime(2026, 8, 5, 10, 25, 53),
            28.6, 83.0, 1002.1, 3.3, "北风", 0.0, 75.7, None, 1, "多云", 60,
        ),
    ])
    collector = XuchangStationDeviationEvidenceCollector(
        connection_string_factory=lambda: "fake-connection-string",
        weather_repo=_WeatherRepo(),
    )
    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.evidence.pyodbc.connect",
        lambda *args, **kwargs: connection,
    )
    monkeypatch.setattr(
        collector,
        "_load_air_quality",
        lambda start, end: {"status": "success", "local_station_hour_records": []},
    )

    result = await collector.collect(alert=_alert(), source_screening={"status": "not_run"})

    forecast = result["forecast_meteorology"]
    assert forecast["status"] == "success"
    assert forecast["nearest_forecast"]["forecast_time"] == "2026-08-05T14:00:00"
    assert forecast["nearest_forecast"]["offset_minutes"] == 60
    assert forecast["nearest_forecast"]["weather_text"] == "多云"
    statement = connection.cursor_instance.statements[0]
    assert "FROM dbo.XuchangNmcHourlyWeatherForecast" in statement
    assert "ORDER BY ABS(DATEDIFF(SECOND, forecast_time, ?))" in statement
    parameters = connection.cursor_instance.parameters[0]
    # 第一个参数用于 DATEDIFF 计算 offset，其后是 ±6h 窗口边界和排序基准。
    assert parameters[0] == datetime(2026, 8, 5, 13, 0)
    assert parameters[1] == datetime(2026, 8, 5, 7, 0)
    assert parameters[2] == datetime(2026, 8, 5, 19, 0)
    assert parameters[3] == datetime(2026, 8, 5, 13, 0)
    assert connection.closed is True


@pytest.mark.asyncio
async def test_collect_reports_empty_forecast_when_table_has_no_nearby_row(monkeypatch):
    connection = _ForecastConnection([])
    collector = XuchangStationDeviationEvidenceCollector(
        connection_string_factory=lambda: "fake-connection-string",
        weather_repo=_WeatherRepo(),
    )
    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.evidence.pyodbc.connect",
        lambda *args, **kwargs: connection,
    )
    monkeypatch.setattr(
        collector,
        "_load_air_quality",
        lambda start, end: {"status": "success", "local_station_hour_records": []},
    )

    result = await collector.collect(alert=_alert(), source_screening={"status": "not_run"})

    assert result["forecast_meteorology"]["status"] == "empty"
    assert result["forecast_meteorology"]["nearest_forecast"] is None
    assert result["collection"]["status"] == "partial"
