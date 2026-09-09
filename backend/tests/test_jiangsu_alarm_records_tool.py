import pytest

from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_alarm_records_uses_indexed_query_params_and_extracts_page(monkeypatch):
    tool = JiangsuAlarmRecordsTool(
        base_url="http://ops.example/api/operacityproduct",
        token_url="http://token.example/token",
        username="user",
        password="password",
    )
    captured = {}

    async def get_token():
        return "token-value"

    async def get_records(params, token):
        captured["params"] = params
        captured["token"] = token
        return _Response({"result": {"items": [{"id": 7, "code": "5006A"}], "totalCount": 1}})

    monkeypatch.setattr(tool, "_get_token", get_token)
    monkeypatch.setattr(tool, "_get", get_records)

    result = await tool.execute(
        station_codes=["5006A", "5005A"],
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-12 15:00:00",
        call_type="qb",
        alarm_state=1,
        call_level="qb",
        max_result_count=10,
    )

    assert result["success"] is True
    assert result["metadata"]["total_count"] == 1
    assert ("code[0]", "5006A") in captured["params"]
    assert ("code[1]", "5005A") in captured["params"]
    assert ("DDALARMSTATE", 1) in captured["params"]
    assert captured["token"] == "token-value"


@pytest.mark.asyncio
async def test_alarm_records_rejects_invalid_time_range_before_request():
    tool = JiangsuAlarmRecordsTool(
        base_url="http://ops.example/api/operacityproduct",
        token_url="http://token.example/token",
        username="user",
        password="password",
    )
    result = await tool.execute(
        station_codes=["5006A"],
        start_time="2026-08-13 00:00:00",
        end_time="2026-08-12 00:00:00",
    )
    assert result["success"] is False
    assert "start_time 不能晚于 end_time" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_supports_unscoped_upstream_query_and_pagination(monkeypatch):
    tool = JiangsuAlarmRecordsTool(
        base_url="http://ops.example/api/operacityproduct",
        token_url="http://token.example/token",
        username="user",
        password="password",
    )
    requests = []

    async def get_records(params):
        requests.append(params)
        skip = dict(params)["skipCount"]
        rows = [{"id": skip + index, "stacode": f"S{skip + index}"} for index in range(2 if skip == 0 else 1)]
        return {"success": True, "result": {"items": rows, "totalCount": 3}}

    monkeypatch.setattr(tool, "_request", get_records)
    result = await tool.execute(
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-12 15:00:00",
        max_result_count=2,
        sorting="timePoint",
    )

    assert result["success"] is True
    assert result["metadata"]["scope_mode"] == "upstream_all_stations"
    assert result["metadata"]["total_count"] == 3
    assert len(result["data"]) == 3
    assert not any(key.startswith("code[") for key, _ in requests[0])
    assert dict(requests[1])["skipCount"] == 2


@pytest.mark.asyncio
async def test_alarm_records_filters_unscoped_query_to_requested_station_type(monkeypatch):
    tool = JiangsuAlarmRecordsTool(
        base_url="http://ops.example/api/operacityproduct",
        token_url="http://token.example/token",
        username="user",
        password="password",
    )
    async def resolve_station_type_codes(station_type):
        assert station_type == "省控"
        return {"P1"}, True

    async def get_records(params):
        return {"success": True, "result": {"items": [
            {"id": 1, "stacode": "P1"}, {"id": 2, "stacode": "N1"},
        ], "totalCount": 2}}

    monkeypatch.setattr(tool, "_resolve_station_type_codes", resolve_station_type_codes)
    monkeypatch.setattr(tool, "_request", get_records)
    result = await tool.execute(
        station_type="省控",
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-12 15:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["station_type_filter_applied"] is True
    assert result["metadata"]["upstream_total_count"] == 2
    assert result["metadata"]["total_count"] == 1
    assert result["data"][0]["stacode"] == "P1"
