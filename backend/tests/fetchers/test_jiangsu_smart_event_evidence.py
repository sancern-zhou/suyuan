import pytest

from app.fetchers.jiangsu_smart_event_evidence import (
    JiangsuSmartEventEvidenceFetcher,
    _compact_result,
    _instrument_pollutant_codes,
    _profile,
    _qc_severe_only,
    _target_pollutants,
)
from app.tools.jiangsu.legacy_evidence import JiangsuLegacyEvidenceAdapter


def test_event_profile_routes_alarm_types_to_required_sources():
    assert "qc_history" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.instrument"})["fetch"]
    assert "station_alarm" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.power"})["fetch"]
    assert {"acquisition_alarm", "door"}.issubset(
        set(_profile({"event_trigger_type": "jiangsu.smart_event.alarm.network"})["fetch"])
    )
    assert "instrument_status" in _profile({"event_trigger_type": "jiangsu.smart_event.alarm.instrument"})["fetch"]


def test_profiles_fetch_weather_and_comparison_for_all_triggers():
    for trigger in ("power", "network", "environment", "instrument"):
        profile = _profile({"event_trigger_type": f"jiangsu.smart_event.alarm.{trigger}"})
        assert "comparison" in profile["fetch"], trigger
        assert "weather" in profile["fetch"], trigger


def test_profiles_no_longer_fetch_platform_alarm():
    for trigger in ("power", "network", "environment", "instrument"):
        profile = _profile({"event_trigger_type": f"jiangsu.smart_event.alarm.{trigger}"})
        assert "platform_alarm" not in profile["fetch"]


def test_windows_define_event_hour_and_day_scopes():
    windows = JiangsuSmartEventEvidenceFetcher._windows({
        "event_start_time": "2026-09-09T10:15:00+08:00",
        "event_end_time": "2026-09-09T11:20:00+08:00",
    })
    assert windows["event"] == {"start": "2026-09-09 10:15:00", "end": "2026-09-09 11:20:00"}
    # 整点小时区间覆盖起止时间所在小时之间的完整周期（合并桶首末线索）。
    assert windows["hour"] == {"start": "2026-09-09 10:00:00", "end": "2026-09-09 11:59:59"}
    # 当天窗口覆盖事件自然日。
    assert windows["day"] == {"start": "2026-09-09 00:00:00", "end": "2026-09-09 23:59:59"}
    # 起止在同一小时内时区间退化为单个整点小时。
    single = JiangsuSmartEventEvidenceFetcher._windows({
        "event_start_time": "2026-09-09T10:15:00+08:00",
        "event_end_time": "2026-09-09T10:40:00+08:00",
    })
    assert single["hour"] == {"start": "2026-09-09 10:00:00", "end": "2026-09-09 10:59:59"}

    early = JiangsuSmartEventEvidenceFetcher._windows({
        "event_start_time": "2026-09-09T01:15:00+08:00",
    })
    assert early["day"]["start"] == "2026-09-08 19:15:00"



def test_compact_result_preserves_declared_nested_record_count():
    result = _compact_result({"success": True, "status": "success", "metadata": {"record_count": 34}, "data": [{"result": {}}]})
    assert result["record_count"] == 34
    assert result["returned_records"] == 1


def test_compact_result_uses_message_as_summary_fallback():
    result = _compact_result({"success": False, "status": "unavailable", "message": "缺少站点归属城市或气象接口尚未配置", "data": []})
    assert result["summary"] == "缺少站点归属城市或气象接口尚未配置"


def test_compact_result_infers_success_from_positive_status():
    weather_like = {"status": "partial", "message": "气象站 响水：22/24 小时", "data": [{}]}
    assert _compact_result(weather_like)["success"] is True
    assert _compact_result({"status": "success", "data": [{}]})["success"] is True
    assert _compact_result({"status": "unavailable", "data": []})["success"] is False
    assert _compact_result({"success": False, "status": "partial", "data": []})["success"] is False


def test_profile_exposes_collection_policy_sources():
    profile = _profile({"event_trigger_type": "jiangsu.smart_event.alarm.power"})
    assert profile["fetch"][:2] == ["monitoring", "station_alarm"]


