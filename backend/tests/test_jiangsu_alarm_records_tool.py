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
