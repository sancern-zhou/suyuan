import pytest

from app.tools.query.get_particulate_components.tool import GetParticulateComponentsTool


class DummyContext:
    def save_data(self, *args, **kwargs):
        raise AssertionError("empty API response should not save data")


class DummyTokenManager:
    def get_auth_headers(self):
        return {"Authorization": "Bearer test"}


class DummyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": {"result": {"resultOne": []}}}


@pytest.mark.asyncio
async def test_locations_station_name_maps_to_component_station_code(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json)
        return DummyResponse()

    monkeypatch.setattr("app.tools.query.get_particulate_components.tool.get_particulate_token_manager", lambda: DummyTokenManager())
    monkeypatch.setattr("requests.post", fake_post)

    result = await GetParticulateComponentsTool().execute(
        context=DummyContext(),
        locations=["公园前"],
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert result["success"] is False
    assert result["station"] == "公园前"
    assert result["code"] == "1006b"
    assert captured["Station"] == "公园前"
    assert captured["Code"] == "1006b"


@pytest.mark.asyncio
async def test_locations_city_is_not_mapped_to_representative_station(monkeypatch):
    def fail_post(*args, **kwargs):
        raise AssertionError("city input should fail before API request")

    monkeypatch.setattr("requests.post", fail_post)

    result = await GetParticulateComponentsTool().execute(
        context=DummyContext(),
        locations=["广州"],
        start_time="2026-07-05 14:00:00",
        end_time="2026-07-05 21:00:00",
    )

    assert result["success"] is False
    assert "resolve_station_geo" in result["error"]
