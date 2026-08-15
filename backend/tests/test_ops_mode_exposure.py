import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.tools.social.spawn.tool import SpawnTool


def test_ops_mode_is_exposed_to_assistant_and_social_prompts():
    assistant_prompt = build_react_system_prompt("assistant")
    social_prompt = build_react_system_prompt("social")

    for prompt in (assistant_prompt, social_prompt):
        assert 'target_mode="ops"' in prompt
        assert "ops_agent_guide.md" in prompt
        assert "调用前先阅读" in prompt


def test_ops_mode_is_reachable_from_assistant_and_social_tools():
    assistant_tools = get_tools_by_mode("assistant")
    social_tools = get_tools_by_mode("social")
    ops_tools = get_tools_by_mode("ops")

    assert "call_sub_agent" in assistant_tools
    assert "call_sub_agent" in social_tools
    assert "spawn" in social_tools
    assert "execute_ops_sql_query" in ops_tools
    assert "execute_ops_sql_query" not in assistant_tools
    assert "execute_ops_sql_query" not in social_tools

    call_schema = CallSubAgentTool().get_function_schema()
    target_modes = call_schema["parameters"]["properties"]["target_mode"]["enum"]
    assert "ops" in target_modes

    spawn_schema = SpawnTool().get_function_schema()
    spawn_modes = spawn_schema["parameters"]["properties"]["manual_mode"]["enum"]
    assert "ops" in spawn_modes
