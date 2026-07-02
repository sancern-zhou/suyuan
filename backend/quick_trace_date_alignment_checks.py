import asyncio
import types
from datetime import date, datetime

from app.agent.executors.quick_trace_executor import QuickTraceExecutor, SimpleExecutionContext


def test_simple_execution_context_save_data_returns_string_id():
    context = SimpleExecutionContext()

    data_id = context.save_data(data=[], schema="weather")

    assert isinstance(data_id, str)
    assert data_id.startswith("quick_trace_weather:")


def test_air_quality_forecast_window_uses_alert_date():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    alert_dt = datetime(2026, 5, 12, 14, 0, 0)

    start_date, end_date = executor._air_quality_forecast_window(alert_dt)

    assert start_date == date(2026, 5, 12)
    assert end_date == date(2026, 5, 18)


def test_history_time_window_uses_alert_time():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    alert_dt = datetime(2026, 5, 12, 14, 0, 0)

    start_time, end_time = executor._history_time_window(alert_dt)

    assert start_time == datetime(2026, 5, 12, 2, 0, 0)
    assert end_time == alert_dt


def test_historical_backfill_skips_realtime_weather_forecast():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    alert_dt = datetime(2026, 5, 12, 14, 0, 0)
    now = datetime(2026, 6, 17, 12, 0, 0)

    result = executor._historical_forecast_unavailable_result(alert_dt, now=now)

    assert result["success"] is False
    assert result["status"] == "skipped"
    assert result["data"] == []
    assert "2026-05-12" in result["summary"]
    assert "实时预报接口" in result["summary"]


def test_select_analysis_event_uses_daily_max_aqi_primary_pollutant():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    records = [
        {
            "TimePoint": datetime(2026, 5, 12, 1, 0, 0),
            "AQI": 90,
            "PrimaryPollutant": "PM2.5",
            "PM2_5": 80,
            "O3": 120,
        },
        {
            "TimePoint": datetime(2026, 5, 12, 15, 0, 0),
            "AQI": 140,
            "PrimaryPollutant": "O3",
            "PM2_5": 45,
            "O3": 210,
        },
    ]

    event = executor._select_analysis_event_from_records("济宁市", "2026-05-12", records)

    assert event["alert_time"] == "2026-05-12 15:00:00"
    assert event["pollutant"] == "O3"
    assert event["alert_value"] == 210.0
    assert event["aqi"] == 140


def test_primary_pollutant_alias_supports_o3_one_hour_text():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)

    assert executor._normalize_primary_pollutant("臭氧1小时(O3_1h)") == "O3"


def test_select_analysis_event_falls_back_to_largest_threshold_ratio():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    records = [
        {
            "TimePoint": datetime(2026, 5, 12, 8, 0, 0),
            "AQI": None,
            "PrimaryPollutant": None,
            "PM2_5": 60,
            "O3": 170,
            "PM10": 90,
        }
    ]

    event = executor._select_analysis_event_from_records("济宁市", "2026-05-12", records)

    assert event["alert_time"] == "2026-05-12 08:00:00"
    assert event["pollutant"] == "O3"
    assert event["alert_value"] == 170.0
    assert event["selection_reason"] == "max_threshold_ratio"


def test_execute_historical_backfill_routes_alert_time_to_date_sensitive_tasks():
    executor = QuickTraceExecutor.__new__(QuickTraceExecutor)
    calls = {}

    class FakeWeatherDataTool:
        async def execute(self, **kwargs):
            calls["historical_weather"] = kwargs
            return {"success": True, "data": [], "summary": "历史气象"}

    class FakeWeatherForecastTool:
        async def execute(self, **kwargs):
            calls["forecast_called"] = True
            return {"success": True, "data": [], "summary": "实时预报"}

    class FakeWeatherSituationMapTool:
        async def execute(self, **kwargs):
            calls["weather_situation"] = kwargs
            return {"success": True, "data": {"analysis": "天气形势"}}

    executor.tools = {
        "weather_data": FakeWeatherDataTool(),
        "weather_forecast": FakeWeatherForecastTool(),
        "weather_situation_map": FakeWeatherSituationMapTool(),
    }

    async def fake_air_quality(self, city, reference_time=None):
        calls["air_quality"] = {
            "city": city,
            "reference_time": reference_time,
        }
        return {"success": True, "data": [], "summary": "空气质量"}

    async def fake_trajectory(self, **kwargs):
        calls["trajectory"] = kwargs
        return {"success": True, "summary": "轨迹"}

    async def fake_generate_summary(self, results, **kwargs):
        calls["results"] = results
        return {"summary_text": "ok", "visuals": []}

    executor._get_air_quality_from_db = types.MethodType(fake_air_quality, executor)
    executor._get_trajectory_analysis = types.MethodType(fake_trajectory, executor)
    executor._generate_summary = types.MethodType(fake_generate_summary, executor)

    result = asyncio.run(executor.execute(
        city="济宁市",
        alert_time="2026-05-12 14:00:00",
        pollutant="PM2.5",
        alert_value=115.0,
    ))

    assert result["summary_text"] == "ok"
    assert "forecast_called" not in calls
    assert calls["results"]["forecast"]["status"] == "skipped"
    assert calls["air_quality"]["reference_time"] == datetime(2026, 5, 12, 14, 0, 0)
    assert calls["historical_weather"]["start_time"] == "2026-05-09 14:00:00"
    assert calls["historical_weather"]["end_time"] == "2026-05-11 14:00:00"
    assert calls["trajectory"]["start_time"] == "2026-05-12 14:00:00"
    assert calls["weather_situation"]["date"] == "20260512"
