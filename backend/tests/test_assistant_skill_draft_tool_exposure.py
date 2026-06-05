from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.tools import create_global_tool_registry


def test_assistant_mode_exposes_create_skill_draft_and_view_skill():
    assistant_tools = get_tools_by_mode("assistant")
    assistant_order = get_tool_order("assistant")

    assert "view_skill" in assistant_tools
    assert "create_skill_draft" in assistant_tools
    assert "view_skill" in assistant_order
    assert "create_skill_draft" in assistant_order


def test_non_assistant_modes_do_not_expose_create_skill_draft():
    for mode in ("expert", "query", "report", "chart", "ops", "social"):
        assert "create_skill_draft" not in get_tools_by_mode(mode)
        assert "create_skill_draft" not in get_tool_order(mode)


def test_global_registry_registers_skill_tools():
    registry = create_global_tool_registry()
    tools = registry.list_tools()

    assert "view_skill" in tools
    assert "create_skill_draft" in tools


def test_assistant_prompt_requires_user_confirmation_before_skill_draft():
    prompt = build_assistant_prompt(["create_skill_draft", "view_skill", "list_skills"])

    assert "create_skill_draft" in prompt
    assert "候选技能" in prompt
    assert "用户明确同意" in prompt
    assert "不要调用" in prompt
