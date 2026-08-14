from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from config.settings import settings


def test_xuchang_mode_prompts_do_not_change_shared_prompts(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    xuchang_query = build_react_system_prompt("query")
    xuchang_expert = build_react_system_prompt("expert")

    assert "## Agentic GIS 视觉交互" not in xuchang_query
    assert "每个结论必须区分" not in xuchang_expert
    assert "### 常见机制检查" not in xuchang_expert

    monkeypatch.setattr(settings, "project_id", "default")
    shared_query = build_react_system_prompt("query")
    shared_expert = build_react_system_prompt("expert")

    assert "## Agentic GIS 视觉交互" in shared_query
    assert "每个结论必须区分" in shared_expert
    assert "### 常见机制检查" in shared_expert


def test_xuchang_disables_guangdong_query_tools_only_for_xuchang(monkeypatch):
    standard_report_tools = {
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_station_standard_report",
        "query_station_standard_yoy_report",
    }
    monkeypatch.setattr(settings, "project_id", "xuchang")
    for mode in ("query", "report", "chart"):
        tools = get_tools_by_mode(mode)
        assert "get_5min_data" not in tools
        assert "analyze_city_pollutant_rankings" not in tools
        assert standard_report_tools.isdisjoint(tools)

    monkeypatch.setattr(settings, "project_id", "default")
    assert "get_5min_data" in get_tools_by_mode("query")
    assert "analyze_city_pollutant_rankings" in get_tools_by_mode("query")
    assert standard_report_tools.issubset(get_tools_by_mode("query"))


def test_report_prompt_has_no_guangdong_business_text(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")

    prompt = build_react_system_prompt("report")

    assert "广东" not in prompt
    assert "粤东" not in prompt
    assert "粤西" not in prompt
    assert "粤北" not in prompt
    assert "珠三角" not in prompt
