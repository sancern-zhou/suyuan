from datetime import date, datetime

import pytest

from app.fetchers.weather.city_air_quality_forecast_fetcher import (
    CITY_AQ_FORECAST_CITIES,
    CityAirQualityForecastClient,
    CityAirQualityForecastFetcher,
    build_city_forecast_payload,
    normalize_forecast_day,
    parse_current_air_quality_params,
    parse_forecast_7day_params,
    parse_hourly_weather_params,
    parse_trend_24h_params,
)

SAMPLE_PAYLOAD = {
    "current": {
        "aqi": 29,
        "pm25": 14.0,
        "pm10": 29.0,
        "o3": 30.0,
        "so2": 2.0,
        "no2": 19.0,
        "co": 0.5,
        "time": "08/30 00:00",
        "aqiLevel": 1,
        "maxPollution": "",
        "tips": "各类人群可正常活动。",
        "tipsLevel": 1,
        "condition": "雾",
        "temperature": "20",
        "windPowder": "1级",
        "humidity": "96",
        "today": {
            "condition": "雾",
            "minAqi": 30,
            "maxAqi": 50,
            "maxPollution": "",
            "conditionIco": 18,
            "temp": "20~31℃",
            "tips": "各类人群可正常活动。",
            "tipsLevel": 1,
        },
        "tomorrow": {
            "condition": "多云",
            "minAqi": 25,
            "maxAqi": 45,
            "maxPollution": "",
            "conditionIco": 1,
            "temp": "19~28℃",
            "tips": "各类人群可正常活动。",
            "tipsLevel": 1,
        },
    },
    "trendList24aqi": {
        "list": [
            {"time": "01:00", "value": "25", "id": 0},
            {"time": "02:00", "value": "24", "id": 1},
        ]
    },
    "forecastWeatherData7": [
        {
            "dayTitle": "今天",
            "day": "08/30",
            "minAqi": 30,
            "maxAqi": 50,
            "maxPollution": "",
            "condition": "雾",
            "conditionIco": 18,
            "temp": "20~31℃",
            "windLevel": "2",
            "windDir": "西北风",
        },
        {
            "dayTitle": "明天",
            "day": "08/31",
            "minAqi": 25,
            "maxAqi": 45,
            "maxPollution": "",
            "condition": "多云",
            "conditionIco": 1,
            "temp": "19~28℃",
            "windLevel": "2",
            "windDir": "东北风",
        },
    ],
    "hourlys": [
        {"temp": "25°", "time": "00:00", "ico": 2},
        {"temp": "23°", "time": "01:00", "ico": 31},
    ],
    "cityCenterLongitude": 116.407112,
    "cityCenterLatitude": 39.904138,
    "code": 0,
}


def test_city_catalog_covers_nationwide_cities():
    assert len(CITY_AQ_FORECAST_CITIES) == 367
    assert CITY_AQ_FORECAST_CITIES["110000"] == "北京市"
    assert CITY_AQ_FORECAST_CITIES["140800"] == "运城市"
    assert CITY_AQ_FORECAST_CITIES["411000"] == "许昌市"


def test_build_city_forecast_payload_matches_app_protocol():
    payload = build_city_forecast_payload("110000")

    assert payload["params"] == {"cityId": "110000"}
    assert payload["common"]["package_name"] == "com.cnemc.aqi"
    assert payload["common"]["platform"] == "Android"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("08/30", date(2025, 8, 30)),
        ("8.30", date(2025, 8, 30)),
        ("8-30", date(2025, 8, 30)),
        ("12/31", date(2025, 12, 31)),
        ("01/02", date(2026, 1, 2)),
        ("", None),
        ("abc", None),
        ("13/40", None),
    ],
)
def test_normalize_forecast_day_handles_formats_and_year_rollover(value, expected):
    assert normalize_forecast_day(value, date(2025, 8, 30)) == expected


def test_parse_current_air_quality_params_has_symmetric_insert_values():
    params = parse_current_air_quality_params("110000", SAMPLE_PAYLOAD)

    assert params is not None
    assert len(params) == 70
    assert params[0] == "110000"
    assert params[1] == 29
    assert params[17] == 116.407112
    assert params[35] == "110000"
    assert params[:35] == [params[0], *params[1:35]]


def test_parse_current_air_quality_params_returns_none_without_current_block():
    assert parse_current_air_quality_params("110000", {}) is None


