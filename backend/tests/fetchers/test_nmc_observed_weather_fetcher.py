from datetime import datetime

import pytest
import requests

from app.fetchers.weather.nmc_observed_fetcher import (
    NMC_CITY_STATIONS,
    NMCObservedWeatherFetcher,
    _normalize_nmc_number,
    parse_nmc_passedchart_row,
)


def test_normalize_nmc_number_treats_sentinels_as_none():
    assert _normalize_nmc_number(9999) is None
    assert _normalize_nmc_number("9999.0") is None
    assert _normalize_nmc_number("") is None
    assert _normalize_nmc_number("bad") is None
    assert _normalize_nmc_number("36.4") == 36.4


def test_parse_nmc_passedchart_row_maps_fields_to_observed_data_point():
    station = NMC_CITY_STATIONS["xuchang"]
    row = {
        "time": "2026-07-08 16:00",
        "temperature": 36.4,
        "humidity": 50.0,
        "pressure": 990.0,
        "rain1h": 0.0,
        "rain24h": 9999.0,
        "windDirection": 170.0,
        "windSpeed": 6.6,
    }

    data_point = parse_nmc_passedchart_row(station, row)

    assert data_point.station_id == "ZzMTA"
    assert data_point.station_name == "许昌"
    assert data_point.lat == 34.07
    assert data_point.lon == 113.92
    assert data_point.time == datetime(2026, 7, 8, 16, 0)
    assert data_point.temperature_2m == 36.4
    assert data_point.relative_humidity_2m == 50.0
    assert data_point.surface_pressure == 990.0
    assert data_point.precipitation == 0.0
    assert data_point.wind_direction_10m == 170.0
    assert data_point.wind_speed_10m == 6.6
    assert data_point.data_source == "NMC"
    assert data_point.data_quality == "good"


def test_parse_nmc_passedchart_row_marks_partial_when_core_values_missing():
    station = NMC_CITY_STATIONS["yuncheng"]
    row = {
        "time": "2026-07-08 16:00",
        "temperature": 9999,
        "humidity": "",
        "pressure": 954.0,
        "rain1h": 0.0,
        "windDirection": 160.0,
        "windSpeed": 2.6,
    }

    data_point = parse_nmc_passedchart_row(station, row)

    assert data_point.temperature_2m is None
    assert data_point.relative_humidity_2m is None
    assert data_point.data_quality == "partial"


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.requested_station_ids = []

    def fetch_weather(self, station_id):
        self.requested_station_ids.append(station_id)
        response = self.responses[station_id]
        if isinstance(response, Exception):
            raise response
        return response


class FakeRepo:
    def __init__(self):
        self.saved = []

    async def save_observed_data(self, data_point):
        self.saved.append(data_point)
        return True


@pytest.mark.asyncio
async def test_fetcher_stores_passedchart_rows_for_both_cities():
    client = FakeClient(
        {
            "AupnI": {
                "data": {
                    "passedchart": [
                        {
                            "time": "2026-07-08 15:00",
                            "temperature": 38.6,
                            "humidity": 30.0,
                            "pressure": 955.0,
                            "rain1h": 0.0,
                            "windDirection": 179.0,
                            "windSpeed": 5.7,
                        }
                    ]
                }
            },
            "ZzMTA": {
                "data": {
                    "passedchart": [
                        {
                            "time": "2026-07-08 16:00",
                            "temperature": 36.4,
                            "humidity": 50.0,
                            "pressure": 990.0,
                            "rain1h": 0.0,
                            "windDirection": 170.0,
                            "windSpeed": 6.6,
                        }
                    ]
                }
            },
        }
    )
    repo = FakeRepo()
    stations = {key: NMC_CITY_STATIONS[key] for key in ("yuncheng", "xuchang")}
    fetcher = NMCObservedWeatherFetcher(
        client=client,
        repo=repo,
        stations=stations,
        request_interval_seconds=0,
        max_attempts=1,
    )

    result = await fetcher.fetch_and_store()

    assert result["saved"] == 2
    assert result["failed_cities"] == 0
    assert [point.station_id for point in repo.saved] == ["AupnI", "ZzMTA"]


@pytest.mark.asyncio
async def test_fetcher_continues_when_one_city_fails():
    client = FakeClient(
        {
            "AupnI": RuntimeError("network failed"),
            "ZzMTA": {
                "data": {
                    "passedchart": [
                        {
                            "time": "2026-07-08 16:00",
                            "temperature": 36.4,
                            "humidity": 50.0,
                            "pressure": 990.0,
                            "rain1h": 0.0,
                            "windDirection": 170.0,
                            "windSpeed": 6.6,
                        }
                    ]
                }
            },
        }
    )
    repo = FakeRepo()
    stations = {key: NMC_CITY_STATIONS[key] for key in ("yuncheng", "xuchang")}
    fetcher = NMCObservedWeatherFetcher(
        client=client,
        repo=repo,
        stations=stations,
        request_interval_seconds=0,
        max_attempts=1,
    )

    result = await fetcher.fetch_and_store()

    assert result["saved"] == 1
    assert result["failed_cities"] == 1
    assert [point.station_id for point in repo.saved] == ["ZzMTA"]


def test_henan_nmc_station_catalog_covers_all_prefecture_level_cities():
    henan_stations = {
        station.city: station
        for station in NMC_CITY_STATIONS.values()
        if station.province == "河南省"
    }

    assert set(henan_stations) == {
        "郑州市",
        "开封市",
        "洛阳市",
        "平顶山市",
        "安阳市",
        "鹤壁市",
        "新乡市",
        "焦作市",
        "濮阳市",
        "许昌市",
        "漯河市",
        "三门峡市",
        "南阳市",
        "商丘市",
        "信阳市",
        "周口市",
        "驻马店市",
        "济源市",
    }
    assert henan_stations["郑州市"].station_id == "YVItN"
    assert henan_stations["洛阳市"].url.endswith("/luoyang2.html")


@pytest.mark.asyncio
async def test_fetcher_spaces_requests_and_retries_transient_failures():
    station = NMC_CITY_STATIONS["xuchang"]

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def fetch_weather(self, station_id):
            self.calls += 1
            if self.calls == 1:
                raise requests.ConnectionError("temporary failure")
            return {"data": {"passedchart": []}}

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client = FlakyClient()
    fetcher = NMCObservedWeatherFetcher(
        client=client,
        repo=FakeRepo(),
        stations={"xuchang": station},
        request_interval_seconds=3,
        retry_backoff_seconds=15,
        max_attempts=2,
        sleeper=fake_sleep,
    )

    result = await fetcher.fetch_and_store()

    assert client.calls == 2
    assert sleeps == [15]
    assert result["failed_cities"] == 0


@pytest.mark.asyncio
async def test_fetcher_defers_remaining_cities_after_rate_limit():
    stations = {key: NMC_CITY_STATIONS[key] for key in ("xuchang", "zhengzhou", "kaifeng")}

    class RateLimitedClient:
        def __init__(self):
            self.calls = 0

        def fetch_weather(self, station_id):
            self.calls += 1
            response = requests.Response()
            response.status_code = 429
            raise requests.HTTPError("too many requests", response=response)

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client = RateLimitedClient()
    fetcher = NMCObservedWeatherFetcher(
        client=client,
        repo=FakeRepo(),
        stations=stations,
        request_interval_seconds=3,
        max_attempts=2,
        sleeper=fake_sleep,
    )

    result = await fetcher.fetch_and_store()

    assert client.calls == 1
    assert sleeps == []
    assert result["rate_limited"] == 1
    assert result["failed_cities"] == 1
    assert result["deferred_cities"] == 2
