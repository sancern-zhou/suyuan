import pytest

from app.tools.jiangsu.query_tools import (
    JiangsuCityDataTool,
    JiangsuDistrictDataTool,
    JiangsuStatisticsTool,
)


class _FakeContext:
    def __init__(self):
        self.saved = []

    def save_data(self, *, data, schema, metadata):
        self.saved.append({"data": data, "schema": schema, "metadata": metadata})
        return f"backend/backend_data_registry/sessions/test/data/{schema}.json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "data_kind", "codes"),
    [
        (JiangsuCityDataTool(), "city_hour", ["320100"]),
        (JiangsuDistrictDataTool(), "district_hour", ["320102"]),
    ],
)
async def test_area_data_tools_default_to_audited_operating_conditions(monkeypatch, tool, data_kind, codes):
    async def request(path, params):
        assert ("dataType", 1) in params
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind=data_kind,
        codes=codes,
        start_time="2026-08-12 00:00:00",
        end_time="2026-08-12 01:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["data_type"] == 1
    assert tool.function_schema["parameters"]["properties"]["data_type"]["default"] == 1


@pytest.mark.asyncio
async def test_statistics_tool_defaults_to_audited_operating_conditions(monkeypatch):
    tool = JiangsuStatisticsTool()

    async def request(path, params):
        assert ("DataType", 1) in params
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        statistic_kind="city_rank",
        codes=["320100"],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 00:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["data_type"] == 1
    assert tool.function_schema["parameters"]["properties"]["data_type"]["default"] == 1


@pytest.mark.asyncio
async def test_city_data_resolves_jiangsu_name_inside_the_query_tool(monkeypatch):
    tool = JiangsuCityDataTool()

    async def request(path, params):
        if path != "AirCityProductBase/GetBSDRegionAsync":
            return {"result": {"items": [], "totalCount": 0}}
        assert params == []
        return {"result": [
            {"areaCode": "320000", "areaName": "江苏省", "parentID": "0", "level": 1},
            {"areaCode": "320100", "areaName": "南京市", "parentID": "320000", "level": 2},
            {"areaCode": "320200", "areaName": "无锡市", "parentID": "320000", "level": 2},
            {"areaCode": "320101001", "areaName": "玄武区", "parentID": "320100", "level": 3},
        ]}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind="city_hour", area_names=["江苏省"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["codes"] == ["320100", "320200"]


@pytest.mark.asyncio
async def test_city_data_accepts_city_name_without_a_code(monkeypatch):
    tool = JiangsuCityDataTool()

    async def request(path, params):
        if path == "AirCityProductBase/GetBSDRegionAsync":
            return {"result": [{"areaCode": "320100", "areaName": "南京市", "parentID": "320000", "level": 2}]}
        return {"result": {"items": [], "totalCount": 0}}

    monkeypatch.setattr(tool, "_get", request)
    result = await tool.execute(
        data_kind="city_hour", area_names=["南京"],
        start_time="2026-08-12 00:00:00", end_time="2026-08-12 23:00:00",
    )

    assert result["success"] is True
    assert result["metadata"]["codes"] == ["320100"]


@pytest.mark.asyncio
async def test_city_hour_data_preserves_full_series_and_externalizes_only_inline_preview(monkeypatch):
    tool = JiangsuCityDataTool()
    records = [
        {
            "name": "南京市",
            "code": "320100",
            "timePoint": f"2026-08-{1 + hour // 24:02d}T{hour % 24:02d}:00:00",
            "dataType": 0,
            "aqi": str(20 + hour % 30),
        }
        for hour in range(288)
    ]

    async def request(path, params):
        if path == "AirCityProductBase/GetBSDRegionAsync":
            return {
                "result": [
                    {
                        "areaCode": "320100",
                        "areaName": "南京市",
                        "parentID": "320000",
                        "level": 2,
                    }
                ]
            }
        return {"result": {"items": records, "totalCount": len(records)}}

    monkeypatch.setattr(tool, "_get", request)
    context = _FakeContext()

    result = await tool.execute(
        context=context,
        data_kind="city_hour",
        area_names=["南京市"],
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-12 23:59:59",
        max_results=1000,
    )

    assert result["success"] is True
    assert result["record_count"] == 288
    assert result["returned_records"] == 24
    assert result["sample_strategy"] == "head_tail"
    assert result["data"][0]["timePoint"] == "2026-08-01T00:00:00"
    assert result["data"][-1]["timePoint"] == "2026-08-12T23:00:00"
    assert result["file_path"].endswith("jiangsu_city_city_hour_filtered.json")
    filtered = next(item for item in context.saved if item["schema"].endswith("_filtered"))
    assert len(filtered["data"]) == 288
    assert "完整时间序列 288 条" in result["summary"]
