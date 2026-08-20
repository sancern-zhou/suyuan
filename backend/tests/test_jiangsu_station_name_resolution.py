import pytest

from app.tools.jiangsu.station_data import JiangsuStationDataTool


def test_station_tool_schema_exposes_atomic_area_and_station_selectors():
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    parameters = tool.function_schema["parameters"]

    assert "city_names" not in parameters["required"]
    assert {"station_codes", "station_names", "city_names", "district_names"} <= set(parameters["properties"])
    assert parameters["properties"]["allow_province_query"]["default"] is False
    assert parameters["properties"]["data_type"]["default"] == 1
    assert parameters["properties"]["station_type"]["default"] == "国控"
    assert parameters["properties"]["station_type"]["enum"] == ["国控", "省控", "市控", "全部"]
    assert tool.requires_context is True


@pytest.mark.asyncio
@pytest.mark.parametrize("province_name", ["江苏省", "江苏", "全省", "江苏全省"])
async def test_station_tool_requires_explicit_province_confirmation_before_directory_request(monkeypatch, province_name):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")

    async def unexpected_directory_request():
        pytest.fail("省级查询不应访问站点目录或外部接口")

    monkeypatch.setattr(tool, "_get_station_directory", unexpected_directory_request)
    result = await tool.execute(
        data_kind="station_day",
        city_names=[province_name],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is False
    assert "allow_province_query=true" in result["summary"]


@pytest.mark.asyncio
async def test_station_tool_accepts_district_selector(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    requests = []

    async def get_directory():
        return [
            {"stationCode": "A", "positionName": "玄武湖", "cityName": "南京市", "districtName": "玄武区"},
            {"stationCode": "B", "positionName": "江宁站", "cityName": "南京市", "districtName": "江宁区"},
        ]

    async def request(data_kind, payload):
        requests.append(payload)
        return {"result": [{"stationCode": code} for code in payload["codes"]]}

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        data_kind="station_hour",
        district_names=["南京市江宁区"],
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["station_codes"] == ["B"]
    assert requests[0]["codes"] == ["B"]


@pytest.mark.asyncio
async def test_station_tool_filters_city_by_station_type_and_defaults_to_national(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    directory = [
        {"stationCode": "N", "positionName": "国控站", "cityName": "南京市", "stationType": 1},
        {"stationCode": "P", "positionName": "省控站", "cityName": "南京市", "stationTypeName": "省控"},
        {"stationCode": "M", "positionName": "市控站", "cityName": "南京市", "站点类型ID": 3.0},
    ]
    requests = []

    async def get_directory():
        return directory

    async def request(data_kind, payload):
        requests.append(payload)
        return {"result": [{"stationCode": code} for code in payload["codes"]]}

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        data_kind="station_hour", city_names=["南京市"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["station_type"] == "国控"
    assert requests[0]["codes"] == ["N"]

    result = await tool.execute(
        data_kind="station_hour", city_names=["南京市"], station_type="市控",
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 01:00:00",
    )
    assert result["metadata"]["station_type"] == "市控"
    assert requests[1]["codes"] == ["M"]


@pytest.mark.asyncio
async def test_station_tool_resolves_city_and_batches_station_requests(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    directory = [
        {"stationCode": f"S{i}", "positionName": f"站点{i}", "cityName": "南京市", "districtName": "鼓楼区", "provinceName": "江苏省"}
        for i in range(101)
    ]
    requests = []

    async def get_directory():
        return directory

    async def request(data_kind, payload):
        assert payload["dataType"] == 1
        requests.append(payload["codes"])
        return {"result": [{"stationCode": code} for code in payload["codes"]]}

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        data_kind="station_hour", city_names=["南京"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert len(result["metadata"]["station_codes"]) == 101
    assert [len(item) for item in requests] == [100, 1]
    assert result["metadata"]["batching"] == {
        "strategy": "serial", "batch_size": 100, "batch_count": 2, "retry_count": 0,
    }


@pytest.mark.asyncio
async def test_station_tool_externalizes_large_results_when_agent_context_is_available(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    directory = [
        {"stationCode": f"S{i}", "positionName": f"站点{i}", "cityName": "南京市"}
        for i in range(30)
    ]

    class FakeContext:
        def __init__(self):
            self.saved = []

        def save_data(self, data, schema, metadata):
            self.saved.append({"count": len(data), "schema": schema, "metadata": metadata})
            return f"backend/test_data/{schema}.json"

    async def get_directory():
        return directory

    async def request(data_kind, payload):
        return {"result": [{"stationCode": code, "timePoint": "2026-08-12 00:00:00"} for code in payload["codes"]]}

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    monkeypatch.setattr(tool, "_request", request)
    context = FakeContext()
    result = await tool.execute(
        context=context,
        data_kind="station_hour",
        city_names=["南京市"],
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert result["data_complete"] is False
    assert result["returned_records"] == 24
    assert len(result["data"]) == 24
    assert result["file_path"].endswith("jiangsu_station_hour_filtered.json")
    assert [item["count"] for item in context.saved] == [30, 30]


@pytest.mark.asyncio
async def test_station_tool_limits_explicit_province_query_time_range(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")

    async def get_directory():
        return [{"stationCode": "A", "provinceName": "江苏省", "cityName": "南京市"}]

    monkeypatch.setattr(tool, "_get_station_directory", get_directory)
    result = await tool.execute(
        data_kind="station_hour",
        city_names=["江苏省"],
        allow_province_query=True,
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 07:00:00",
    )

    assert result["success"] is False
    assert "最多 6 小时" in result["summary"]


@pytest.mark.asyncio
async def test_station_tool_retries_transient_batch_failure(monkeypatch):
    tool = JiangsuStationDataTool(base_url="http://example.test", username="user", password="password")
    calls = 0

    async def request(data_kind, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("上游接口繁忙，请稍后重试")
        return {"result": [{"stationCode": payload["codes"][0]}]}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(tool, "_request", request)
    monkeypatch.setattr("app.tools.jiangsu.station_data.asyncio.sleep", no_sleep)
    result = await tool.execute(
        data_kind="station_hour",
        station_codes=["A"],
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert calls == 2
    assert result["metadata"]["batching"]["retry_count"] == 1
