import pytest

from app.tools.workflow.jiangsu_network_inspection_workflow import (
    JiangsuNetworkInspectionWorkflow,
    build_network_inspection_result,
)


def test_build_network_inspection_result_has_stable_counts_and_short_conclusion():
    result = build_network_inspection_result(
        {
            "staList": [
                {"stationName": "站点甲", "cityName": "南京市", "isAlarm": True, "alarmTypeName": "动环"},
                {"stationName": "站点乙", "cityName": "南京市", "isAlarm": True, "alarmTypeName": "采样系统"},
                {"stationName": "站点丙", "cityName": "苏州市", "isAlarm": False},
            ],
            "alarmInfo": [{"id": 1}],
        },
        "day",
    )

    assert result["station_count"] == 3
    assert result["alarm_station_count"] == 2
    assert result["alarm_city_count"] == 1
    assert result["city_statistics"] == [{"city": "南京市", "count": 2}]
    assert result["category_statistics"] == [{"category": "动环", "count": 1}, {"category": "采样系统", "count": 1}]
    assert len(result["issues"]) == 2
    assert 200 <= result["conclusion_char_count"] <= 300


def test_build_network_inspection_result_accepts_lowercase_alarm_fields():
    result = build_network_inspection_result(
        {"stationList": [{"positionName": "站点甲", "city": "无锡市", "alarm": "true", "categoryName": "钢瓶"}]},
        "week",
    )
    assert result["alarm_station_count"] == 1
    assert result["issues"][0]["station_name"] == "站点甲"
    assert result["issues"][0]["category"] == "钢瓶"


@pytest.mark.asyncio
async def test_workflow_calls_existing_summary_tool_and_returns_structured_output(monkeypatch):
    async def fake_execute(self, context=None, period="day", **kwargs):
        assert period == "month"
        return {
            "success": True,
            "data": {"staList": [{"stationName": "站点甲", "cityName": "南京市", "isAlarm": True}]},
            "metadata": {"period": period},
        }

    monkeypatch.setattr(
        "app.tools.workflow.jiangsu_network_inspection_workflow.JiangsuNetworkInspectionSummaryTool.execute",
        fake_execute,
    )
    result = await JiangsuNetworkInspectionWorkflow().execute(period="month")
    assert result["success"] is True
    assert result["data"]["alarm_station_count"] == 1
    assert result["metadata"]["output_type"] == "short_conclusion_and_issue_list"


@pytest.mark.asyncio
async def test_workflow_rejects_unknown_period():
    result = await JiangsuNetworkInspectionWorkflow().execute(period="year")
    assert result["success"] is False
    assert "period 必须是 day、week 或 month" in result["summary"]

