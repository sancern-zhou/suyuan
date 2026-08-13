from datetime import datetime
import pytest

from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    AIR_QUALITY_FORECAST_CITIES,
    DailyForecastTarget,
    HourlyObservation,
    OpenMeteoAirQualityForecastClient,
    OpenMeteoAirQualityForecastFetcher,
    SQLForecastStorage,
    aggregate_daily_pollutants_from_hourly,
    apply_daily_calibration,
    apply_weighted_fusion_with_observation,
    calculate_hourly_aqi,
    calculate_pollutant_shifts_for_target_aqi,
    calculate_primary_pollutant,
    parse_open_meteo_hourly_forecast,
)


def test_calculate_hourly_aqi_uses_max_pollutant_iaqi_and_o3_hourly_standard():
    aqi = calculate_hourly_aqi(
        {
            "pm25": 20.0,
            "pm10": 40.0,
            "o3": 320.0,
            "so2": 10.0,
            "no2": 20.0,
            "co": 600.0,
        }
    )

    assert aqi == 110


def test_calculate_primary_pollutant_returns_none_for_excellent_air():
    assert calculate_primary_pollutant({"pm25": 10.0, "pm10": 15.0}, aqi=30) is None


def test_aggregate_daily_pollutants_uses_24h_averages_and_o3_max_8h_average():
    rows = [
        {
            "pollutants": {
                "pm25": 10.0,
                "pm10": 20.0,
                "o3": float(100 + hour),
                "so2": 5.0,
                "no2": 10.0,
                "co": 500.0,
            }
        }
        for hour in range(24)
    ]

    result = aggregate_daily_pollutants_from_hourly(rows)

    assert result["pm25"] == 10.0
    assert result["pm10"] == 20.0
    assert result["so2"] == 5.0
    assert result["no2"] == 10.0
    assert result["co"] == 500.0
    assert result["o3"] == 119.5


def test_calculate_pollutant_shifts_matches_target_aqi_delta_for_all_pollutants():
    shifts = calculate_pollutant_shifts_for_target_aqi(
        {
            "pm25": 35.0,
            "pm10": 50.0,
            "o3": 100.0,
            "so2": 50.0,
            "no2": 40.0,
            "co": 2000.0,
        },
        target_aqi=70,
        original_aqi=50,
    )

    assert shifts["pm25"] == 16.0
    assert shifts["pm10"] == 40.0
    assert shifts["o3"] == 24.0
    assert shifts["so2"] == 40.0
    assert shifts["no2"] == 16.0
    assert shifts["co"] == 800.0


def test_apply_daily_calibration_moves_daily_aqi_toward_target_range():
    rows = [
        {
            "forecast_time": f"2026-07-10T{hour:02d}:00:00",
            "aqi": 29,
            "pollutants": {
                "pm25": 20.0,
                "pm10": 30.0,
                "o3": 80.0,
                "so2": 5.0,
                "no2": 8.0,
                "co": 500.0,
            },
        }
        for hour in range(24)
    ]
    targets = {
        "运城市": [
            DailyForecastTarget(
                city="运城市",
                forecast_date="2026-07-10",
                min_aqi=80,
                max_aqi=100,
                primary_pollutant="PM2.5",
            )
        ]
    }

    calibrated = apply_daily_calibration(rows, "运城市", targets)

    assert calibrated[0]["process_type"] == "calibrated"
    assert calibrated[0]["daily_shift_value"] > 0
    assert calibrated[0]["pollutants"]["pm25"] > 20.0
    assert calibrated[0]["raw_pollutants"]["pm25"] == 20.0


def test_apply_weighted_fusion_blends_first_12_hours_and_recalculates_aqi():
    rows = [
        {
            "forecast_time": f"2026-07-09T{hour:02d}:00:00",
            "aqi": 20,
            "pollutants": {
                "pm25": 14.0,
                "pm10": 20.0,
                "o3": 80.0,
                "so2": 5.0,
                "no2": 8.0,
                "co": 500.0,
            },
        }
        for hour in (10, 16, 23)
    ]
    observation = HourlyObservation(
        city="运城市",
        time=datetime(2026, 7, 9, 9, 0),
        aqi=100,
        pollutants={"pm25": 75.0, "pm10": 150.0, "o3": 300.0, "so2": 50.0, "no2": 80.0, "co": 2000.0},
    )

    fused = apply_weighted_fusion_with_observation(
        rows,
        observation,
        generated_at=datetime(2026, 7, 9, 10, 0),
    )

    assert fused[0]["fusion"]["observation_weight"] == 0.7
    assert fused[0]["pollutants"]["pm25"] > rows[0]["pollutants"]["pm25"]
    assert fused[1]["fusion"]["observation_weight"] == 0.17
    assert fused[2]["fusion"]["observation_weight"] == 0
    assert fused[2]["pollutants"]["pm25"] == rows[2]["pollutants"]["pm25"]


