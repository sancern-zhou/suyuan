import json
from datetime import datetime, timedelta

import pytest

from app.fetchers.jiangsu_station_fault_event import (
    EVENT_TYPE,
    JIANGSU_PREFECTURE_CITIES,
    MAX_ALARM_EVENTS_PER_POLL,
    MAX_NEW_MONITOR_INCIDENTS_PER_POLL,
    MONITOR_INCIDENT_KEY_VERSION,
    JiangsuStationFaultEventFetcher,
    detect_monitoring_anomalies,
)


NOW = datetime.fromisoformat("2026-08-13T16:10:00+08:00")


class FakeAlarmTool:
    async def execute(self, **kwargs):
        return {
            "success": True,
            "data": [{
                "id": 157853,
                "stacode": "3001A",
                "positionName": "江宁九龙湖",
                "areaname": "南京市",
                "district": "江宁区",
                "content": "测量电压低于限定值",
                "alarmtime": "8/13/2026 3:00:00 PM",
                "alarmlevel": "一般",
                "ddRuleType": "仪器状态超上下限报警",
                "callType": "Instrument",
            }],
        }


class FakeManyAlarmsTool:
    async def execute(self, **kwargs):
        return {
            "success": True,
            "data": [
                {
                    "id": index,
                    "stacode": f"S{index:04d}",
                    "positionName": f"站点 {index}",
                    "areaname": "南京市",
                    "district": "玄武区",
                    "content": f"告警 {index}",
                    "alarmtime": "8/13/2026 3:00:00 PM",
                    "alarmlevel": "一般",
                    "ddRuleType": "设备告警",
                }
                for index in range(MAX_ALARM_EVENTS_PER_POLL + 2)
            ],
        }


class FakeStationTool:
    def __init__(self):
        self.calls = []

    async def fetch_raw_records(self, **kwargs):
        self.calls.append(kwargs)
        rows = []
        for station_index, (code, name) in enumerate((
            ("3001A", "江宁九龙湖"),
            ("3002A", "江宁大学城"),
            ("3003A", "江宁城区"),
        )):
            for point, hour in enumerate((11, 12, 13, 14, 15, 16)):
                rows.append({
                    "code": code,
                    "name": name,
                    "cityName": "南京市",
                    "districtName": "江宁区",
                    "timePoint": f"2026-08-13T{hour}:00:00+08:00",
                    "sO2": str(10 + point + station_index),
                    "nO2": str(20 + point + station_index),
                    "pM10": str(40 + point + station_index),
                    "co": str(0.5 + point * 0.01 + station_index * 0.01),
                    "o3": "50" if code == "3001A" else str(45 + point + station_index),
                    "pM2_5": str(25 + point + station_index),
                })
        return rows, {"codes": ["3001A", "3002A", "3003A"]}


class FakeEvidenceTool:
    async def execute(self, **kwargs):
        return {"success": True, "status": "success", "data": [], "metadata": kwargs}


class FakeStationToolWithNonReportingDirectoryStation(FakeStationTool):
    async def fetch_raw_records(self, **kwargs):
        rows, payload = await super().fetch_raw_records(**kwargs)
        return rows, {"codes": [*payload["codes"], "3999A"]}


@pytest.mark.asyncio
async def test_fetch_monitoring_splits_province_window_by_prefecture_city(tmp_path):
    station_tool = FakeStationTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        station_tool=station_tool,
    )

    records, station_codes = await fetcher._fetch_monitoring(NOW)

    assert [call["city_names"] for call in station_tool.calls] == [
        [city_name] for city_name in JIANGSU_PREFECTURE_CITIES
    ]
    assert all(call["city_names"] != ["江苏省"] for call in station_tool.calls)
    assert all(call["data_type"] == 0 for call in station_tool.calls)
    assert len(records) == 18
    assert station_codes == ["3001A", "3002A", "3003A"]


def test_detect_monitoring_anomalies_finds_flatline():
    rows, _ = __import__("asyncio").run(FakeStationTool().fetch_raw_records())

    anomalies = detect_monitoring_anomalies(rows, now=NOW)

    assert len(anomalies) == 1
    assert any(
        finding["type"] == "flatline" and finding["pollutant"] == "O3"
        for finding in anomalies[0]["findings"]
    )


def test_monitor_incident_key_is_stable_when_findings_change():
    first = {
        "station_code": "3001A",
        "source_record": {"findings": [{"type": "flatline", "pollutant": "O3"}]},
    }
    second = {
        "station_code": "3001A",
        "source_record": {
            "findings": [{"type": "persistent_peer_bias", "pollutant": "PM2.5"}]
        },
    }

    assert JiangsuStationFaultEventFetcher._monitor_incident_key(first) == (
        JiangsuStationFaultEventFetcher._monitor_incident_key(second)
    )


