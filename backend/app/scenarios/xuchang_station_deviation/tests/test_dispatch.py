import copy
import io
import json
import time
from datetime import datetime

import pytest
from PIL import Image

from app.scenarios.xuchang_station_deviation.dispatch import (
    CONFIG_PATH, MapServiceError, UpwindRoadDispatchBuilder, destination, distance_bearing,
    resolve_station, select_roads, select_wind,
)
from app.scenarios.xuchang_station_deviation.service import XuchangStationDeviationAlertService


@pytest.fixture
def config():
    return json.loads(CONFIG_PATH.read_text())


@pytest.fixture
def alert():
    return {"station_id": "1005A", "station_name": "市一中（启用170929）", "lon": 116.417, "lat": 39.929,
            "target_pollutant": "CO", "occurred_at": "2026-09-09T14:20:00+08:00", "event_id": "event-co"}


@pytest.fixture
def evidence():
    return {"air_quality_context": {"local_station_hour_records": [
        {"station_id": "3134A", "station_name": "市一中", "lon": 113.8172, "lat": 34.0339}]},
        "observed_meteorology": {"station_hour_records": [
            {"station_id": "ZzMTA", "time": "2026-09-09T06:00:00+00:00", "wind_speed_10m": 3,
             "wind_direction_10m": 360, "data_quality": "good"}]}}


def test_resolve_station_rejects_foreign_id_coordinate(alert, evidence):
    rows = evidence["air_quality_context"]["local_station_hour_records"]
    station = resolve_station(alert, rows)
    assert station["canonical_station_id"] == "3134A"
    assert station["longitude"] == 113.8172
    assert resolve_station(alert, []) is None


def test_minute_sql_join_uses_xuchang_name_not_foreign_id(tmp_path):
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    replies = iter([[{"count": 6}], [{"station_id": "3134A", "name": "市一中", "lon": 113.8172, "lat": 34.0339}],
                    [{"count": 6}], [{"station_id": "1005A", "name": "市一中（启用170929）"}]])
    service._query = lambda *args: next(replies)
    rows, _ = service.load_station_rows(datetime(2026, 9, 9, 14, 20))
    assert rows[-1]["station_id"] == "1005A"
    assert rows[-1]["canonical_station_id"] == "3134A"
    assert rows[-1]["lat"] == 34.0339


def test_wind_from_north_utc_and_future_data(config, alert, evidence):
    observed = evidence["observed_meteorology"]
    observed["station_hour_records"].append({"station_id": "ZzMTA", "time": "2026-09-09T07:00:00+00:00",
        "wind_speed_10m": 9, "wind_direction_10m": 180})
    wind = select_wind(observed, alert["occurred_at"], config)
    assert wind["status"] == "success"
    assert wind["wind_from_degrees"] == 0
    assert wind["observation_time"] == "2026-09-09T14:00:00+08:00"


@pytest.mark.parametrize("field,value", [("wind_speed_10m", 0.1), ("wind_direction_10m", 999),
                                         ("wind_direction_10m", "nan"), ("time", "2026-09-08T01:00:00+08:00")])
def test_unusable_wind_never_produces_upwind_sector(config, alert, evidence, field, value):
    evidence["observed_meteorology"]["station_hour_records"][0][field] = value
    wind = select_wind(evidence["observed_meteorology"], alert["occurred_at"], config)
    assert wind["status"] == "unavailable"
    assert "wind_from_degrees" not in wind


def test_shifting_wind_is_not_a_single_direction(config, alert, evidence):
    rows = evidence["observed_meteorology"]["station_hour_records"]
    rows.append({**rows[0], "time": "2026-09-09T05:00:00+00:00", "wind_direction_10m": 180})
    assert select_wind(evidence["observed_meteorology"], alert["occurred_at"], config)["status"] == "unavailable"


def make_poi(station, name, direction, distance):
    lon, lat = destination(station["longitude"], station["latitude"], direction, distance)
    return {"name": name, "location": f"{lon},{lat}", "id": name, "cityname": "许昌市", "typecode": "190301"}


def test_roads_filter_sector_distance_duplicates_and_minor_roads(config):
    station = {"longitude": 113.8172, "latitude": 34.0339}
    pois = [make_poi(station, "许继大道", 359, 1), make_poi(station, "北路", 29, 2.99),
            make_poi(station, "远路", 0, 3.02), make_poi(station, "南路", 180, 1),
            make_poi(station, "后巷", 0, 0.3), make_poi(station, "许继大道", 1, 2),
            make_poi(station, "辅路", 10, 1)]
    roads = select_roads(pois, station, {"wind_from_degrees": 0}, config)
    assert [r["name"] for r in roads] == ["许继大道", "北路"]
    assert roads[0]["distance_km"] == 1
    assert all(r["geometry_type"] == "road_name_poi" for r in roads)
    assert distance_bearing(113.8172,34.0339,*destination(113.8172,34.0339,0,3))[0] == pytest.approx(3)


