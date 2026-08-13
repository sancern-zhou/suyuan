import json
from datetime import datetime, timedelta

import pytest

from app.fetchers.jiangsu_station_fault_event import (
    EVENT_TYPE,
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


class FakeStationTool:
    async def fetch_raw_records(self, **kwargs):
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


def test_detect_monitoring_anomalies_finds_flatline():
    rows, _ = __import__("asyncio").run(FakeStationTool().fetch_raw_records())

    anomalies = detect_monitoring_anomalies(rows, now=NOW)

    assert len(anomalies) == 1
    assert any(
        finding["type"] == "flatline" and finding["pollutant"] == "O3"
        for finding in anomalies[0]["findings"]
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

    assert first["published_events"] == 2
    assert second["published_events"] == 0
    assert third["published_events"] == 0
    assert {event.event_type for event in events} == {EVENT_TYPE}
    assert {event.attributes["source_type"] for event in events} == {
        "platform_alarm",
        "monitoring_anomaly",
    }
    for event in events:
        package_path = event.payload["evidence_pack_path"]
        payload = json.loads(__import__("pathlib").Path(package_path).read_text(encoding="utf-8"))
        assert payload["event_id"] == event.event_id
        assert payload["station"]["station_code"] == "3001A"
        assert "historical_fault_work_orders" in payload
        assert "quality_control_history" in payload
