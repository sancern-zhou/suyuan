from app.agent.prompts.tool_registry import ASSISTANT_TOOL_ORDER, get_tools_by_mode
from app.agent.prompts.assistant_prompt import build_assistant_prompt


def test_assistant_mode_does_not_expose_task_tools_or_todowrite():
    tools = get_tools_by_mode("assistant")

    assert "TodoWrite" not in tools
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(tools)
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(ASSISTANT_TOOL_ORDER)


def test_weather_image_tool_is_available_in_assistant_and_expert_modes():
    assert "get_platform_weather_image" in get_tools_by_mode("assistant")
    assert "get_platform_weather_image" in get_tools_by_mode("expert")


def test_assistant_prompt_does_not_describe_task_tools():
    prompt = build_assistant_prompt(["TaskCreate", "TaskUpdate", "TaskList", "TaskGet"])

    assert "TaskCreate" not in prompt
    assert "TaskUpdate" not in prompt
    assert "TaskList" not in prompt
    assert "TaskGet" not in prompt
    assert "任务清单工具" not in prompt


def test_assistant_prompt_distinguishes_freeform_and_template_diagram_references():
    prompt = build_assistant_prompt(["create_diagram_artifact", "read_file"])

    assert "diagram_mode=\"freeform\"" in prompt
    assert "freeform-index.md" in prompt
    assert "freeform-architecture.md" in prompt
    assert "canvas/shapes/connectors/groups" in prompt
    assert "diagram_mode=\"template\"" in prompt
    assert "references/index.md" in prompt
    assert "layers/groups/items" in prompt