def test_target_pollutants_extracted_from_clue_tags():
    event = {
        "primary_clue_tag": "浓度超限",
        "alarm_content": "PM2.5 小时浓度超过阈值",
        "clue_tags": [{"tag_category": "报警", "tag_name": "单仪器断数", "tag_object": "SO2"}],
    }
    assert _target_pollutants(event) == ["PM2.5", "SO2"]
    assert _target_pollutants({"primary_clue_tag": "供电报警"}) == ["PM10", "PM2.5", "SO2", "NO2", "CO", "O3"]
    # NO2 优先于 NO，避免子串误命中。
    assert _target_pollutants({"alarm_content": "NO2 分析仪故障"}) == ["NO2"]
    assert _instrument_pollutant_codes(["PM2.5", "SO2"]) == ["PM2_5", "PM2.5", "SO2"]


def test_qc_severe_only_keeps_non_qualified_records():
    result = {
        "success": True,
        "status": "success",
        "summary": "质控任务查询完成。",
        "metadata": {},
        "record_count": 3,
        "returned_records": 3,
        "data": [
            {"qcResult": "合格"},
            {"qcResult": "不合格，超过跨度偏差"},
            {"qcResult": ""},
        ],
    }
    filtered = _qc_severe_only(result)
    assert [row["qcResult"] for row in filtered["data"]] == ["不合格，超过跨度偏差"]
    assert filtered["record_count"] == 1
    assert filtered["metadata"]["qc_severe_only"] is True
    assert filtered["metadata"]["total_record_count"] == 3
    assert "1/3" in filtered["summary"]


def test_power_environment_alarm_classification():
    from app.fetchers.jiangsu_smart_event_evidence import (
        _is_power_environment_alarm,
        _power_environment_alarms,
    )
    assert _is_power_environment_alarm({"AlarmType": 1216})  # 站房温度
    assert _is_power_environment_alarm({"AlarmType": 1213})  # IB 电流
    assert not _is_power_environment_alarm({"AlarmType": 1205})  # 水浸
    assert not _is_power_environment_alarm({"AlarmType": 1207})  # 火警
    assert not _is_power_environment_alarm({"AlarmType": 1218})  # 采样总管温度
    assert not _is_power_environment_alarm({"AlarmType": 750})  # 仪器状态
    station_alarm_result = {
        "success": True,
        "data": [{
            "station": {"station_code": "3011A"},
            "result": {
                "alarmLogs": [
                    {"AlarmType": 750, "Description": "SO2 状态异常"},
                    {"AlarmType": 1216, "Description": "站房温度超限"},
                ],
            },
            "success": True,
        }],
    }
    env_alarms = _power_environment_alarms(station_alarm_result)
    assert [row["AlarmType"] for row in env_alarms] == [1216]


@pytest.mark.asyncio
async def test_legacy_adapter_normalizes_instrument_and_door_payloads(monkeypatch):
    adapter = JiangsuLegacyEvidenceAdapter()

    async def fake_post(path, payload):
        return {"result": [{"path": path, "value": 1, "pollutantCode": "SO2"}, {"pollutantCode": "O3", "value": 2}]}

    async def fake_get(path, params):
        return {"result": {"list": [{"path": path, "params": params}]}}

    monkeypatch.setattr(adapter, "_post_retry", fake_post)
    monkeypatch.setattr(adapter, "_get_retry", fake_get)
    instrument = await adapter.instrument_status(
        station_code="3011A", start_time="2026-09-09 00:00:00", end_time="2026-09-09 01:00:00",
        pollutant_codes=["SO2"],
    )
    door = await adapter.door_records(
        station_code="3011A", start_time="2026-09-09 00:00:00", end_time="2026-09-09 01:00:00"
    )
    assert instrument["status"] == "success"
    assert instrument["record_count"] == 2
    assert instrument["metadata"]["query"]["pollutant_codes"] == ["SO2"]
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
        self.calls = []

    async def fetch_station_directory(self):
        return self.directory

    async def fetch_raw_records(self, *, data_kind, station_codes, start_time, end_time, data_type, station_type):
        self.calls.append({
            "data_kind": data_kind,
            "station_codes": list(station_codes),
            "start_time": start_time,
            "end_time": end_time,
        })
        records = [dict(row) for code in station_codes for row in self.records_by_code.get(code, [])]
        return records, {"codes": list(station_codes)}


@pytest.mark.asyncio
async def test_monitoring_fetches_only_hourly_data_for_day():
    tool = StubStationDataTool([], {})
    fetcher = JiangsuSmartEventEvidenceFetcher(station_data_tool=tool)
    windows = JiangsuSmartEventEvidenceFetcher._windows({
        "event_start_time": "2026-09-09T10:15:00+08:00",
    })
    result = await fetcher._monitoring("3011A", windows)
    calls = {call["data_kind"]: call for call in tool.calls}
    assert calls["station_hour"]["start_time"] == "2026-09-09 00:00:00"
    assert calls["station_hour"]["end_time"] == "2026-09-09 23:59:59"
    assert len(tool.calls) == 1
    assert set(calls) == {"station_hour"}
    assert set(result["data"]) == {"station_hour"}
    assert result["status"] == "empty"
    assert result["success"] is True


