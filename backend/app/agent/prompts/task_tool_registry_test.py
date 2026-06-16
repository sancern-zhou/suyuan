from app.agent.prompts.tool_registry import ASSISTANT_TOOL_ORDER, CHART_TOOL_ORDER, get_tools_by_mode
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.agent.prompts.chart_prompt import DRAWIO_GUIDE_PATHS, build_chart_prompt
from app.agent.prompts.ops_prompt import build_ops_prompt


def test_assistant_mode_does_not_expose_task_tools_or_todowrite():
    tools = get_tools_by_mode("assistant")

    assert "TodoWrite" not in tools
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(tools)
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(ASSISTANT_TOOL_ORDER)


def test_assistant_mode_does_not_expose_diagram_artifact_tool():
    tools = get_tools_by_mode("assistant")

    assert "create_diagram_artifact" not in tools
    assert "create_diagram_artifact" not in ASSISTANT_TOOL_ORDER


def test_weather_image_tool_is_available_in_assistant_and_expert_modes():
    assert "get_platform_weather_image" in get_tools_by_mode("assistant")
    assert "get_platform_weather_image" in get_tools_by_mode("expert")


def test_ops_mode_exposes_call_sub_agent_for_audit_confirmation_gate():
    tools = get_tools_by_mode("ops")

    assert "call_sub_agent" in tools


def test_ops_prompt_requires_sub_agent_excluded_items_gate_before_report_package():
    prompt = build_ops_prompt(["call_sub_agent", "create_report_package"])

    assert "call_sub_agent(target_mode='ops')" in prompt
    assert "excluded_items" in prompt
    assert "剔除这些 excluded_items" in prompt


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


def test_chart_mode_exposes_drawio_board_not_diagram_artifact():
    tools = get_tools_by_mode("chart")

    assert "create_drawio_board" in tools
    assert "create_drawio_board" in CHART_TOOL_ORDER
    assert "analyze_image" not in tools
    assert "analyze_image" not in CHART_TOOL_ORDER
    assert "present_artifact" not in tools
    assert "present_artifact" not in CHART_TOOL_ORDER
    assert "create_diagram_artifact" not in tools
    assert "create_diagram_artifact" not in CHART_TOOL_ORDER
    assert "knowledge_qa_workflow" not in tools
    assert "knowledge_qa_workflow" not in CHART_TOOL_ORDER
    assert "knowledge_document_reader" not in tools
    assert "knowledge_document_reader" not in CHART_TOOL_ORDER


def test_chart_prompt_injects_authoritative_board_context():
    prompt = build_chart_prompt(
        ["create_drawio_board"],
        board_context={
            "current_xml": "<mxfile><diagram id=\"board-1\">current</diagram></mxfile>",
            "selected_cells": [{"id": "node-1", "value": "站点A"}],
            "viewport": {"scale": 1.2},
        },
    )

    assert "board_context.current_xml" in prompt
    assert "权威状态" in prompt
    assert "node-1" in prompt
    assert "<mxfile><diagram id=\"board-1\">current</diagram></mxfile>" in prompt
    assert "selected_cells[*].xml" in prompt
    assert "selected_cells[*].geometry" in prompt
    assert "update_label" in prompt
    assert 'target="selected"' in prompt
    assert 'create_drawio_board(operation="edit")' in prompt
    assert "只传结构化 `operations`" in prompt


def test_drawio_tool_schema_does_not_expose_current_xml_to_llm():
    tools = get_tools_by_mode("chart")
    assert "create_drawio_board" in tools

    from app.agent.tool_adapter import get_tool_schemas

    schemas = get_tool_schemas(mode="chart")
    drawio_schema = next(schema for schema in schemas if schema["name"] == "create_drawio_board")

    assert "current_xml" not in drawio_schema["parameters"]["properties"]
    assert "currentXml" not in drawio_schema["parameters"]["properties"]


def test_chart_prompt_mentions_confirmed_board_snapshot_native_multimodal_input():
    prompt = build_chart_prompt(["create_drawio_board", "analyze_image"])

    assert "确认画板修改" in prompt
    assert "本轮上传图片和画板截图已经作为原生多模态输入提供" in prompt
    assert "直接基于可见图片理解图表类型、样式、配色和布局" in prompt
    assert "视觉质量检查" in prompt
    assert "XML 仍然是权威状态" in prompt


def test_chart_prompt_treats_uploaded_images_as_native_multimodal_input():
    prompt = build_chart_prompt(["create_drawio_board", "read_file", "analyze_image"])

    assert "本轮上传图片和画板截图已经作为原生多模态输入提供" in prompt
    assert "直接基于可见图片理解图表类型、样式、配色和布局" in prompt
    assert "analysis_type" not in prompt
    assert "analyze_image" not in prompt
    assert "read_file(path, analysis_type=\"chart\")" not in prompt
    assert "可调用 `analyze_image` 对该截图做视觉质量检查" not in prompt


def test_chart_prompt_does_not_embed_drawio_tool_reading_instructions():
    prompt = build_chart_prompt(["create_drawio_board", "read_file"])

    assert "Draw.io 画板强约束文档" not in prompt
    assert "第一次调用 `create_drawio_board` 之前" not in prompt
    assert "create_diagram_artifact" not in prompt
    for guide_path in DRAWIO_GUIDE_PATHS:
        assert guide_path not in prompt


def test_chart_prompt_omits_drawio_guide_when_board_tool_unavailable():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert "Draw.io 画板强约束文档" not in prompt
    for guide_path in DRAWIO_GUIDE_PATHS:
        assert guide_path not in prompt


def test_chart_prompt_has_no_accidental_python_string_fragments_or_duplicate_headings():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert '        "##' not in prompt
    assert prompt.count("### ✅ 正确示例：series 在顶层") == 1
