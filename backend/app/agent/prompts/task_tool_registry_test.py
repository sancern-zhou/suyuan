from app.agent.prompts.tool_registry import ASSISTANT_TOOL_ORDER, BOARD_TOOL_ORDER, CHART_TOOL_ORDER, get_tools_by_mode
from app.agent.prompts.assistant_prompt import build_assistant_prompt
from app.agent.prompts.board_prompt import build_board_prompt
from app.agent.prompts.chart_prompt import build_chart_prompt
from app.agent.prompts.ops_prompt import build_ops_prompt
from app.agent.prompts.social_prompt import build_social_prompt



def test_assistant_mode_does_not_expose_task_tools_or_todowrite():
    tools = get_tools_by_mode("assistant")

    assert "TodoWrite" not in tools
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(tools)
    assert {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}.isdisjoint(ASSISTANT_TOOL_ORDER)


def test_assistant_mode_does_not_expose_diagram_artifact_tool():
    tools = get_tools_by_mode("assistant")

    assert "create_diagram_artifact" not in tools
    assert "create_diagram_artifact" not in ASSISTANT_TOOL_ORDER


def test_weather_image_tool_is_reserved_for_expert_mode():
    assert "get_platform_weather_image" not in get_tools_by_mode("assistant")
    assert "get_platform_weather_image" in get_tools_by_mode("expert")


def test_domain_tender_tools_are_reserved_for_specialist_workspaces():
    assert "qianlima_realtime_tender" not in get_tools_by_mode("assistant")
    assert "execute_tender_sql_query" not in ASSISTANT_TOOL_ORDER


def test_assistant_mode_keeps_lightweight_office_and_web_tools():
    tools = get_tools_by_mode("assistant")

    assert {
        "list_directory", "search_files", "read_file", "write_file", "edit_file", "grep",
        "create_html_artifact", "execute_python", "web_search", "web_fetch", "browser",
    }.issubset(tools)
    assert "manage_editable_ppt" not in tools
    assert "create_report_package" in tools
    assert "render_report_package" in tools
    assert "validate_report_package" in tools
    assert "bash" not in tools


def test_ops_mode_exposes_call_sub_agent_for_audit_confirmation_gate():
    tools = get_tools_by_mode("ops")

    assert "call_sub_agent" in tools


def test_ops_mode_no_longer_exposes_report_package_tools():
    tools = get_tools_by_mode("ops")

    assert "create_report_chart" not in tools
    assert "create_report_package" not in tools
    assert "validate_report_package" not in tools


def test_ops_prompt_stays_review_only_and_hands_off_report_generation():
    prompt = build_ops_prompt(["call_sub_agent", "ops_audit_run_rules"])

    assert "## 复核交接" in prompt
    assert "report_input_path" in prompt
    assert "call_sub_agent(target_mode='ops')" in prompt
    assert "ops_audit_submit_review" in prompt
    assert "issue_id" in prompt
    assert "禁止仅返回 excluded_items" in prompt
    assert "report_ready=false" in prompt
    assert "正式报告优先使用" not in prompt
    assert "生成标准报告包" not in prompt
    assert "不要把正式报告委托给 `report` 子Agent" in prompt
    assert "当前模式只负责数据抽取、规则/语义复核和结果文件落盘" in prompt


def test_social_mode_exposes_report_package_tools_for_main_agent_reporting():
    tools = get_tools_by_mode("social")

    assert "create_report_chart" in tools
    assert "create_report_package" in tools
    assert "validate_report_package" in tools


def test_social_prompt_prefers_main_agent_report_generation():
    prompt = build_social_prompt(
        ["create_report_chart", "create_report_package", "validate_report_package", "call_sub_agent"],
    )

    assert "正式报告、QMD、Word 和报告包由当前主 Agent 直接完成" in prompt
    assert "不委托 `report` 子Agent" in prompt
    assert "运维审核子Agent只负责复核和持久化记录" in prompt
    assert "target_mode=\"report\"" not in prompt


def test_ops_prompt_discovers_active_audit_skill_without_hardcoded_shared_path():
    prompt = build_ops_prompt(["list_skills", "read_file", "ops_audit_run_rules"])

    assert "list_skills(keyword='工单审核')" in prompt
    assert "完整读取返回的技能文件" in prompt
    assert "backend/docs/skills" not in prompt
    assert "ops_work_order_audit.md" not in prompt