def _alarm_gate_result(alarm_type, *, success=True):
    return {
        "success": success,
        "status": "success" if success else "failed",
        "summary": "站房告警查询完成。" if success else "站房告警查询失败",
        "data": [{
            "station": {"station_code": "3011A"},
            "result": {"alarmLogs": [{"AlarmType": alarm_type, "Description": "测试告警"}]},
            "success": success,
        }],
    }


class StubEnvironmentTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "success", "success": True, "data": {"tableData": [{}]}}


@pytest.mark.asyncio
async def test_resolve_city_falls_back_to_station_directory():
    directory = [{"stationCode": "3011A", "cityName": "南通市"}]
    fetcher = JiangsuSmartEventEvidenceFetcher(station_data_tool=StubStationDataTool(directory, {}))
    assert await fetcher._resolve_city("3011A") == "南通市"
    assert await fetcher._resolve_city("XXXX") == ""


@pytest.mark.asyncio
async def test_resolve_city_swallows_directory_failure():
    class BrokenDirectoryTool:
        async def fetch_station_directory(self):
            raise RuntimeError("目录接口不可用")

    fetcher = JiangsuSmartEventEvidenceFetcher(station_data_tool=BrokenDirectoryTool())
    assert await fetcher._resolve_city("3011A") == ""


@pytest.mark.asyncio
async def test_environment_skipped_without_power_environment_alarms():
    environment_tool = StubEnvironmentTool()
    fetcher = JiangsuSmartEventEvidenceFetcher(environment_tool=environment_tool)
    windows = JiangsuSmartEventEvidenceFetcher._windows({"event_start_time": "2026-09-09T10:15:00+08:00"})

    async def gate():
        return _alarm_gate_result(750)  # 仪器状态类告警，非动环。

    result = await fetcher._environment({"site_id": "3011A"}, "3011A", windows, gate())
    assert result["status"] == "skipped"
    assert result["success"] is True
    assert result["gate"]["environment_alarm_count"] == 0
    assert environment_tool.calls == []


@pytest.mark.asyncio
async def test_environment_fetches_hour_window_when_power_environment_alarm_exists():
    environment_tool = StubEnvironmentTool()
    fetcher = JiangsuSmartEventEvidenceFetcher(environment_tool=environment_tool)
    windows = JiangsuSmartEventEvidenceFetcher._windows({"event_start_time": "2026-09-09T10:15:00+08:00"})

    async def gate():
        return _alarm_gate_result(1216)  # 站房温度告警，动环类。

    result = await fetcher._environment({"site_id": "3011A"}, "3011A", windows, gate())
    assert result["success"] is True
    assert result["gate"]["environment_alarm_count"] == 1
    assert environment_tool.calls[0]["start_time"] == "2026-09-09 10:00:00"
    assert environment_tool.calls[0]["end_time"] == "2026-09-09 10:59:59"


@pytest.mark.asyncio
async def test_environment_marks_gap_when_alarm_logs_unavailable():
    environment_tool = StubEnvironmentTool()
    fetcher = JiangsuSmartEventEvidenceFetcher(environment_tool=environment_tool)
    windows = JiangsuSmartEventEvidenceFetcher._windows({"event_start_time": "2026-09-09T10:15:00+08:00"})

    async def gate():
        return _alarm_gate_result(1216, success=False)

    result = await fetcher._environment({"site_id": "3011A"}, "3011A", windows, gate())
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["gate"]["available"] is False
    assert environment_tool.calls == []


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
        "hour": {"start": "2026-09-09 10:00:00", "end": "2026-09-09 10:59:59"},
        "day": {"start": "2026-09-09 00:00:00", "end": "2026-09-09 23:59:59"},
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


def test_target_pollutants_reads_all_merged_alarm_contents():
    assert _target_pollutants({"evidence": {"alarms": [
        {"content": "PM₂.₅浓度异常"}, {"alarmContent": "SO₂-API-M100流量异常"},
        {"description": "二氧化氮分析仪故障"},
    ], "alarm": {"content": "PM10采样异常"}}}) == ["PM10", "PM2.5", "SO2", "NO2"]


