from app.agent.prompts.tool_registry import ASSISTANT_TOOL_NAMES, ASSISTANT_TOOL_ORDER


def test_assistant_mode_exposes_deck_ppt_tool_not_low_level_renderer():
    assert "create_pptx_from_deck" in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_deck" in ASSISTANT_TOOL_ORDER

    assert "create_pptx" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx" not in ASSISTANT_TOOL_ORDER
