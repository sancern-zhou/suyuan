from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.prompts.assistant_prompt import build_assistant_prompt


def test_assistant_mode_exposes_task_tools_instead_of_todowrite():
    tools = get_tools_by_mode("assistant")

    assert "TodoWrite" not in tools
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.issubset(tools)


def test_weather_image_tool_is_available_in_assistant_and_expert_modes():
    assert "get_platform_weather_image" in get_tools_by_mode("assistant")
    assert "get_platform_weather_image" in get_tools_by_mode("expert")


def test_assistant_prompt_defines_complex_multistep_task_threshold():
    prompt = build_assistant_prompt(["TaskCreate", "TaskUpdate", "TaskList", "TaskGet"])

    assert "8 个以上任务节点" in prompt
    assert "8 个及以下任务节点不要使用任务清单工具" in prompt