def test_parse_open_meteo_hourly_forecast_limits_to_72_hours_and_maps_fields():
    payload = {
        "hourly": {
            "time": [f"2026-07-{day:02d}T00:00" for day in range(9, 13)],
            "pm2_5": [20.0, 21.0, 22.0, 23.0],
            "pm10": [40.0, 41.0, 42.0, 43.0],
            "ozone": [180.0, 220.0, 320.0, 330.0],
            "sulphur_dioxide": [8.0, 8.1, 8.2, 8.3],
            "nitrogen_dioxide": [18.0, 18.1, 18.2, 18.3],
            "carbon_monoxide": [600.0, 610.0, 620.0, 630.0],
        }
    }

    rows = parse_open_meteo_hourly_forecast(
        payload,
        city_key="yuncheng",
        city_name="运城市",
        generated_at=datetime(2026, 7, 8, 10, 0),
        max_hours=3,
    )

    assert len(rows) == 3
    assert rows[0]["city"] == "运城市"
    assert rows[0]["forecast_time"] == "2026-07-09T00:00:00"
    assert rows[0]["pollutants"]["pm25"] == 20.0
    assert rows[2]["aqi"] == 110
    assert rows[2]["primary_pollutant"] == "O3"


def test_parse_open_meteo_hourly_forecast_skips_hours_before_generation_time():
    payload = {
        "hourly": {
            "time": [
                "2026-07-09T09:00",
                "2026-07-09T10:00",
                "2026-07-09T11:00",
                "2026-07-09T12:00",
            ],
            "pm2_5": [20.0, 21.0, 22.0, 23.0],
            "pm10": [40.0, 41.0, 42.0, 43.0],
            "ozone": [180.0, 220.0, 320.0, 330.0],
            "sulphur_dioxide": [8.0, 8.1, 8.2, 8.3],
            "nitrogen_dioxide": [18.0, 18.1, 18.2, 18.3],
            "carbon_monoxide": [600.0, 610.0, 620.0, 630.0],
        }
    }

    rows = parse_open_meteo_hourly_forecast(
        payload,
        city_key="xuchang",
        city_name="许昌市",
        generated_at=datetime(2026, 7, 9, 10, 30),
        max_hours=2,
    )

    assert [row["forecast_time"] for row in rows] == [
        "2026-07-09T11:00:00",
        "2026-07-09T12:00:00",
    ]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.headers = {}

    def get(self, url, params, timeout):
        self.requests.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


class FakeSupplementalDataProvider:
    def fetch_daily_targets(self, cities, generated_at):
        return {}

    def fetch_latest_observations(self, cities, generated_at):
        return {}


class FakeForecastStorage:
    table_name = "OpenMeteoAirQualityForecast72h"

    def __init__(self):
        self.calls = []

    def save_forecast(self, **kwargs):
        self.calls.append(kwargs)
        return sum(len(records) for records in kwargs["city_results"].values())


def test_client_requests_open_meteo_air_quality_hourly_forecast():
    session = FakeSession({"hourly": {"time": []}})
    client = OpenMeteoAirQualityForecastClient(session=session)

    client.fetch_city(AIR_QUALITY_FORECAST_CITIES["xuchang"])

    request = session.requests[0]
    assert request["url"] == "https://air-quality-api.open-meteo.com/v1/air-quality"
    assert request["params"]["latitude"] == AIR_QUALITY_FORECAST_CITIES["xuchang"].lat
    assert request["params"]["longitude"] == AIR_QUALITY_FORECAST_CITIES["xuchang"].lon
    assert request["params"]["timezone"] == "Asia/Shanghai"
    assert request["params"]["forecast_days"] == 4
    assert "pm2_5" in request["params"]["hourly"]
    assert "carbon_monoxide" in request["params"]["hourly"]


