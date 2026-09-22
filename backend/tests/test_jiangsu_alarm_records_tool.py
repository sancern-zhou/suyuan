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


def _tool():
    return JiangsuAlarmRecordsTool(
        base_url="http://ops.example/api/operacityproduct",
        token_url="http://token.example/token",
        username="user",
        password="password",
    )


def _patch_resolver(monkeypatch, codes):
    async def resolve(self, station_name):
        return list(codes)

    monkeypatch.setattr(JiangsuAlarmRecordsTool, "_resolve_station_name_codes", resolve)


@pytest.mark.asyncio
async def test_alarm_records_requires_station_name():
    result = await _tool().execute(
        start_time="2026-08-11 15:00:00", end_time="2026-08-11 16:00:00"
    )
    assert result["success"] is False
    assert "station_name" in result["summary"]
    assert "execute_smart_event_sql_query" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_rejects_city_scope():
    result = await _tool().execute(
        city_name="江苏省", start_time="2026-08-11 15:00:00", end_time="2026-08-11 16:00:00"
    )
    assert result["success"] is False
    assert "不支持 city_name" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_uses_station_name_and_indexed_query_params(monkeypatch):
    tool = _tool()
    captured = {}
    _patch_resolver(monkeypatch, ["5006A", "5005A"])

    async def get_token():
        return "token-value"

    async def get_records(params, token):
        captured["params"] = params
        captured["token"] = token
        return _Response({"result": {"items": [{"id": 7, "code": "5006A"}], "totalCount": 1}})

    monkeypatch.setattr(tool, "_get_token", get_token)
    monkeypatch.setattr(tool, "_get", get_records)

    result = await tool.execute(
        station_name="江宁站",
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-12 14:00:00",
        call_type="qb",
        alarm_state=1,
        call_level="qb",
        max_result_count=10,
    )

    assert result["success"] is True
    assert result["metadata"]["station_name"] == "江宁站"
    assert result["metadata"]["total_count"] == 1
    assert ("code[0]", "5006A") in captured["params"]
    assert ("code[1]", "5005A") in captured["params"]
    assert ("DDALARMSTATE", 1) in captured["params"]
    assert captured["token"] == "token-value"


@pytest.mark.asyncio
async def test_alarm_records_rejects_range_over_24h(monkeypatch):
    _patch_resolver(monkeypatch, ["5006A"])
    result = await _tool().execute(
        station_name="江宁站",
        start_time="2026-08-11 00:00:00",
        end_time="2026-08-12 01:00:00",
    )
    assert result["success"] is False
    assert "24 小时" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_rejects_invalid_time_range_before_request(monkeypatch):
    _patch_resolver(monkeypatch, ["5006A"])
    result = await _tool().execute(
        station_name="江宁站",
        start_time="2026-08-13 00:00:00",
        end_time="2026-08-12 00:00:00",
    )
    assert result["success"] is False
    assert "start_time 不能晚于 end_time" in result["summary"]


@pytest.mark.asyncio
async def test_alarm_records_pipeline_supports_unscoped_pagination(monkeypatch):
    tool = _tool()
    requests = []

    async def get_records(params):
        requests.append(params)
        skip = dict(params)["skipCount"]
        rows = [{"id": skip + index, "stacode": f"S{skip + index}"} for index in range(2 if skip == 0 else 1)]
        return {"success": True, "result": {"items": rows, "totalCount": 3}}

    monkeypatch.setattr(tool, "_request", get_records)
    result = await tool.execute_pipeline(
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-11 16:00:00",
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
async def test_alarm_records_pipeline_filters_to_requested_station_type(monkeypatch):
    tool = _tool()

    async def resolve_station_type_codes(station_type):
        assert station_type == "省控"
        return {"P1"}, True

    async def get_records(params):
        return {"success": True, "result": {"items": [
            {"id": 1, "stacode": "P1"}, {"id": 2, "stacode": "N1"},
        ], "totalCount": 2}}

    monkeypatch.setattr(tool, "_resolve_station_type_codes", resolve_station_type_codes)
    monkeypatch.setattr(tool, "_request", get_records)
    result = await tool.execute_pipeline(
        station_type="省控",
        start_time="2026-08-11 15:00:00",
        end_time="2026-08-11 16:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["station_type_filter_applied"] is True
    assert result["metadata"]["upstream_total_count"] == 2
    assert result["metadata"]["total_count"] == 1
    assert result["data"][0]["stacode"] == "P1"
