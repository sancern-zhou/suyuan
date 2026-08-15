"""Jiangsu-specific social mode tool surface (moved from the shared suite)."""
from app.project_config.loader import load_project_context


def test_jiangsu_social_mode_owns_a_read_only_project_tool_surface():
    context = load_project_context("jiangsu-ops")
    tools = context.manifest.backend.agent_mode_tools["social"]

    assert "jiangsu_fetch_city_data" in tools
    assert "jiangsu_fetch_station_alarm_logs" in tools
    assert "schedule_task" in tools
    assert "jiangsu_execute_device_control" not in tools
    assert "call_sub_agent" not in tools
    assert "bash" not in tools
