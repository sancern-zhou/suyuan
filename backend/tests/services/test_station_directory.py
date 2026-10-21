import time

import pytest

from app.services.station_directory import (
    StaticStationDirectoryProvider,
    StationCategory,
    StationDirectoryCache,
    StationDirectoryNotFound,
    StationDirectoryRegistry,
    StationQuery,
    StationRecord,
    normalize_station_category,
    normalize_station_type,
    station_type_from_row,
)


def test_normalize_station_type_accepts_names_ids_and_aliases():
    assert normalize_station_type("国控") == "国控"
    assert normalize_station_type("national") == "国控"
    assert normalize_station_type(2) == "省控"
    assert normalize_station_type("2.0") == "省控"
    assert normalize_station_type(7) == "背景站"
    assert normalize_station_type("全部") is None
    assert normalize_station_type("全部", allow_all=True) == "全部"
    assert normalize_station_type("regular") is None
    assert normalize_station_type(None) is None


def test_station_type_from_row_prefers_name_then_id():
    assert station_type_from_row({"typeName": "国控"}) == "国控"
    assert station_type_from_row({"stationTypeId": 3}) == "市控"
    assert station_type_from_row({"station_type": "township"}) is None


def test_normalize_station_category_maps_roles():
    assert normalize_station_category("township") == StationCategory.TOWNSHIP.value
    assert normalize_station_category("乡镇站") == StationCategory.TOWNSHIP.value
    assert normalize_station_category("component") == StationCategory.COMPONENT.value
    assert normalize_station_category("regular") == StationCategory.REGULAR.value
    assert normalize_station_category("nonsense") is None


def test_from_mapping_handles_xuchang_catalog_row():
    record = StationRecord.from_mapping(
        {
            "station_code": "1107B",
            "station_name": "长葛市和尚桥镇",
            "district": "长葛市",
            "city": "许昌市",
            "station_type": "township",
            "type_name": "乡镇站",
            "longitude": "113.8019",
            "latitude": "34.2052",
        },
        source="airdata_platform:v_t_d_src",
    )
    assert record.station_code == "1107B"
    assert record.station_category == StationCategory.TOWNSHIP.value
    assert record.station_type == "乡镇控"
    assert record.longitude == pytest.approx(113.8019)
    assert record.source == "airdata_platform:v_t_d_src"
    assert record.as_dict()["type_name"] == "乡镇控"


def test_from_mapping_handles_jiangsu_directory_row():
    record = StationRecord.from_mapping(
        {
            "stationCode": "1005A",
            "positionName": "市一中",
            "cityName": "许昌市",
            "stationType": "国控",
            "longitude": 113.8172,
            "latitude": 34.0339,
            "uniquecode": "411000406",
        }
    )
    assert record.station_type == "国控"
    assert record.unique_code == "411000406"
    assert record.longitude == pytest.approx(113.8172)


def _provider() -> StaticStationDirectoryProvider:
    return StaticStationDirectoryProvider(
        [
            {
                "station_code": "1005A",
                "station_name": "市一中",
                "city": "许昌市",
                "district": "魏都区",
                "station_type": "国控",
                "longitude": 113.8172,
                "latitude": 34.0339,
                "unique_code": "411000406",
            },
            {
                "station_code": "1008A",
                "station_name": "许昌学院",
                "city": "许昌市",
                "district": "东城区",
                "station_type": "国控",
                "longitude": 113.8611,
                "latitude": 34.0443,
            },
            {
                "station_code": "1107B",
                "station_name": "长葛市和尚桥镇",
                "city": "许昌市",
                "district": "长葛市",
                "station_category": "township",
                "station_type": "乡镇控",
                "longitude": 113.8019,
                "latitude": 34.2052,
            },
        ],
        name="test",
    )


@pytest.mark.asyncio
async def test_provider_filters_by_type_and_code():
    provider = _provider()
    national = await provider.list_stations(StationQuery(station_types=("国控",)))
    assert {station.station_code for station in national} == {"1005A", "1008A"}

    by_code = await provider.list_stations(StationQuery(station_codes=("411000406",)))
    assert [station.station_name for station in by_code] == ["市一中"]

    township = await provider.list_stations(StationQuery(station_categories=("township",)))
    assert [station.station_code for station in township] == ["1107B"]


@pytest.mark.asyncio
async def test_provider_resolve_reports_unresolved():
    provider = _provider()
    resolution = await provider.resolve(
        StationQuery.create(station_names=["市一中", "不存在站"], station_codes=["9999Z"])
    )
    assert [station.station_code for station in resolution.stations] == ["1005A"]
    assert resolution.unresolved_names == ["不存在站"]
    assert resolution.unresolved_codes == ["9999Z"]
    assert resolution.success is False


@pytest.mark.asyncio
async def test_provider_get_station_by_unique_code():
    provider = _provider()
    station = await provider.get_station("411000406")
    assert station is not None
    assert station.station_name == "市一中"


@pytest.mark.asyncio
async def test_provider_nearby_sorted_and_filtered():
    provider = _provider()
    nearby = await provider.nearby(34.0339, 113.8172, radius_km=100)
    assert [item.station.station_code for item in nearby] == ["1005A", "1008A", "1107B"]
    assert nearby[0].distance_km == pytest.approx(0.0)
    assert nearby[0].direction == "N"


def test_station_query_create_cleans_and_dedupes():
    query = StationQuery.create(station_names=[" 市一中 ", "市一中", ""], station_codes=["1005A"])
    assert query.station_names == ("市一中",)
    assert query.station_codes == ("1005A",)
    assert query.is_empty is False
    assert StationQuery().is_empty is True


def test_cache_roundtrip_and_expiry(tmp_path):
    cache = StationDirectoryCache("demo", ttl_seconds=60, base_dir=tmp_path)
    assert cache.load() is None
    cache.save({"stations": [{"station_code": "1005A"}]})
    loaded = cache.load()
    assert loaded is not None
    assert loaded["from_cache"] is True
    assert loaded["stations"][0]["station_code"] == "1005A"

    stale = StationDirectoryCache("demo", ttl_seconds=60, base_dir=tmp_path)
    stale.save({"stations": []}, generated_at=time.time() - 3600)
    assert stale.load() is None

    cache.clear()
    assert cache.load() is None


def test_registry_binds_providers_to_projects():
    registry = StationDirectoryRegistry()
    default_provider = StaticStationDirectoryProvider([], name="default")
    xuchang_provider = StaticStationDirectoryProvider([], name="xuchang")

    registry.register(default_provider, default=True)
    registry.register(xuchang_provider, projects=["xuchang-air-quality"])

    assert registry.for_project("xuchang-air-quality") is xuchang_provider
    assert registry.for_project("unknown") is default_provider
    assert registry.get("xuchang") is xuchang_provider
    assert registry.names() == ("default", "xuchang")

    with pytest.raises(StationDirectoryNotFound):
        registry.get("missing")

    registry.clear()
    assert registry.for_project("xuchang-air-quality") is None
