import json
import logging
import asyncio

import httpx
import pytest

from app.fetchers.weather.jiangsu_review_weather import fetch_city_weather
from app.fetchers.weather import jiangsu_review_weather as weather_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(weather_module, 'get_data_registry', lambda: tmp_path)


def row(time="2026-09-01T00:00:00", **kwargs):
    return {"stationCode": "101190101", "stationName": "南京", "cityName": "南京市",
            "timePoint": time, "temperature": "25", "humidity": "90",
            "windDirection": 9999, "windSpeed": "0", **kwargs}


@pytest.mark.asyncio
async def test_city_station_selection_filters_districts_times_and_preserves_missing(monkeypatch):
    monkeypatch.setenv("SUNCERE_WEATHER_TOKEN", "test-secret")
    monkeypatch.setenv("JIANGSU_REVIEW_WEATHER_STATIONS", json.dumps({'南京市': '101190101'}))
    def handler(request):
        assert request.url.params["beginTime"] == "2026-09-01 00:00:00"
        return httpx.Response(200, json={"code": 200, "dataList": [
            row(), row(), row(stationName="江宁", stationCode="district"),
            row(cityName="苏州市"), row("2026-08-31T23:00:00"),
            row("2026-09-01T02:00:00", temperature="--", humidity="9999"),
        ]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_city_weather(city_name="南京市", start_time="2026-09-01 00:00:00", end_time="2026-09-01 02:59:59", client=client)
    assert result["station_code"] == "101190101"
    assert result["record_count"] == 2
    assert result["status"] == "partial"
    assert result["missing_hours"] == ["2026-09-01T01:00:00"]
    assert result["data"][0]["windDirection"] is None
    assert result["data"][0]["windSpeed"] == 0
    assert result["data"][1]["temperature"] is None


@pytest.mark.asyncio
async def test_chunk_failure_retries_hourly_and_redacts_secret(monkeypatch):
    monkeypatch.setenv("SUNCERE_WEATHER_TOKEN", "test-secret")
    monkeypatch.setenv("JIANGSU_REVIEW_WEATHER_STATIONS", json.dumps({"南京市": "101190101"}))
    requests = []
    def handler(request):
        left, right = request.url.params["beginTime"], request.url.params["endTime"]
        requests.append((left, right))
        if left != right:
            return httpx.Response(413)
        if left.endswith("01:00:00"):
            return httpx.Response(403)
        return httpx.Response(200, json={"code": 200, "dataList": [row(left)]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_city_weather(city_name="南京市", start_time="2026-09-01 00:00:00", end_time="2026-09-01 12:59:59", client=client)
    assert requests[0] == ("2026-09-01 00:00:00", "2026-09-01 11:00:00")
    assert result["expected_hours"] == 13
    assert result["record_count"] == 12
    assert len(result["gaps"]) == 1
    assert "test-secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_available_same_city_station_selected_and_named(monkeypatch):
    monkeypatch.setenv("SUNCERE_WEATHER_TOKEN", "test-secret")
    monkeypatch.delenv("JIANGSU_REVIEW_WEATHER_STATIONS", raising=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "code": 200, "dataList": [row(stationName="江宁", stationCode="district")]
    }))) as client:
        result = await fetch_city_weather(city_name="南京市", start_time="2026-09-01 00:00:00", end_time="2026-09-01 00:00:00", client=client)
    assert result["status"] == "partial"
    assert result["station_code"] == "district"
    assert result['station_name'] == '江宁'
    assert result['station_candidates'][0]['station_code'] == 'district'
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_missing_configuration_does_not_request(monkeypatch):
    monkeypatch.delenv("SUNCERE_WEATHER_TOKEN", raising=False)
    result = await fetch_city_weather(city_name="南京市", start_time="2026-09-01 00:00:00", end_time="2026-09-01 00:00:00")
    assert result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_explicit_urban_code_and_http_logging_redaction(monkeypatch, caplog):
    monkeypatch.setenv("SUNCERE_WEATHER_TOKEN", "private-weather-token")
    monkeypatch.setenv("JIANGSU_REVIEW_WEATHER_STATIONS", json.dumps({"南京": "urban-provider-code"}))
    caplog.set_level(logging.INFO, logger="httpx")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "code": 200, "dataList": [row(stationName="城区观测站", stationCode="urban-provider-code")]
    }))) as client:
        result = await fetch_city_weather(city_name="南京市", start_time="2026-09-01 00:00:00", end_time="2026-09-01 00:00:00", client=client)
    assert result["station_code"] == "urban-provider-code"
    assert result["station_name"] == "城区观测站"
    assert result["selection_method"] == "configured_station"
    assert result["record_count"] == 1
    assert "private-weather-token" not in caplog.text
    assert "HTTP Request" in caplog.text


