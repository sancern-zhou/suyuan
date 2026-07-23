"""Contracts for the dedicated editable presentation mode."""

from pathlib import Path

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import PPT_TOOL_ORDER, get_tools_by_mode
from app.agent.runtime.mode_capabilities import supports_native_multimodal


def test_ppt_mode_exposes_focused_editable_presentation_tools():
    tools = get_tools_by_mode("ppt")

    assert list(tools) == list(PPT_TOOL_ORDER)
    assert {
        "manage_editable_ppt",
        "validate_pptx",
        "read_file",
        "edit_file",
        "create_report_chart",
        "analyze_image",
        "web_search",
    }.issubset(tools)
    assert {
        "ops_audit_fetch_dataset",
        "execute_sql_query",
        "create_drawio_board",
        "call_sub_agent",
    }.isdisjoint(tools)

    from app.agent.tool_adapter import get_tool_schemas

    schema_names = {schema["name"] for schema in get_tool_schemas(mode="ppt")}
    assert {"manage_editable_ppt", "validate_pptx", "read_file", "edit_file"}.issubset(schema_names)
    assert "create_drawio_board" not in schema_names


def test_ppt_mode_prompt_uses_editable_incremental_workflow_by_default():
    prompt = build_react_system_prompt("ppt")

    assert "幻灯片智能体" in prompt
    assert "manage_editable_ppt" in prompt
    assert "app/tools/office/editable_ppt/references/index.md" in prompt
    assert "增量" in prompt
    assert "无需从头重新生成" in prompt
    assert "validate_pptx" in prompt
    assert "create_pptx_with_ppt_master" in prompt
    assert "兼容" in prompt
    assert "锚点页只是中间检查点" in prompt
    assert "不得把锚点页当作最终交付" in prompt
    assert "逐页读取渲染图" in prompt
    assert "finalize 返回 success=true" in prompt
    assert "不要使用渐变、filter、transform、box-shadow" in prompt
    assert "每个承载可见文字的叶子节点" in prompt
    assert "诊断是定位索引，不是源码" in prompt
    assert "修改前必须读取" in prompt
    assert "diagnostic.status=unchanged" in prompt
    assert "不得立即重复同一种修改" in prompt
    assert "一次读取全部受影响源码" in prompt
    assert "expected_slide_count" in prompt


def test_ppt_workflow_defines_diagnostic_driven_stage_protocol():
    workflow = Path(
        "app/tools/office/editable_ppt/references/workflow.md"
    ).read_text(encoding="utf-8")
    headings = [
        "材料理解",
        "大纲规划",
        "初稿生成",
        "低成本预览",
        "批量修复",
        "严格编译",
        "验证与交付",
    ]
    assert all(
        f"## {index}. {heading}" in workflow
        for index, heading in enumerate(headings, 1)
    )
    assert workflow.index("读取全部受影响源码") < workflow.index("edit_sources")
    assert "read_report" in workflow
    assert "原始报告只有在结构化诊断不足时" in workflow


def test_ppt_mode_prompt_keeps_memory_preferences():
    prompt = build_react_system_prompt(
        "ppt",
        memory_context="用户偏好：深蓝色、简洁风格",
        memory_file_path="/tmp/MEMORY.md",
    )

    assert "用户偏好：深蓝色、简洁风格" in prompt
    assert "/tmp/MEMORY.md" in prompt


def test_ppt_mode_accepts_native_image_references():
    assert supports_native_multimodal("ppt") is True
