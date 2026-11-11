from app.agent.prompts.tool_registry import (
    ASSISTANT_TOOL_NAMES,
    ASSISTANT_TOOL_ORDER,
    PPT_TOOL_NAMES,
    PPT_TOOL_ORDER,
)
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.agent.tool_adapter import get_tool_schemas
def test_assistant_and_ppt_modes_use_skill_route_not_retired_pipelines():
    """PPT 管线（ppt_master/editable_ppt）已退役：ppt 模式走技能路线。"""
    for retired in ("create_pptx_with_ppt_master", "manage_editable_ppt"):
        assert retired not in ASSISTANT_TOOL_NAMES
        assert retired not in ASSISTANT_TOOL_ORDER
        assert retired not in PPT_TOOL_NAMES
    for needed in ("execute_python", "validate_pptx", "view_skill"):
        assert needed in PPT_TOOL_NAMES
    assert "revise_pptx_with_ppt_master" not in ASSISTANT_TOOL_NAMES
    assert "revise_pptx_with_ppt_master" not in ASSISTANT_TOOL_ORDER
    assert "analyze_pptx_template" not in ASSISTANT_TOOL_NAMES
    assert "analyze_pptx_template" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_template" not in ASSISTANT_TOOL_ORDER

    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx_from_deck" not in ASSISTANT_TOOL_ORDER
    assert "create_pptx" not in ASSISTANT_TOOL_NAMES
    assert "create_pptx" not in ASSISTANT_TOOL_ORDER


def test_assistant_and_ppt_modes_do_not_expose_dedicated_image_analysis_tool():
    assert "analyze_image" not in ASSISTANT_TOOL_NAMES
    assert "analyze_image" not in ASSISTANT_TOOL_ORDER
    assert "analyze_image" not in PPT_TOOL_NAMES
    assert "analyze_image" not in PPT_TOOL_ORDER


def test_assistant_prompt_does_not_advertise_dedicated_image_analysis_tool():
    prompt = build_assistant_prompt(["read_file"])

    assert "`analyze_image`" not in prompt
    # 多模态看图统一走 read_file(as_multimodal_attachment)（工具描述与技能协议承载），
    # 助手提示词不内联工具参数细节


def test_tool_schema_adapter_never_exposes_dedicated_image_analysis_tool():
    schemas = get_tool_schemas(allowed_tool_names=["analyze_image"])

    assert "analyze_image" not in {schema["name"] for schema in schemas}


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


def test_assistant_prompt_routes_ppt_through_skill_pipeline():
    """PPT 管线退役后：助手提示词把 PPT 制作交给 ppt 模式（技能路线），不指向已删工具。"""
    prompt = build_assistant_prompt(list(ASSISTANT_TOOL_ORDER))
    assert "create_pptx_with_ppt_master" not in prompt
    assert "manage_editable_ppt" not in prompt
    assert "PPT" in prompt or "ppt" in prompt