def test_detect_monitoring_anomalies_reuses_persistent_peer_bias_rules():
    rows = []
    start = datetime.fromisoformat("2026-08-13T00:00:00+08:00")
    for point in range(12):
        timestamp = (start + timedelta(hours=point)).isoformat()
        for code, pm25 in (("A", 80), ("B", 40), ("C", 42)):
            rows.append({
                "code": code,
                "name": code,
                "cityName": "南京市",
                "timePoint": timestamp,
                "pM2_5": pm25 + point,
                "pM10": 70 + point,
                "nO2": 30 + point,
                "o3": 80 - point,
                "co": 0.6,
            })

    anomalies = detect_monitoring_anomalies(rows, now=NOW)
    station_a = next(item for item in anomalies if item["station_code"] == "A")

    assert any(
        finding["type"] == "persistent_peer_bias"
        and finding["pollutant"] == "PM2_5"
        for finding in station_a["findings"]
    )


def test_regional_synchronous_jump_is_not_a_single_station_fault():
    rows = []
    start = datetime.fromisoformat("2026-08-13T05:00:00+08:00")
    for point in range(12):
        timestamp = (start + timedelta(hours=point)).isoformat()
        regional_value = 40 + point if point < 11 else 180
        for station_index, code in enumerate(("A", "B", "C")):
            rows.append({
                "code": code,
                "name": code,
                "cityName": "南京市",
                "timePoint": timestamp,
                "pM2_5": regional_value + station_index,
                "pM10": regional_value + 20 + station_index,
                "nO2": 30 + point + station_index,
                "o3": 80 - point + station_index,
                "co": 0.6 + point * 0.01,
            })

    anomalies = detect_monitoring_anomalies(
        rows,
        now=datetime.fromisoformat("2026-08-13T16:10:00+08:00"),
    )

    assert not any(
        finding.get("pollutant") in {"PM2_5", "PM10"}
        and finding["type"] in {
            "peer_aggregate_deviation",
            "persistent_peer_bias",
            "trend_inconsistency",
        }
        for item in anomalies
        for finding in item["findings"]
    )


def test_detect_monitoring_anomalies_rejects_broad_upstream_data_gap():
    with pytest.raises(RuntimeError, match="覆盖率异常"):
        detect_monitoring_anomalies(
            [{"code": "3001A", "timePoint": "2026-08-13T15:00:00+08:00"}],
            now=NOW,
            expected_station_codes=["3001A", "3002A", "3003A"],
        )


@pytest.mark.asyncio
async def test_fetcher_writes_packages_publishes_events_and_deduplicates(tmp_path):
    events = []
    current_time = [NOW]

    async def publish(event):
        events.append(event)

    evidence_tool = FakeEvidenceTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: current_time[0],
        alarm_tool=FakeAlarmTool(),
        station_tool=FakeStationTool(),
        station_alarm_tool=evidence_tool,
        work_order_tool=evidence_tool,
        inspection_tool=evidence_tool,
        qc_history_tool=evidence_tool,
    )
    first = await fetcher.fetch_and_store()
    second = await fetcher.fetch_and_store()
    current_time[0] = NOW + timedelta(minutes=60)
    third = await fetcher.fetch_and_store()

    assert first["published_events"] == 1
    assert first["suppressed_monitor_events"] == 1
    assert second["published_events"] == 0
    assert third["published_events"] == 0
    assert {event.event_type for event in events} == {EVENT_TYPE}
    assert {event.attributes["source_type"] for event in events} == {"platform_alarm"}
    assert {event.attributes["station_name"] for event in events} == {"江宁九龙湖"}
    for event in events:
        package_path = event.payload["evidence_pack_path"]
        payload = json.loads(__import__("pathlib").Path(package_path).read_text(encoding="utf-8"))
        assert payload["event_id"] == event.event_id
        assert payload["station"]["station_code"] == "3001A"
        assert "historical_fault_work_orders" in payload
        assert "quality_control_history" in payload


@pytest.mark.asyncio
async def test_first_monitor_poll_baselines_observed_stations_not_directory(tmp_path):
    events = []

    async def publish(event):
        events.append(event)

    evidence_tool = FakeEvidenceTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        alarm_tool=FakeAlarmTool(),
        station_tool=FakeStationToolWithNonReportingDirectoryStation(),
        station_alarm_tool=evidence_tool,
        work_order_tool=evidence_tool,
        inspection_tool=evidence_tool,
        qc_history_tool=evidence_tool,
    )

    result = await fetcher.fetch_and_store()
    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))

    assert result["published_events"] == 1
    assert result["suppressed_monitor_events"] == 1
    assert all(event.attributes.get("station_code") != "3999A" for event in events)
    assert state["monitor_station_codes"] == ["3001A", "3002A", "3003A"]