def test_parse_forecast_7day_params_builds_rows_and_skips_bad_days():
    payload = {
        "forecastWeatherData7": [
            SAMPLE_PAYLOAD["forecastWeatherData7"][0],
            {"dayTitle": "坏数据", "day": "not-a-date"},
        ]
    }

    rows = parse_forecast_7day_params("110000", "北京市", payload, date(2025, 8, 30))

    assert len(rows) == 1
    city_code, city_name, time_point, day_title, min_aqi, max_aqi = rows[0][:6]
    assert city_code == "110000"
    assert city_name == "北京市"
    assert time_point == datetime(2025, 8, 30, 0, 0, 0)
    assert day_title == "今天"
    assert min_aqi == 30
    assert max_aqi == 50


def test_parse_trend_24h_params_converts_values():
    rows = parse_trend_24h_params("110000", SAMPLE_PAYLOAD)

    assert rows == [
        ("110000", "01:00", 25, 0),
        ("110000", "02:00", 24, 1),
    ]
    assert parse_trend_24h_params("110000", {}) == []


def test_parse_hourly_weather_params_builds_rows():
    rows = parse_hourly_weather_params("110000", SAMPLE_PAYLOAD)

    assert rows == [
        ("110000", "00:00", "25°", 2),
        ("110000", "01:00", "23°", 31),
    ]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if isinstance(self.payload, Exception):
            raise self.payload
        return _FakeResponse(self.payload)


def test_client_fetch_city_returns_payload_on_success():
    session = _FakeSession(SAMPLE_PAYLOAD)
    client = CityAirQualityForecastClient(session=session)

    payload = client.fetch_city("110000")

    assert payload["code"] == 0
    assert session.calls[0]["json"]["params"]["cityId"] == "110000"
    assert session.calls[0]["timeout"] == 30


def test_client_fetch_city_raises_on_error_code():
    client = CityAirQualityForecastClient(session=_FakeSession({"code": 500, "message": "boom"}))

    with pytest.raises(RuntimeError, match="code=500"):
        client.fetch_city("110000")


class _FakeClient:
    def __init__(self, payloads=None, fail_cities=()):
        self.payloads = payloads or dict.fromkeys(["110000", "140800"], SAMPLE_PAYLOAD)
        self.fail_cities = set(fail_cities)
        self.calls = []

    def fetch_city(self, city_id):
        self.calls.append(city_id)
        if city_id in self.fail_cities:
            self.fail_cities.discard(city_id)
            raise RuntimeError(f"transient failure for {city_id}")
        return self.payloads[city_id]


class _FakeStorage:
    def __init__(self):
        self.stored = []
        self.counts = {
            "CurrentAirQuality": 1,
            "AQITrend24H": 2,
            "WeatherForecast7Day": 2,
            "HourlyWeather": 2,
        }

    def store_city(self, city_id, city_name, payload, fetched_at):
        self.stored.append((city_id, city_name))
        return dict(self.counts)

    def close(self):
        pass


async def test_fetcher_stores_all_cities_and_returns_summary():
    storage = _FakeStorage()
    fetcher = CityAirQualityForecastFetcher(
        client=_FakeClient(),
        storage=storage,
        cities={"110000": "北京市", "140800": "运城市"},
        delay_factory=lambda: 0,
    )

    summary = await fetcher.fetch_and_store()

    assert summary["cities"] == 2
    assert summary["total_cities"] == 2
    assert summary["failed_cities"] == 0
    assert summary["saved_rows"] == {
        "CurrentAirQuality": 2,
        "AQITrend24H": 4,
        "WeatherForecast7Day": 4,
        "HourlyWeather": 4,
    }
    assert storage.stored == [("110000", "北京市"), ("140800", "运城市")]


async def test_fetcher_retries_transient_failures():
    client = _FakeClient(fail_cities={"110000"})
    storage = _FakeStorage()
    fetcher = CityAirQualityForecastFetcher(
        client=client,
        storage=storage,
        cities={"110000": "北京市"},
        delay_factory=lambda: 0,
    )

    summary = await fetcher.fetch_and_store()

    assert client.calls.count("110000") == 2
    assert summary["cities"] == 1
    assert summary["failed_cities"] == 0


class _AlwaysFailClient:
    def fetch_city(self, city_id):
        raise RuntimeError("unreachable")


async def test_fetcher_raises_when_all_cities_fail():
    fetcher = CityAirQualityForecastFetcher(
        client=_AlwaysFailClient(),
        storage=_FakeStorage(),
        cities={"110000": "北京市"},
        delay_factory=lambda: 0,
    )

    with pytest.raises(RuntimeError, match="All city air quality forecast fetches failed"):
        await fetcher.fetch_and_store()


def test_fetcher_reports_daily_schedule():
    fetcher = CityAirQualityForecastFetcher(
        client=_FakeClient(),
        storage=_FakeStorage(),
        cities={"110000": "北京市"},
    )

    assert fetcher.name == "city_air_quality_forecast_fetcher"
    assert fetcher.schedule == "30 7 * * *"
    assert fetcher.enabled
