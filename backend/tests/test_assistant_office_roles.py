from types import SimpleNamespace

import pytest

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.delegation import delegation_error
from app.agent.workflow.profiles import get_agent_profile
from app.agent.workflow.target_mode_contract import target_mode_values
from config.settings import settings


@pytest.mark.parametrize("project", ["default", "xuchang"])
def test_assistant_and_office_roles_cannot_be_expanded_by_project_tools(monkeypatch, project):
    from app.agent.prompts import tool_registry

    monkeypatch.setattr(settings, "project_id", project)
    forbidden = {
        "execute_sql_query",
        "execute_crawler_sql_query",
        "execute_bigdata_sql_query",
        "execute_postgres_sql_query",
        "query_xcai_city_history",
        "get_weather_data",
        "get_weather_forecast",
        "create_business_chart",
        "create_report_package",
        "knowledge_qa_workflow",
        "knowledge_document_reader",
        "bash",
        "spawn",
    }
    for mode in ("social", "office"):
        assert forbidden.isdisjoint(get_tools_by_mode(mode))
    assert "execute_python" not in get_tools_by_mode("social")
    assert {"read_file", "edit_file"}.issubset(get_tools_by_mode("social"))
    assert "wait_task" not in get_tools_by_mode("social")
    assert {"manage_assistant_memory", "manage_assistant_runs"}.issubset(get_tools_by_mode("social"))
    assert "execute_python" in get_tools_by_mode("office")
    assert {"call_sub_agent", "run_agent_workflow"}.isdisjoint(get_tools_by_mode("office"))
    monkeypatch.setattr(
        tool_registry, "_get_project_tool_names_by_mode", lambda mode: list(forbidden)
    )
    assert forbidden.isdisjoint(get_tools_by_mode("social"))
    assert forbidden.isdisjoint(get_tools_by_mode("office"))


def test_office_is_a_leaf_child_of_assistant_and_retains_explicit_session_reuse():
    from app.tools.agent_tools.call_sub_agent import CallSubAgentTool

    assert "office" in target_mode_values()
    assert "assistant" not in target_mode_values()
    assert "social" not in target_mode_values()
    assert delegation_error("social", ["office"]) is None
    assert delegation_error("query", ["office"])
    assert delegation_error("office", ["knowledge"])
    assert delegation_error("social", ["assistant"])
    assert not get_agent_profile("office", profile="orchestrator").allow_delegation
    tool = CallSubAgentTool()
    assert not tool._should_auto_reuse_session("office", None, False, False)
    assert not tool._should_auto_reuse_session("office", "existing-office-session", False, False)
    assert get_tools_by_mode("assistant") == get_tools_by_mode("office")
    assert "办公模式（office）" in build_react_system_prompt("assistant")


@pytest.mark.parametrize("mode", ["social", "office"])
def test_extra_tools_cannot_restore_professional_execution(mode):
    from app.agent.runtime.agent_runtime import AgentRuntime
    from app.agent.runtime.types import RunState

    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.config = SimpleNamespace(
        extra_tool_names=["execute_sql_query", "create_report_package"]
    )
    runtime.executor = SimpleNamespace(tool_registry={"submit_result": object()})
    tools = runtime._allowed_tool_names_for_state(
        RunState(session_id="role-test", user_query="test", mode=mode)
    )
    assert "execute_sql_query" not in tools
    assert "create_report_package" not in tools
    assert "submit_result" in tools


@pytest.mark.parametrize("project", ["default", "xuchang"])
def test_assistant_media_contract_survives_project_prompt_overrides(monkeypatch, project):
    from app.agent.prompts.assistant_role_contract import ASSISTANT_MEDIA_CONTRACT

    monkeypatch.setattr(settings, "project_id", project)
    prompt = build_react_system_prompt("social")
    assert ASSISTANT_MEDIA_CONTRACT in prompt
    if project == "default":
        assert "所有图片、图表、文件必须主动发送给用户" not in prompt
        assert "{backend_host} + 相对路径" not in prompt
    assert "不使用通用 read_file、edit_file" not in prompt