def test_assistant_prompt_does_not_describe_task_tools():
    prompt = build_assistant_prompt(["TaskCreate", "TaskUpdate", "TaskList", "TaskGet"])

    assert "TaskCreate" not in prompt
    assert "TaskUpdate" not in prompt
    assert "TaskList" not in prompt
    assert "TaskGet" not in prompt
    assert "任务清单工具" not in prompt


def test_assistant_prompt_is_a_workspace_router():
    prompt = build_assistant_prompt(["call_sub_agent"])

    assert "call_sub_agent" in prompt
    assert "target_mode=\"board\"" in prompt
    assert "promote_to_workspace=true" in prompt
    assert "只表示本次委托使用的专家执行器" in prompt
    assert "单轮架构图或流程图可以直接委托" in prompt
    assert "create_report_chart" not in prompt
    assert "execute_python" not in prompt
    assert "create_diagram_artifact" not in prompt


def test_board_mode_exposes_drawio_board_not_diagram_artifact():
    tools = get_tools_by_mode("board")

    assert "create_drawio_board" in tools
    assert "render_drawio_board_candidate" in tools
    assert "accept_drawio_board_candidate" in tools
    assert "create_drawio_board" in BOARD_TOOL_ORDER
    assert "render_drawio_board_candidate" in BOARD_TOOL_ORDER
    assert "accept_drawio_board_candidate" in BOARD_TOOL_ORDER
    assert "create_drawio_board" not in CHART_TOOL_ORDER
    assert "analyze_image" not in tools
    assert "analyze_image" not in BOARD_TOOL_ORDER
    assert "present_artifact" not in tools
    assert "create_diagram_artifact" not in tools
    assert "knowledge_qa_workflow" not in tools
    assert "knowledge_document_reader" not in tools

    from app.agent.tool_adapter import get_tool_schemas

    schemas = get_tool_schemas(mode="board")
    assert "analyze_image" not in {schema["name"] for schema in schemas}


def test_board_prompt_injects_authoritative_board_context():
    prompt = build_board_prompt(
        ["create_drawio_board"],
        board_context={
            "current_xml": "<mxfile><diagram id=\"board-1\">current</diagram></mxfile>",
            "selected_cells": [{"id": "node-1", "value": "站点A"}],
            "viewport": {"scale": 1.2},
            "current_request_images": [{"name": "board.png"}],
        },
    )

    assert '"structure": "current_xml"' in prompt
    assert '"visual_effect": "current_request_images"' in prompt
    assert '"on_conflict": "report_the_observed_difference"' in prompt
    assert "node-1" in prompt
    assert "board.png" in prompt
    assert "<mxfile><diagram id=\"board-1\">current</diagram></mxfile>" in prompt
    assert "render_drawio_board_candidate" in prompt
    assert "建议" in prompt
    assert "自主决定" in prompt
    assert "最多两轮" not in prompt
    assert "不得直接" not in prompt


def test_drawio_tool_schema_does_not_expose_current_xml_to_llm():
    tools = get_tools_by_mode("board")
    assert "create_drawio_board" in tools

    from app.agent.tool_adapter import get_tool_schemas

    schemas = get_tool_schemas(mode="board")
    drawio_schema = next(schema for schema in schemas if schema["name"] == "create_drawio_board")

    assert "current_xml" not in drawio_schema["parameters"]["properties"]
    assert "currentXml" not in drawio_schema["parameters"]["properties"]


def test_chart_prompt_does_not_embed_board_instructions_even_if_called_with_board_tool():
    prompt = build_chart_prompt(["create_drawio_board", "read_file"])

    assert "Draw.io" not in prompt
    assert "board_context" not in prompt
    assert "create_diagram_artifact" not in prompt


def test_chart_prompt_omits_drawio_guide_when_board_tool_unavailable():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert "Draw.io 画板强约束文档" not in prompt
    assert "board_context" not in prompt


def test_chart_prompt_has_no_accidental_python_string_fragments_or_duplicate_headings():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert '        "##' not in prompt
    assert "series 在顶层" not in prompt
    assert "execute_echarts_python" not in prompt
    assert "read_file" not in prompt