@pytest.mark.asyncio
async def test_fetcher_stores_forecast_rows_in_database_storage():
    payload = {
        "hourly": {
            "time": ["2026-07-09T10:00", "2026-07-09T11:00", "2026-07-09T12:00"],
            "pm2_5": [20.0, 21.0, 22.0],
            "pm10": [40.0, 41.0, 42.0],
            "ozone": [180.0, 320.0, 330.0],
            "sulphur_dioxide": [8.0, 8.1, 8.2],
            "nitrogen_dioxide": [18.0, 18.1, 18.2],
            "carbon_monoxide": [600.0, 610.0, 620.0],
        }
    }
    client = OpenMeteoAirQualityForecastClient(session=FakeSession(payload))
    storage = FakeForecastStorage()
    fetcher = OpenMeteoAirQualityForecastFetcher(
        client=client,
        data_provider=FakeSupplementalDataProvider(),
        storage=storage,
        generated_at_factory=lambda: datetime(2026, 7, 9, 10, 30),
    )

    result = await fetcher.fetch_and_store()

    assert result["run_id"] == "20260709103000"
    assert result["cities"] == 2
    assert result["forecast_hours"] == 4
    assert result["saved_rows"] == 4
    assert result["table"] == "OpenMeteoAirQualityForecast72h"
    assert "latest_path" not in result
    assert len(storage.calls) == 1
    stored = storage.calls[0]
    assert stored["process_type"] == "update"
    assert stored["calibration_applied"] is False
    assert set(stored["city_results"]) == {"yuncheng", "xuchang"}


def test_sql_storage_builds_forecast_rows_for_insert(monkeypatch):
    executed = []
    inserted = []

    class FakeCursor:
        fast_executemany = False

        def execute(self, sql, *params):
            executed.append((sql, params))

        def executemany(self, sql, rows):
            inserted.append((sql, list(rows)))

        def close(self):
            return None

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class FakeSQLClient:
        connection_string = "DRIVER=fake"

    monkeypatch.setattr(
        "app.fetchers.weather.open_meteo_air_quality_forecast_fetcher.get_sql_server_client",
        lambda: FakeSQLClient(),
    )
    monkeypatch.setattr(
        "app.fetchers.weather.open_meteo_air_quality_forecast_fetcher.pyodbc.connect",
        lambda connection_string, timeout: FakeConnection(),
    )

    storage = SQLForecastStorage()
    saved = storage.save_forecast(
        run_id="20260709083000",
        generated_at=datetime(2026, 7, 9, 8, 30),
        source="open-meteo",
        process_type="calibrated",
        calibration_applied=True,
        cities={"yuncheng": AIR_QUALITY_FORECAST_CITIES["yuncheng"]},
        city_results={
            "yuncheng": [
                {
                    "forecast_time": "2026-07-09T09:00:00",
                    "aqi": 50,
                    "raw_aqi": 45,
                    "aqi_level": {"value": 1, "name": "优"},
                    "primary_pollutant": "PM2.5",
                    "pollutants": {"pm25": 35.0, "pm10": 50.0, "o3": 100.0, "so2": 5.0, "no2": 20.0, "co": 500.0},
                    "raw_pollutants": {"pm25": 30.0, "pm10": 45.0, "o3": 90.0, "so2": 5.0, "no2": 18.0, "co": 480.0},
                    "daily_shift_value": 5,
                    "is_first_forecast": True,
                    "shift_info": {"target_min_aqi": 50, "target_max_aqi": 70, "reason": "test"},
                    "fusion": {"observation_weight": 0.7},
                }
            ]
        },
    )

    assert saved == 1
    assert any("CREATE TABLE" in sql for sql, _ in executed)
    assert any("UX_OpenMeteoAirQualityForecast72h_CityTime" in sql for sql, _ in executed)
    assert len(inserted) == 1
    assert "MERGE dbo.OpenMeteoAirQualityForecast72h" in inserted[0][0]
    assert "target.city_code = src.city_code" in inserted[0][0]
    assert "target.forecast_time = src.forecast_time" in inserted[0][0]
    row = inserted[0][1][0]
    assert row[0] == "20260709083000"
    assert row[6] == "运城市"
    assert row[12] == 50
