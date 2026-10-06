"""Xuchang overrides retain bounded delegation for both interactive parents."""

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.delegation import LEAF_MODES
from config.settings import settings


def test_xuchang_parent_overrides_enable_bounded_delegation(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    for mode in ("query", "expert"):
        tools = get_tools_by_mode(mode)
        assert {"run_agent_workflow", "call_sub_agent"}.issubset(tools)
        prompt = build_react_system_prompt(mode, available_tools=list(tools))
        assert "精简子 Agent 与依赖工作流" in prompt
        assert "query_monitoring_station" in prompt
    for mode in LEAF_MODES:
        assert not {"run_agent_workflow", "call_sub_agent"}.intersection(get_tools_by_mode(mode))
