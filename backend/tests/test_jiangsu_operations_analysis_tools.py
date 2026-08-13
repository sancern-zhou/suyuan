import pytest

from app.tools.jiangsu.operations_analysis import JiangsuAttendanceRecordsTool, JiangsuStationDirectoryTool


@pytest.mark.asyncio
async def test_attendance_records_maps_filters_and_returns_location_events(monkeypatch):
    tool = JiangsuAttendanceRecordsTool()
    captured = {}

    async def request(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"result": {"items": [{"UserName": "张三", "StationCode": "5006A", "Longitude": 118.7}], "totalCount": 1}}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-02 00:00:00",
        user_name="张三",
        unit_id="unit-a",
        station_code="5006A",
    )

    assert result["success"] is True
    assert result["metadata"]["total_count"] == 1
    assert captured["path"] == "operation/AirCityAPPAttendance/GetAttendanceManagement"
    assert ("warrantytime[0]", "2026-08-01 00:00:00") in captured["params"]
    assert ("UserName", "张三") in captured["params"]
    assert ("StationCode", "5006A") in captured["params"]


@pytest.mark.asyncio
async def test_station_directory_filters_result_client_side(monkeypatch):
    tool = JiangsuStationDirectoryTool()

    async def request(path, params):
        assert path == "operation/AirOperaBase/GetOpaEnabledStationAsync"
        assert params == []
        return {"result": [{"stationCode": "5006A"}, {"stationCode": "5005A"}]}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(station_codes=["5005A"])

    assert result["success"] is True
    assert result["data"] == [{"stationCode": "5005A"}]


@pytest.mark.asyncio
async def test_attendance_records_rejects_oversized_time_range_before_request():
    tool = JiangsuAttendanceRecordsTool()
    result = await tool.execute(start_time="2026-01-01 00:00:00", end_time="2026-06-01 00:00:00")
    assert result["success"] is False
    assert "不超过 93 天" in result["summary"]
