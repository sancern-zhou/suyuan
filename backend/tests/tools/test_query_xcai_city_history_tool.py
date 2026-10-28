import asyncio

from app.tools.query.query_xcai_city_history.tool import (
    QueryXcAiCityHistoryTool,
    find_blocked_cities,
)


def test_find_blocked_cities_matches_short_and_full_names():
    assert find_blocked_cities(["许昌", "广州市"]) == ["许昌", "许昌市"]
    assert find_blocked_cities(["许昌市"]) == ["许昌市"]
    assert find_blocked_cities(["广州市", "深圳市"]) == []


def test_execute_rejects_xuchang_before_querying():
    tool = QueryXcAiCityHistoryTool()

    result = asyncio.run(
        tool.execute(
            context=None,
            cities=["许昌"],
            data_type="hour",
            start_time="2025-01-01 00:00:00",
            end_time="2025-01-02 00:00:00",
        )
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["metadata"]["blocked_cities"] == ["许昌", "许昌市"]
    assert "query_airdata_platform" in result["summary"]
    assert result["data"] is None


def test_tool_description_declares_xuchang_restriction():
    tool = QueryXcAiCityHistoryTool()

    assert "不支持许昌市" in tool.function_schema["description"]
