"""历史证据包重投影/拆分迁移的投影逻辑（不触网、不写盘）。"""
from app.utils.jiangsu_smart_event_evidence_repack import project_package


def _raw_package():
    instrument_rows = [
        {"pollutantCode": "PM10", "statusName": "采样流量", "moniterValue": "1.0", "mark": "N",
         "timePoint": "2026-09-14T10:00:00", "targetUnit": "l/min", "stationCode": "3013A"},
        {"pollutantCode": "PM10", "statusName": "采样流量", "moniterValue": "1.2", "mark": "R",
         "timePoint": "2026-09-14T10:05:00", "targetUnit": "l/min", "stationCode": "3013A"},
    ]
    return {
        "event_id": "alarm:1", "status": "success",
        "sources": {
            "instrument_status": {"status": "success", "record_count": 2,
                                  "data": {"five_minute": instrument_rows, "hour": []}},
            "monitoring": {"status": "success", "data": {"station_hour": {
                "success": True, "status": "success", "data": [
                    {"id": 1, "createTime": "t", "modifyTime": "t", "pM10": "10",
                     "pM10_IAQI": "5", "timePoint": "2026-09-14T10:00:00"},
                ],
            }}},
            "weather": {"status": "empty"},
        },
    }


def test_project_package_projects_instrument_and_monitoring():
    package, changed = project_package(_raw_package())
    assert changed is True
    instrument = package["sources"]["instrument_status"]["data"]
    assert instrument["schema_version"] == "instrument_status_series/v1"
    assert instrument["raw_points"] == 2
    flow = next(item for item in instrument["five_minute"]["series"] if item["param"] == "采样流量")
    assert flow["abnormal"] == [{"t": "2026-09-14T10:05:00", "v": "1.2", "m": "R"}]
    monitoring_row = package["sources"]["monitoring"]["data"]["station_hour"]["data"][0]
    assert "id" not in monitoring_row and "pM10_IAQI" not in monitoring_row
    assert monitoring_row["pM10"] == "10"
    assert package["sources"]["weather"] == {"status": "empty"}


def test_project_package_is_idempotent():
    once, _ = project_package(_raw_package())
    twice, changed = project_package(once)
    assert changed is False
    assert twice == once


def test_project_package_without_sources_is_untouched():
    package = {"event_id": "alarm:1", "status": "failed", "gaps": []}
    projected, changed = project_package(package)
    assert changed is False
    assert projected == package