@pytest.mark.asyncio
async def test_fetcher_checkpoints_each_event_before_a_later_publish_fails(tmp_path):
    events = []
    fail_second = True

    async def publish(event):
        nonlocal fail_second
        events.append(event)
        if fail_second and len(events) == 2:
            raise RuntimeError("publish interrupted")

    evidence_tool = FakeEvidenceTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        alarm_tool=FakeAlarmTool(),
        station_tool=FakeStationTool(),
        station_alarm_tool=evidence_tool,
        work_order_tool=evidence_tool,
        inspection_tool=evidence_tool,
        qc_history_tool=evidence_tool,
    )
    fetcher._write_json(
        fetcher.state_path,
        {"monitor_incident_key_version": MONITOR_INCIDENT_KEY_VERSION},
    )

    with pytest.raises(RuntimeError, match="publish interrupted"):
        await fetcher.fetch_and_store()

    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    assert len(state["processed_fingerprints"]) == 1
    assert state["monitor_station_codes"] == ["3001A", "3002A", "3003A"]
    assert "last_alarm_poll_at" not in state

    fail_second = False
    resumed = await fetcher.fetch_and_store()

    assert resumed["published_events"] == 1
    assert len(events) == 3


@pytest.mark.asyncio
async def test_fetcher_suppresses_monitor_event_storm(monkeypatch, tmp_path):
    events = []

    async def publish(event):
        events.append(event)

    def broad_anomalies(*args, **kwargs):
        return [
            {
                "station_code": f"S{index:04d}",
                "station_name": f"站点 {index}",
                "city_name": "南京市",
                "district_name": "玄武区",
                "latest_time": NOW.isoformat(),
                "findings": [{"type": "flatline", "severity": "warning"}],
            }
            for index in range(MAX_NEW_MONITOR_INCIDENTS_PER_POLL + 1)
        ]

    monkeypatch.setattr(
        "app.fetchers.jiangsu_station_fault_event.detect_monitoring_anomalies",
        broad_anomalies,
    )
    evidence_tool = FakeEvidenceTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        alarm_tool=FakeAlarmTool(),
        station_tool=FakeStationTool(),
        station_alarm_tool=evidence_tool,
        work_order_tool=evidence_tool,
        inspection_tool=evidence_tool,
        qc_history_tool=evidence_tool,
    )
    fetcher._write_json(
        fetcher.state_path,
        {"monitor_incident_key_version": MONITOR_INCIDENT_KEY_VERSION},
    )

    result = await fetcher.fetch_and_store()

    assert result["published_events"] == 1
    assert result["suppressed_monitor_events"] == MAX_NEW_MONITOR_INCIDENTS_PER_POLL + 1
    assert {event.attributes["source_type"] for event in events} == {"platform_alarm"}


@pytest.mark.asyncio
async def test_fetcher_drains_platform_alarm_backlog_without_advancing_cursor(tmp_path):
    events = []

    async def publish(event):
        events.append(event)

    evidence_tool = FakeEvidenceTool()
    fetcher = JiangsuStationFaultEventFetcher(
        registry_root=tmp_path,
        event_publisher=publish,
        clock=lambda: NOW,
        alarm_tool=FakeManyAlarmsTool(),
        station_tool=FakeStationTool(),
        station_alarm_tool=evidence_tool,
        work_order_tool=evidence_tool,
        inspection_tool=evidence_tool,
        qc_history_tool=evidence_tool,
    )
    previous_cursor = (NOW - timedelta(hours=2)).isoformat()
    fetcher._write_json(
        fetcher.state_path,
        {"last_alarm_poll_at": previous_cursor},
    )

    first = await fetcher.fetch_and_store()
    first_state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    second = await fetcher.fetch_and_store()
    second_state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))

    assert first["published_alarm_events"] == MAX_ALARM_EVENTS_PER_POLL
    assert first["deferred_alarm_events"] == 2
    assert first_state["last_alarm_poll_at"] == previous_cursor
    assert second["published_alarm_events"] == 2
    assert second["deferred_alarm_events"] == 0
    assert second_state["last_alarm_poll_at"] == NOW.isoformat()
    assert len(events) == MAX_ALARM_EVENTS_PER_POLL + 2
