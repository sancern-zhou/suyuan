import pytest

from app.agent.prompts import prompt_builder
from app.agent.prompts.tool_registry import _build_tool_dict
from app.tools.base.registry import ToolRegistry
from app.tools.visualization.create_report_chart.tool import CreateReportChartTool


@pytest.mark.parametrize("project_override", [False, True])
@pytest.mark.parametrize("mode", ["query", "expert", "report", "assistant", "chart", "ppt", "ops", "social"])
def test_chart_priority_applies_to_default_and_project_prompts(monkeypatch, mode, project_override):
    monkeypatch.setattr(prompt_builder, "load_project_mode_prompt", lambda _: "项目提示词" if project_override else None)
    monkeypatch.setattr(prompt_builder, "get_tools_by_mode", lambda _: {})
    prompt = prompt_builder.build_react_system_prompt(mode, available_tools=[])
    policy = prompt.split("## 绘图工具优先级（共享模式约定）")[-1]
    assert "create_business_chart" in policy
    if mode == "query":
        assert "问数模式以 `execute_echarts_python`（ECharts 交互图）为主要绘图工具" in policy
        assert "不要把问数常规趋势" in policy
    else:
        assert "以 `execute_python`（Matplotlib/Seaborn）为主要绘图工具" in policy
        assert "辅助需要交互探索" in policy


def test_business_chart_is_exposed_once_under_canonical_name():
    tool = CreateReportChartTool()
    assert tool.name == "create_business_chart"
    assert tool.get_function_schema()["name"] == tool.name
    names = _build_tool_dict(["create_business_chart"])
    assert list(names) == ["create_business_chart"]
    registry = object.__new__(ToolRegistry)
    registry._tools = {tool.name: {"tool": tool, "function_schema": tool.get_function_schema()}}
    registry._priority_order = [(213, tool.name)]
    assert registry.get_tool("create_business_chart") is tool
    assert registry.get_tool_data("create_business_chart") is registry.get_tool_data(tool.name)
    assert registry.get_tool("create_report_chart") is None
    assert registry.list_tools() == ["create_business_chart"]
