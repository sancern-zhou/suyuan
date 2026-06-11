from app.agent.prompts.tool_registry import ASSISTANT_TOOL_NAMES, ASSISTANT_TOOL_ORDER
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool


def test_assistant_mode_exposes_ppt_master_tool_not_deck_or_low_level_renderer():
    assert "create_pptx_with_ppt_master" in ASSISTANT_TOOL_NAMES
    assert "create_pptx_with_ppt_master" in ASSISTANT_TOOL_ORDER
    assert "analyze_image" in ASSISTANT_TOOL_NAMES
    assert "analyze_image" in ASSISTANT_TOOL_ORDER

    assert "analyze_pptx_template" not in ASSISTANT_TOOL_NAMES
    assert "analyze_pptx_template" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_ORDER

    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx" not in ASSISTANT_TOOL_ORDER


def test_assistant_mode_does_not_expose_retired_word_or_office_xml_tools():
    retired_tools = {
        "edit_word_document",
        "word_edit",
        "find_replace_word",
        "accept_word_changes",
        "unpack_office",
        "pack_office",
    }

    assert retired_tools.isdisjoint(ASSISTANT_TOOL_NAMES)
    assert retired_tools.isdisjoint(ASSISTANT_TOOL_ORDER)


def test_assistant_prompt_requires_reading_ppt_guide_before_generation():
    prompt = build_assistant_prompt(["create_pptx_with_ppt_master", "read_file"])

    assert "PPT操作指南.md" in prompt
    assert "生成 PPT 前" in prompt
    assert "必须先阅读" in prompt


def test_ppt_master_schema_requires_reading_ppt_guide_before_generation():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    serialized = str(schema)
    assert "PPT操作指南.md" in serialized
    assert "生成 PPT 前" in serialized
    assert "必须先阅读" in serialized


def test_ppt_master_schema_exposes_agent_shape_plan():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    properties = schema["parameters"]["properties"]
    assert "slide_plan" in properties
    assert "Agent 自行规划" in properties["slide_plan"]["description"]
    assert "shape" in properties["slide_plan"]["description"].lower()


def test_ppt_master_schema_requires_title_to_prevent_empty_tool_calls():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    assert schema["parameters"]["required"] == ["title"]