@pytest.mark.asyncio
async def test_collection_deadline_preserves_completed_chunks(monkeypatch):
    monkeypatch.setenv('SUNCERE_WEATHER_TOKEN', 'test')
    monkeypatch.setenv('JIANGSU_REVIEW_WEATHER_STATIONS', json.dumps({'南京市': '101190101'}))
    monkeypatch.setattr(weather_module, 'WEATHER_COLLECTION_TIMEOUT_SECONDS', 0.02)
    async def handler(request):
        if request.url.params['beginTime'].endswith('12:00:00'):
            await asyncio.sleep(1)
        return httpx.Response(200, json={'code': 200, 'dataList': [row()]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_city_weather(city_name='南京市', start_time='2026-09-01 00:00:00', end_time='2026-09-01 12:59:59', client=client)
    assert result['record_count'] == 1
    assert result['status'] == 'partial'
    assert len(result['gaps']) == 1
    assert result['gaps'][0]['start'] == '2026-09-01T12:00:00'


@pytest.mark.asyncio
async def test_national_cache_reused_across_cities_and_concurrent_calls(monkeypatch):
    monkeypatch.setenv('SUNCERE_WEATHER_TOKEN', 'test')
    monkeypatch.setenv('JIANGSU_REVIEW_WEATHER_STATIONS', json.dumps({'南京': 'nanjing', '无锡': 'wuxi'}))
    calls = []
    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={'code': 200, 'dataList': [row(stationCode='nanjing'), row(cityName='无锡市', stationName='无锡实测站', stationCode='wuxi')]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await asyncio.gather(*(fetch_city_weather(city_name=city, start_time='2026-09-01 00:00:00', end_time='2026-09-01 00:00:00', client=client) for city in ('南京市', '无锡市')))
    assert len(calls) == 1
    assert [result['record_count'] for result in results] == [1, 1]
    assert sum(result['cache_hit_hours'] for result in results) == 1


@pytest.mark.asyncio
async def test_unavailable_configured_station_uses_available_same_city_station(monkeypatch):
    monkeypatch.setenv('SUNCERE_WEATHER_TOKEN', 'test')
    monkeypatch.setenv('JIANGSU_REVIEW_WEATHER_STATIONS', json.dumps({'南京': 'wrong'}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'code': 200, 'dataList': [row()]}))) as client:
        result = await fetch_city_weather(city_name='南京市', start_time='2026-09-01 00:00:00', end_time='2026-09-01 00:00:00', client=client)
    assert result['status'] == 'partial'
    assert result['station_code'] == '101190101'
    assert result['city_record_count'] == 1


@pytest.mark.asyncio
async def test_best_hour_coverage_and_stable_tie_break_without_station_stitching(monkeypatch):
    monkeypatch.setenv('SUNCERE_WEATHER_TOKEN', 'test')
    monkeypatch.delenv('JIANGSU_REVIEW_WEATHER_STATIONS', raising=False)
    rows = [row(stationCode='a', stationName='甲'), row(stationCode='b', stationName='乙'),
            row('2026-09-01T01:00:00', stationCode='b', stationName='乙'),
            row('2026-09-01T02:00:00', stationCode='a', stationName='甲')]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'code':200, 'dataList':rows}))) as client:
        result = await fetch_city_weather(city_name='南京市', start_time='2026-09-01 00:00:00', end_time='2026-09-01 02:59:59', client=client)
    assert result['station_code'] == 'a'
    assert result['record_count'] == 2
    assert result['missing_hours'] == ['2026-09-01T01:00:00']
