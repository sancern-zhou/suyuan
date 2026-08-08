import pytest


class FakeMatcher:
    def __init__(self):
        self.codes = {"公园前": "1006b", "南沙科大": "1007b"}

    def stations_to_codes(self, names):
        codes = []
        for name in names:
            if name not in self.codes:
                raise ValueError(f"组分站点 '{name}' 不在组分站点映射表中。")
            codes.append(self.codes[name])
        return codes


class DummyContext:
    def save_data(self, *args, **kwargs):
        raise AssertionError("API failure should not save data")


@pytest.mark.asyncio
async def test_pm25_ionic_maps_station_name_but_not_city(monkeypatch):
    from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool

    captured = {}

    class FakeClient:
        def get_ionic_analysis(self, **kwargs):
            captured.update(kwargs)
            return {"success": False, "error": "stop"}

    monkeypatch.setattr("app.tools.query.get_pm25_ionic.tool.get_particulate_geo_matcher", lambda: FakeMatcher())
    monkeypatch.setattr("app.tools.query.get_pm25_ionic.tool.get_particulate_api_client", lambda: FakeClient())

    station_result = await GetPM25IonicTool().execute(
        context=DummyContext(),
        station="公园前",
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert station_result["station"] == "公园前"
    assert station_result["code"] == "1006b"
    assert captured["station"] == "公园前"
    assert captured["code"] == "1006b"

    city_result = await GetPM25IonicTool().execute(
        context=DummyContext(),
        locations=["广州"],
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert city_result["success"] is False
    assert "广州" in city_result["error"]


@pytest.mark.asyncio
async def test_pm25_carbon_maps_station_name_without_city_mapping(monkeypatch):
    from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool

    captured = {}

    class FakeClient:
        def get_carbon_components(self, **kwargs):
            captured.update(kwargs)
            return {"success": False, "error": "stop"}

    monkeypatch.setattr("app.tools.query.get_pm25_carbon.tool.get_particulate_geo_matcher", lambda: FakeMatcher())
    monkeypatch.setattr("app.tools.query.get_pm25_carbon.tool.get_particulate_api_client", lambda: FakeClient())

    result = await GetPM25CarbonTool().execute(
        context=DummyContext(),
        station="南沙科大",
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert result["station"] == "南沙科大"
    assert result["code"] == "1007b"
    assert captured["station"] == "南沙科大"
    assert captured["code"] == "1007b"


@pytest.mark.asyncio
async def test_pm25_crustal_maps_station_name_without_city_mapping(monkeypatch):
    from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool

    captured = {}

    class FakeClient:
        def get_heavy_metal_analysis(self, **kwargs):
            captured.update(kwargs)
            return {"success": False, "error": "stop"}

    monkeypatch.setattr("app.tools.query.get_pm25_crustal.tool.get_particulate_geo_matcher", lambda: FakeMatcher())
    monkeypatch.setattr("app.tools.query.get_pm25_crustal.tool.get_particulate_api_client", lambda: FakeClient())

    result = await GetPM25CrustalTool().execute(
        context=DummyContext(),
        station="公园前",
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert result["station"] == "公园前"
    assert result["code"] == "1006b"
    assert captured["station"] == "公园前"
    assert captured["code"] == "1006b"


@pytest.mark.asyncio
async def test_vocs_maps_station_name_without_city_mapping(monkeypatch):
    from app.tools.query.get_vocs_data.tool_api import GetVOCsDataTool

    captured = {}

    class FakeClient:
        def get_voc_categories(self, **kwargs):
            captured.update(kwargs)
            return {"success": False, "error": "stop"}

    monkeypatch.setattr("app.tools.query.get_vocs_data.tool_api.get_particulate_geo_matcher", lambda: FakeMatcher())
    monkeypatch.setattr("app.tools.query.get_vocs_data.tool_api.get_voc_api_client", lambda: FakeClient())

    result = await GetVOCsDataTool().execute(
        context=DummyContext(),
        station="公园前",
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert result["station"] == "公园前"
    assert result["code"] == "1006b"
    assert captured["station_code"] == "1006b"
