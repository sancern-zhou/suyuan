from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.db.models import JiangsuNMCObservedWeatherData
from app.fetchers.weather.jiangsu_nmc_observed_fetcher import (
    JiangsuNMCObservedWeatherFetcher,
    JiangsuNMCStationTarget,
    NMCJiangsuDirectoryStation,
    parse_passedchart_row,
    resolve_station_targets,
)

REGIONS = [
    {
        "area_code": "320100",
        "area_name": "南京市",
        "parent_code": "320000",
        "level": 2,
    },
    {
        "area_code": "320115",
        "area_name": "江宁区",
        "parent_code": "320100",
        "level": 3,
    },
]


def _directory_station(station_id: str, location_name: str) -> NMCJiangsuDirectoryStation:
    return NMCJiangsuDirectoryStation(
        station_id=station_id,
        province_name="江苏省",
        location_name=location_name,
        forecast_url=f"/publish/forecast/AJS/{station_id}.html",
    )


def test_station_directory_is_joined_to_live_city_and_district_hierarchy():
    targets, unmatched = resolve_station_targets(
        [
            _directory_station("CITY", "南京"),
            _directory_station("DISTRICT", "江宁"),
            _directory_station("UNKNOWN", "未知区域"),
        ],
        REGIONS,
    )

    assert unmatched == ["未知区域"]
    assert targets[0].location_level == "city"
    assert targets[0].city_code == "320100"
    assert targets[0].district_code is None
    assert targets[1].location_level == "district"
    assert targets[1].city_name == "南京市"
    assert targets[1].district_code == "320115"
    assert targets[1].district_name == "江宁区"


def test_duplicate_old_and_new_district_codes_use_directory_priority():
    regions = [
        *REGIONS,
        {
            "area_code": "320116",
            "area_name": "江宁市",
            "parent_code": "320100",
            "level": 3,
        },
    ]

    targets, unmatched = resolve_station_targets(
        [_directory_station("DISTRICT", "江宁")],
        regions,
    )

    assert unmatched == []
    assert targets[0].district_code == "320115"


def test_duplicate_nmc_name_can_represent_city_and_same_named_district():
    regions = [
        {
            "area_code": "320800",
            "area_name": "淮安市",
            "parent_code": "320000",
            "level": 2,
        },
        {
            "area_code": "320803",
            "area_name": "淮安区",
            "parent_code": "320800",
            "level": 3,
        },
    ]

    targets, unmatched = resolve_station_targets(
        [
            _directory_station("HUAIAN_CITY", "淮安"),
            _directory_station("HUAIAN_DISTRICT", "淮安"),
        ],
        regions,
    )

    assert unmatched == []
    assert [target.location_level for target in targets] == ["city", "district"]
    assert targets[1].district_name == "淮安区"


def test_passedchart_parser_preserves_china_time_and_nmc_missing_values():
    target = JiangsuNMCStationTarget(
        station_id="DISTRICT",
        province_name="江苏省",
        city_code="320100",
        city_name="南京市",
        district_code="320115",
        district_name="江宁区",
        location_level="district",
        nmc_location_name="江宁",
        forecast_url="/publish/forecast/AJS/jiangning.html",
    )

    record = parse_passedchart_row(
        target,
        {
            "time": "2026-08-13 16:00",
            "temperature": "34.2",
            "humidity": 9999,
            "pressure": 1001,
            "rain1h": 0,
            "windDirection": 180,
            "windSpeed": 2.4,
        },
    )

    assert record.time == datetime(2026, 8, 13, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert record.relative_humidity_2m is None
    assert record.data_quality == "partial"
    assert record.to_dict()["district_name"] == "江宁区"
    assert record.to_dict()["data_source"] == "NMC"


class FakeClient:
    async def fetch_station_directory(self):
        return [
            _directory_station("CITY", "南京"),
            _directory_station("DISTRICT", "江宁"),
        ]

    async def fetch_weather(self, station_id):
        return {
            "code": 0,
            "data": {
                "passedchart": [
                    {
                        "time": "2026-08-13 16:00",
                        "temperature": 34.2,
                        "humidity": 60,
                        "pressure": 1001,
                        "rain1h": 0,
                        "windDirection": 180,
                        "windSpeed": 2.4,
                    }
                ]
            },
        }


class FakeRegionDirectory:
    async def fetch_regions(self):
        return REGIONS


class FakeRepo:
    def __init__(self):
        self.records = []

    async def save_records(self, records):
        self.records.extend(records)
        return len(records)


class FailingRepo:
    async def save_records(self, records):
        raise RuntimeError("database unavailable")


@pytest.mark.asyncio
async def test_fetcher_discovers_city_and_district_stations_and_saves_hourly_rows():
    repo = FakeRepo()
    fetcher = JiangsuNMCObservedWeatherFetcher(
        client=FakeClient(),
        region_directory=FakeRegionDirectory(),
        repo=repo,
        minimum_directory_stations=2,
        max_concurrency=2,
    )

    result = await fetcher.fetch_and_store()

    assert result == {
        "stations_discovered": 2,
        "stations_resolved": 2,
        "city_stations": 1,
        "district_stations": 1,
        "unmatched_locations": [],
        "fetched_rows": 2,
        "saved": 2,
        "skipped_rows": 0,
        "failed_rows": 0,
        "failed_stations": 0,
    }
    assert {record.station.station_id for record in repo.records} == {"CITY", "DISTRICT"}


@pytest.mark.asyncio
async def test_fetcher_fails_cycle_when_every_database_write_fails():
    fetcher = JiangsuNMCObservedWeatherFetcher(
        client=FakeClient(),
        region_directory=FakeRegionDirectory(),
        repo=FailingRepo(),
        minimum_directory_stations=2,
    )

    with pytest.raises(RuntimeError, match="全部写入失败"):
        await fetcher.fetch_and_store()


def test_project_table_uses_administrative_fields_without_fake_coordinates():
    columns = JiangsuNMCObservedWeatherData.__table__.columns

    assert "city_name" in columns
    assert "district_name" in columns
    assert "lat" not in columns
    assert "lon" not in columns
