from app.agent.prompts.tool_registry import get_tools_by_mode


def test_assistant_mode_exposes_task_tools_instead_of_todowrite():
    tools = get_tools_by_mode("assistant")

    assert "TodoWrite" not in tools
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.issubset(tools)