@pytest.mark.asyncio
async def test_instrument_status_defaults_to_six_pollutants(monkeypatch):
    adapter = JiangsuLegacyEvidenceAdapter()
    calls = []
    async def fake_post(path, payload):
        calls.append(payload)
        return {"result": [{"pollutantCode": "SO2"}]}
    monkeypatch.setattr(adapter, "_post_retry", fake_post)
    result = await adapter.instrument_status(station_code="3011A", start_time="start", end_time="end", pollutant_codes=[])
    assert result["status"] == "success"
    assert len(calls) == 2
    assert calls[0]["PollutantCodes"] == ["PM10", "PM2_5", "PM2.5", "SO2", "NO2", "CO", "O3"]


def test_instrument_row_filter_matches_pm25_aliases_and_rejects_other_instruments():
    from app.tools.jiangsu.legacy_evidence import filter_instrument_rows
    rows = [{"pollutantCode": "PM2_5"}, {"pollutantName": "PM2.5"}, {"pollutantCode": "PM10"}, {"statusName": "流量"}]
    assert filter_instrument_rows({"items": rows}, ["PM2.5"]) == rows[:2]


def test_target_pollutants_does_not_expand_from_automatic_monitoring_tags():
    event = {"alarm_content": "PM2.5浓度偏差报警", "clue_tags": [
        {"detected": True, "tag_category": "数据", "tag_object": "SO2"},
        {"detected": True, "tag_category": "数据", "tag_object": "NO2"},
    ]}
    assert _target_pollutants(event) == ["PM2.5"]


def test_merged_alarm_pollutants_accumulate_and_deduplicate():
    event = {"evidence": {"alarms": [{"content": "PM2.5偏差报警"}]}}
    assert _target_pollutants(event) == ["PM2.5"]
    event["evidence"]["alarms"].append({"content": "SO2采样流量异常"})
    assert _target_pollutants(event) == ["PM2.5", "SO2"]
    event["evidence"]["alarms"].append({"content": "PM2_5浓度超限"})
    assert _target_pollutants(event) == ["PM2.5", "SO2"]


@pytest.mark.asyncio
@pytest.mark.parametrize('rows,success,status,expected', [
    ([], True, 'skipped', []),
    ([{'subCatalog': 1205, 'lauchTime': '2026-09-10T10:01:00'}], True, 'skipped', []),
    ([{'subCatalog': 735, 'lauchTime': '2026-09-10T10:01:00', 'descriptionDE': 'PM2.5浓度突变'}], True, 'success', ['PM2_5', 'PM2.5']),
    ([{'subCatalog': 735, 'lauchTime': '2026-09-09T10:00:00', 'resumeTime': '2026-09-10T10:10:00', 'descriptionDE': 'PM2.5异常'}], True, 'success', ['PM2_5', 'PM2.5']),
    ([{'subCatalog': 735, 'lauchTime': '2026-09-09T10:00:00', 'resumeTime': '2026-09-10T09:59:59'}], True, 'skipped', []),
    ([{'subCatalog': 735, 'lauchTime': '2026-09-10T10:01:00', 'descriptionDE': 'O3异常'}], True, 'skipped', []),
    ([], False, 'failed', []),
    ([{'subCatalog': 735, 'lauchTime': 'invalid'}], True, 'failed', []),
])
async def test_instrument_alarm_gate(rows, success, status, expected):
    calls = []
    class Adapter:
        async def instrument_alarm_logs(self, **kwargs):
            assert kwargs['start_time'] == '2026-09-03 10:00:00'
            return {'success': success, 'data': rows}
        async def instrument_status(self, **kwargs):
            calls.append(kwargs)
            return {'success': True, 'status': 'success', 'data': {}, 'record_count': 1}
    fetcher = JiangsuSmartEventEvidenceFetcher(legacy_adapter=Adapter())
    event = {'alarm_content': 'PM2.5和SO2异常', 'event_start_time': '2026-09-10T10:00:00+08:00'}
    result = await fetcher._instrument_status(event, '3013A', fetcher._windows(event))
    assert result['status'] == status
    assert [call['pollutant_codes'] for call in calls] == ([expected] if expected else [])


@pytest.mark.asyncio
async def test_instrument_alarm_api_validates_response(monkeypatch):
    adapter = JiangsuLegacyEvidenceAdapter()
    async def get(path, params):
        assert path == 'stationintegrate/StationIntegrate/GetAlarmLogListAsync'
        assert params == [('StationCode', '3013A'), ('TimePoint', 'start'), ('TimePoint', 'end')]
        return {'result': {'unexpected': []}}
    monkeypatch.setattr(adapter, '_get_retry', get)
    result = await adapter.instrument_alarm_logs(station_code='3013A', start_time='start', end_time='end')
    assert result['status'] == 'failed'