def test_build_creates_fixed_pm10_circle_png_and_traceable_json_without_credentials(config, alert, evidence, tmp_path):
    alert = {**alert, "target_pollutant": "PM10"}
    builder = UpwindRoadDispatchBuilder(tmp_path, config, api_key="test-secret")
    calls = []
    station = {"longitude": 113.8232, "latitude": 34.0329}
    def request(endpoint, params, deadline, image=False):
        calls.append((endpoint, params))
        if endpoint == "assistant/coordinate/convert":
            return {"locations": "113.8232,34.0329"}
        data = io.BytesIO()
        Image.new("RGB", (900,720), "white").save(data, format="PNG")
        return data.getvalue()
    builder._request = request
    scope = builder.build(alert, evidence)
    assert scope["status"] == "success"
    assert scope["station"]["coordinate_crs"] == "GCJ-02"
    assert scope["roads"] == []
    assert len(list((tmp_path/"charts").glob("*.png"))) == 1
    assert len(list((tmp_path/"road_scopes").glob("*.json"))) == 1
    assert "test-secret" not in json.dumps(scope)
    assert "paths" in calls[-1][1] and "markers" in calls[-1][1]
    with Image.open(scope["upwind_road_scope_image_path"]) as img:
        assert img.width == 900
        assert img.height > 800
    builder.build(alert, evidence)
    assert sum(e == "place/around" for e, _ in calls) == 0


def test_missing_key_degrades_and_keeps_pollutant_dispatch(config, alert, evidence, tmp_path):
    builder = UpwindRoadDispatchBuilder(tmp_path, config, api_key="")
    scope = builder.build({**alert, "target_pollutant": "PM10"}, evidence)
    assert scope["status"] == "unavailable"
    assert scope["roads"] == []
    assert scope["map_status"] == "unavailable"
    assert builder.guidance(alert, scope)["road_names"] == []
    assert "怠速" in "".join(builder.guidance(alert, scope)["actions"])
    for p in ("SO2", "NO2", "O3", "PM2.5", "PM10"):
        assert builder.guidance({**alert, "target_pollutant": p}, scope)["actions"]
    assert builder.build(alert, evidence)["status"] == "not_applicable"


def test_rate_limit_retries_are_bounded(config, tmp_path, monkeypatch):
    builder = UpwindRoadDispatchBuilder(tmp_path, config, api_key="test-secret")
    monkeypatch.setattr("app.scenarios.xuchang_station_deviation.dispatch.time.sleep", lambda _: None)
    calls = []
    def request(*args):
        calls.append(1)
        if len(calls) < 3:
            raise MapServiceError("amap_place_around_10021")
        return {"status": "1"}
    builder._request_once = request
    assert builder._request("place/around", {}, time.monotonic()+30)["status"] == "1"
    assert len(calls) == 3


def test_network_error_does_not_expose_key(config, tmp_path, monkeypatch):
    builder = UpwindRoadDispatchBuilder(tmp_path, config, api_key="test-secret")
    def fail(*args, **kwargs):
        raise ValueError("request url contains key=test-secret")
    monkeypatch.setattr("app.scenarios.xuchang_station_deviation.dispatch.urlopen", fail)
    with pytest.raises(MapServiceError) as error:
        builder._request_once("place/around", {}, time.monotonic()+30)
    assert "test-secret" not in str(error.value)


def test_hourly_factors_keep_separate_evidence_and_combined_media(tmp_path, alert):
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    paths = []
    for pollutant in ("SO2", "CO"):
        item = {"alert": {**alert, "target_pollutant": pollutant, "measurement_granularity": "hour"},
                "evidence": {"dispatch_media": ["map.png", f"{pollutant}.png"]}}
        paths.append(service.write_episode_evidence_package(station_id=alert["station_id"],
            occurred_at=alert["occurred_at"], alerts=[item]))
    assert paths[0] != paths[1]
    assert json.loads(paths[0].read_text())["dispatch_media"] == ["map.png", "SO2.png"]
    assert json.loads(paths[1].read_text())["alerts"][0]["alert"]["target_pollutant"] == "CO"


def test_episode_evidence_envelope_schema_survives_embedded_evidence(tmp_path, alert):
    service = XuchangStationDeviationAlertService(output_root=tmp_path)
    item = {"alert": alert,
            "evidence": {"schema_version": "xuchang_station_deviation_evidence/v3",
                         "dispatch_media": []}}
    path = service.write_episode_evidence_package(
        station_id=alert["station_id"], occurred_at=alert["occurred_at"], alerts=[item])
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == "xuchang_station_deviation_episode_evidence/v1"
    assert payload["station_id"] == alert["station_id"]
    assert payload["alerts"][0]["alert"]["event_id"] == alert["event_id"]


@pytest.mark.asyncio
async def test_fetcher_attaches_same_map_to_two_factors(tmp_path, alert, evidence):
    from app.fetchers.xuchang_station_deviation_alert import XuchangStationDeviationAlertFetcher
    class Builder:
        calls = 0
        def build(self, a, e):
            self.calls += 1
            return {"status": "success", "roads": [{"name": "文峰路"}], "upwind_road_scope_image_path": "map.png",
                    "upwind_road_scope_path": "scope.json"}
        def guidance(self, a, s):
            return {"pollutant": a["target_pollutant"], "road_names": ["文峰路"]}
    builder = Builder()
    fetcher = XuchangStationDeviationAlertFetcher(service=XuchangStationDeviationAlertService(output_root=tmp_path), dispatch_builder=builder)
    scopes = {}
    for p in ("CO", "SO2"):
        a, e = {**alert, "target_pollutant": p, "timeseries_chart_path": f"{p}.png"}, copy.deepcopy(evidence)
        await fetcher._attach_dispatch(a, e, scopes)
        assert e["dispatch_guidance"]["pollutant"] == p
        assert a["upwind_road_scope_image_path"] in e["dispatch_media"]
        assert a["timeseries_chart_path"] in e["dispatch_media"]
        assert e["event"]["upwind_road_scope_path"] == "scope.json"
    assert builder.calls == 1
