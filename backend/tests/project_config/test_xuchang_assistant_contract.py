"""The active Xuchang entry point must match its office and specialist boundaries."""

import pytest

from config.settings import settings
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode


@pytest.fixture(autouse=True)
def xuchang(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")


def test_assistant_loads_project_office_and_code_contract():
    prompt = build_react_system_prompt("assistant")
    for text in ("仓库后端代码检索与解释", "manage_scheduled_tasks", "create_report_package",
                 "同一报告包", "输入输出行数", "线上已验证", "技术问题时，允许"):
        assert text in prompt
    assert "scheduled_tasks/tasks.json" not in prompt
    for mode in ("query", "expert", "report", "chart"):
        assert f'target_mode="{mode}"' not in prompt
    tools = get_tools_by_mode("assistant")
    assert {"create_scheduled_task", "manage_scheduled_tasks", "create_report_package", "execute_python",
            "grep", "read_file", "search_files"}.issubset(tools)
    assert {"bash", "browser", "execute_tender_sql_query"}.isdisjoint(tools)


def test_actual_registered_schemas_only_expose_specialists():
    from app.tools import global_tool_registry
    for name in ("create_scheduled_task", "manage_scheduled_tasks", "create_report_package", "execute_python"):
        assert global_tool_registry.get_tool(name) is not None
    for name in ("call_sub_agent", "run_agent_workflow"):
        tool = global_tool_registry.get_tool(name)
        properties = tool.get_function_schema()["parameters"]["properties"]
        if name == "run_agent_workflow":
            properties = properties["workflow"]["properties"]["nodes"]["items"]["properties"]
        targets = set(properties["target_mode"]["enum"])
        assert {"query", "expert", "report", "chart"}.isdisjoint(targets)
        assert {"query_monitoring_station", "query_monitoring_city", "query_forecast",
                "expert_meteorology", "expert_analysis"}.issubset(targets)
