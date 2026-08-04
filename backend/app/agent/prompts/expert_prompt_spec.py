from app.agent.prompts.expert_prompt import build_expert_prompt
from app.agent.prompts.tool_registry import AGENT_HIDDEN_TOOL_NAMES, get_tools_by_mode


def test_expert_mode_exposes_meteorology_and_remote_sensing_tools():
    tools = get_tools_by_mode("expert")

    assert {
        "get_weather_data",
        "get_universal_meteorology",
        "get_observed_meteorology",
        "get_weather_forecast",
        "get_satellite_data",
        "get_gems_image",
        "get_sentinel5p_image",
        "get_fire_hotspots",
    }.issubset(tools)


def test_hidden_tools_are_not_exposed_by_any_agent_mode():
    modes = (
        "assistant", "ppt", "expert", "query", "report", "social", "chart", "board",
        "ops", "graph", "memory_consolidator", "deliberation_meteorology",
        "deliberation_monitoring", "deliberation_chemistry", "deliberation_reviewer",
    )

    for mode in modes:
        assert AGENT_HIDDEN_TOOL_NAMES.isdisjoint(get_tools_by_mode(mode))


def test_expert_prompt_requires_weather_forecast_and_remote_sensing_evidence_checks():
    prompt = build_expert_prompt([])

    assert "遥感-气象空气质量分析专家" in prompt
    assert "未来风险" in prompt
    assert "遥感来源" in prompt
    assert "不能直接等同于地面浓度、排放量或定量贡献" in prompt
