import pytest


@pytest.mark.asyncio
async def test_resolve_station_geo_returns_station_coordinates(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            assert station_names == ["测试站点"]
            return ["440100A"]

        @classmethod
        def get_station_meta(cls, station_code):
            assert station_code == "440100A"
            return {
                "name": "测试站点",
                "city": "广州",
                "district": "越秀区",
                "lng": 113.2644,
                "lat": 23.1291,
                "address": "测试地址",
                "admin_code": "440104",
                "type_id": 1.0,
            }

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)

    result = await ResolveStationGeoTool().execute(stations=["测试站点"])

    assert result["success"] is True
    station = result["data"]["stations"][0]
    assert station["station_name"] == "测试站点"
    assert station["station_code"] == "440100A"
    assert station["longitude"] == 113.2644
    assert station["latitude"] == 23.1291
    assert station["type_name"] == "国控"


@pytest.mark.asyncio
async def test_resolve_station_geo_reports_unresolved_station(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            return []

        @classmethod
        def get_station_meta(cls, station_code):
            return None

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)

    result = await ResolveStationGeoTool().execute(stations=["不存在站"])

    assert result["success"] is False
    assert result["metadata"]["unresolved_stations"] == ["不存在站"]


@pytest.mark.asyncio
async def test_resolve_station_geo_keeps_directory_station_without_coordinates(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            return ["440100B"]

        @classmethod
        def get_station_meta(cls, station_code):
            assert station_code == "440100B"
            return {
                "name": "缺坐标站",
                "city": "广州",
                "district": "越秀区",
                "lng": None,
                "lat": None,
                "address": "测试地址",
                "admin_code": "440104",
                "type_id": 1.0,
            }

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)

    result = await ResolveStationGeoTool().execute(stations=["缺坐标站"])

    assert result["success"] is True
    station = result["data"]["stations"][0]
    assert station["station_name"] == "缺坐标站"
    assert station["longitude"] is None
    assert station["latitude"] is None


@pytest.mark.asyncio
async def test_resolve_station_geo_expands_regular_stations_by_city(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            return []

        @classmethod
        def resolve_station_codes_by_city(cls, city_names):
            assert city_names == ["广州"]
            return ["1001A", "1002A"]

        @classmethod
        def get_station_meta(cls, station_code):
            return {
                "1001A": {
                    "name": "麓湖",
                    "city": "广州",
                    "district": "越秀区",
                    "lng": 113.285,
                    "lat": 23.145,
                    "address": "麓湖公园",
                    "admin_code": "440104",
                    "type_id": 1.0,
                },
                "1002A": {
                    "name": "广东商学院",
                    "city": "广州",
                    "district": "海珠区",
                    "lng": 113.355,
                    "lat": 23.098,
                    "address": "测试地址",
                    "admin_code": "440105",
                    "type_id": 2.0,
                },
            }.get(station_code)

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)

    result = await ResolveStationGeoTool().execute(cities=["广州"])

    assert result["success"] is True
    assert result["metadata"]["station_count"] == 2
    assert result["metadata"]["query_scope"] == {"cities": ["广州"], "districts": []}
    assert [station["station_name"] for station in result["data"]["stations"]] == ["麓湖", "广东商学院"]
    assert {station["station_category"] for station in result["data"]["stations"]} == {"regular"}


@pytest.mark.asyncio
async def test_resolve_station_geo_expands_regular_stations_by_district(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            return []

        @classmethod
        def resolve_station_codes_by_district(cls, district_names):
            assert district_names == ["南海区"]
            return ["440605001"]

        @classmethod
        def get_station_meta(cls, station_code):
            assert station_code == "440605001"
            return {
                "name": "南海气象局",
                "city": "佛山",
                "district": "南海区",
                "lng": 113.143,
                "lat": 23.029,
                "address": "南海区",
                "admin_code": "440605",
                "type_id": 1.0,
            }

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)

    result = await ResolveStationGeoTool().execute(districts=["南海区"])

    assert result["success"] is True
    assert result["data"]["stations"][0]["station_name"] == "南海气象局"
    assert result["data"]["stations"][0]["district"] == "南海区"


@pytest.mark.asyncio
async def test_resolve_station_geo_resolves_component_stations(monkeypatch):
    from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool

    class FakeResolver:
        @classmethod
        def resolve_station_codes(cls, station_names):
            return []

        @classmethod
        def get_station_meta(cls, station_code):
            return None

    class FakeComponentCatalog:
        def resolve(self, *, station_names, station_codes, cities):
            assert station_names == ["公园前"]
            assert station_codes == []
            assert cities == []
            return [
                {
                    "station_name": "公园前",
                    "station_code": "1006b",
                    "city": "广州",
                    "district": "越秀区",
                    "longitude": 113.2644,
                    "latitude": 23.1291,
                    "address": "测试地址",
                    "admin_code": "440104",
                    "type_id": None,
                    "type_name": "未知",
                    "station_category": "component",
                    "data_domains": ["PM2.5组分", "VOCs"],
                }
            ], [], []

    monkeypatch.setattr("app.tools.query.resolve_station_geo.tool.GeoMappingResolver", FakeResolver)
    monkeypatch.setattr(
        "app.tools.query.resolve_station_geo.tool.get_component_station_catalog",
        lambda: FakeComponentCatalog(),
    )

    result = await ResolveStationGeoTool().execute(stations=["公园前"], station_category="component")

    assert result["success"] is True
    station = result["data"]["stations"][0]
    assert station["station_name"] == "公园前"
    assert station["station_code"] == "1006b"
    assert station["station_category"] == "component"
    assert station["data_domains"] == ["PM2.5组分", "VOCs"]
