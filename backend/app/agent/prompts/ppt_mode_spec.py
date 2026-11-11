"""Contracts for the dedicated presentation mode (skill-route workflow)."""

from pathlib import Path

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.agent.runtime.mode_capabilities import supports_native_multimodal


def test_ppt_mode_exposes_skill_route_presentation_tools():
    tools = get_tools_by_mode("ppt")

    assert list(tools) == get_tool_order("ppt")
    assert {
        "list_skills",
        "view_skill",
        "validate_pptx",
        "read_file",
        "edit_file",
        "create_business_chart",
        "execute_python",
        "web_search",
    }.issubset(tools)
    # 退役管线不得回归
    assert {"create_pptx_with_ppt_master", "manage_editable_ppt"}.isdisjoint(tools)
    assert {
        "ops_audit_fetch_dataset",
        "execute_sql_query",
        "create_drawio_board",
        "call_sub_agent",
        "analyze_image",
    }.isdisjoint(tools)

    from app.agent.tool_adapter import get_tool_schemas

    schema_names = {schema["name"] for schema in get_tool_schemas(mode="ppt")}
    assert {"execute_python", "validate_pptx", "read_file", "edit_file", "view_skill"}.issubset(schema_names)
    assert "create_drawio_board" not in schema_names


def test_ppt_mode_prompt_uses_skill_route_workflow_by_default():
    prompt = build_react_system_prompt("ppt")

    assert "幻灯片智能体" in prompt
    assert "跳过模式确认" in prompt
    # 技能路线：先读技能，再沙箱生成
    assert "view_skill" in prompt
    assert "pptx_authoring" in prompt
    assert "execute_python" in prompt
    assert "artifact_path" in prompt
    assert "增量修改受影响页面" in prompt
    # 质量闭环：确定性 gate + 视觉自评双过
    assert "validate_pptx" in prompt
    assert "as_multimodal_attachment" in prompt
    assert "worst_pages" in prompt
    assert "双过" in prompt or "视觉自评无 fail 页" in prompt
    # 退役管线不得出现在提示词
    assert "manage_editable_ppt" not in prompt
    assert "create_pptx_with_ppt_master" not in prompt
    # 复刻参考图的多模态纪律保留
    assert "实际看到原图像素" in prompt


def test_ppt_skill_references_define_qa_loop_protocol():
    qa_loop = (
        Path(__file__).resolve().parents[3]
        / "docs/skills/pptx_authoring/references/qa-loop.md"
    ).read_text(encoding="utf-8")
    assert "修复对照表" in qa_loop
    assert "视觉自评" in qa_loop
    assert "as_multimodal_attachment" in qa_loop


def test_ppt_mode_prompt_keeps_memory_preferences():
    prompt = build_react_system_prompt(
        "ppt",
        memory_context="用户偏好：深蓝色、简洁风格",
        memory_file_path="/tmp/MEMORY.md",
    )

    assert "用户偏好：深蓝色、简洁风格" in prompt
    assert "MEMORY.md" in prompt and "记忆文件路径" in prompt


def test_ppt_mode_accepts_native_image_references():
    assert supports_native_multimodal("ppt") is True
