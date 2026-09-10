import pytest

from app.fetchers.jiangsu_smart_event_evidence import (
    JiangsuSmartEventEvidenceFetcher,
    _compact_result,
    _profile,
)
from app.tools.jiangsu.legacy_evidence import JiangsuLegacyEvidenceAdapter


def test_event_profile_routes_alarm_types_to_required_sources():
    assert "qc_history" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.instrument"})["fetch"]
    assert "comparison" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.environment"})["fetch"]
    assert "station_alarm" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.power"})["fetch"]
    assert {"platform_alarm", "acquisition_alarm", "door"}.issubset(
        set(_profile({"event_trigger_type": "jiangsu.smart_event.alarm.network"})["fetch"])
    )
    assert "instrument_status" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.instrument"})["fetch"]


def test_windows_extend_event_and_use_natural_day_for_compliance():
    windows = JiangsuSmartEventEvidenceFetcher._windows({
        "event_start_time": "2026-09-09T10:15:00+08:00",
        "event_end_time": "2026-09-09T11:20:00+08:00",
    })
    assert windows["query"] == {"start": "2026-09-09 09:45:00", "end": "2026-09-09 11:50:00"}
    assert windows["compliance"] == {"start": "2026-09-09 00:00:00", "end": "2026-09-09 23:59:59"}


def test_compact_result_preserves_declared_nested_record_count():
    result = _compact_result({"success": True, "status": "success", "metadata": {"record_count": 34}, "data": [{"result": {}}]})
    assert result["record_count"] == 34
    assert result["returned_records"] == 1


def test_profile_exposes_collection_policy_sources():
    profile = _profile({"event_trigger_type": "jiangsu.smart_event.alarm.power"})
    assert profile["fetch"][:2] == ["monitoring", "station_alarm"]
    assert "platform_alarm" in profile["fetch"]


@pytest.mark.asyncio
async def test_legacy_adapter_normalizes_instrument_and_door_payloads(monkeypatch):
    adapter = JiangsuLegacyEvidenceAdapter()

    async def fake_post(path, payload):
        return {"result": [{"path": path, "value": 1}]}

    async def fake_get(path, params):
        return {"result": {"list": [{"path": path, "params": params}]}}

    monkeypatch.setattr(adapter, "_post_retry", fake_post)
    monkeypatch.setattr(adapter, "_get_retry", fake_get)
    instrument = await adapter.instrument_status(
        station_code="3011A", start_time="2026-09-09 00:00:00", end_time="2026-09-09 01:00:00"
    )
    door = await adapter.door_records(
        station_code="3011A", start_time="2026-09-09 00:00:00", end_time="2026-09-09 01:00:00"
    )
    assert instrument["status"] == "success"
    assert instrument["record_count"] == 2
    assert door["status"] == "success"
    assert door["record_count"] == 1


@pytest.mark.asyncio
async def test_video_gap_is_explicit_when_station_is_missing():
    package = await JiangsuSmartEventEvidenceFetcher().fetch({"event_id": "e1", "event_start_time": "2026-09-09T10:00:00+08:00"})
    assert package["status"] == "failed"
    assert any(gap["source"] == "video" for gap in package["gaps"])
    assert any(gap["source"] == "station" for gap in package["gaps"])


class StubStationDataTool:
    def __init__(self, directory, records_by_code):
        self.directory = directory
        self.records_by_code = records_by_code

    async def fetch_station_directory(self):
        return self.directory

    async def fetch_raw_records(self, *, data_kind, station_codes, start_time, end_time, data_type, station_type):
        records = [dict(row) for code in station_codes for row in self.records_by_code.get(code, [])]
        return records, {"codes": list(station_codes)}


@pytest.mark.asyncio
async def test_comparison_computes_regional_deltas_for_nearby_and_city_rest():
    directory = [
        {"stationCode": "A", "positionName": "本站", "cityName": "南通", "districtCode": "D1", "districtName": "如皋", "stationTypeName": "省控"},
        {"stationCode": "B", "positionName": "邻站", "cityName": "南通", "districtCode": "D1", "districtName": "如皋", "stationTypeName": "省控"},
        {"stationCode": "C", "positionName": "外区站", "cityName": "南通", "districtCode": "D2", "districtName": "海安", "stationTypeName": "省控"},
    ]
    records_by_code = {
        # 12:00 的记录落在事件窗口外，必须被均值过滤。
        "A": [
            {"stationCode": "A", "timePoint": "2026-09-09 10:00:00", "pM10": 90, "sO2": 10},
            {"stationCode": "A", "timePoint": "2026-09-09 11:00:00", "pM10": 110, "sO2": 12},
            {"stationCode": "A", "timePoint": "2026-09-09 12:00:00", "pM10": 999, "sO2": 99},
        ],
        "B": [{"stationCode": "B", "timePoint": "2026-09-09 10:00:00", "pM10": 120, "sO2": 11}],
        "C": [{"stationCode": "C", "timePoint": "2026-09-09 10:00:00", "pM10": 140, "sO2": 9}],
    }
    fetcher = JiangsuSmartEventEvidenceFetcher(
        station_data_tool=StubStationDataTool(directory, records_by_code)
    )
    windows = {
        "event": {"start": "2026-09-09 10:00:00", "end": "2026-09-09 11:00:00"},
        "query": {"start": "2026-09-09 09:30:00", "end": "2026-09-09 11:30:00"},
    }

    result = await fetcher._comparison(
        {"site_name": "本站", "city_name": "南通", "district_name": "如皋"}, "A", windows
    )

    assert result["success"] is True
    deltas = result["regional_deltas"]
    assert deltas["pollutant_order"][0] == "PM10"
    assert deltas["target_station"]["means"] == {"PM10": 100.0, "SO2": 11.0}
    # 周边 = 同区县省控站（B）；全市其余 = 同城全部省控站去本站（B、C）。
    assert deltas["nearby_stations"]["station_count"] == 1
    assert deltas["nearby_stations"]["means"] == {"PM10": 120.0, "SO2": 11.0}
    assert deltas["city_rest_stations"]["station_count"] == 2
    assert deltas["city_rest_stations"]["means"] == {"PM10": 130.0, "SO2": 10.0}
    assert deltas["nearby_station_delta"]["PM10"] == -20.0
    assert deltas["nearby_station_delta_pct"]["PM10"] == -16.7
    assert deltas["same_city_delta"]["PM10"] == -30.0
    assert deltas["same_city_delta_pct"]["PM10"] == -23.1
    # 展示数据保留同区站 + 本站的原始记录。
    assert result["record_count"] == 4
