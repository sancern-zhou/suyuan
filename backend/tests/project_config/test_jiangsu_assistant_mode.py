from pathlib import Path

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tool_order
from app.project_config.loader import load_project_context
from app.tools import create_global_tool_registry
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_TOOLS = [
    "list_session_resources",
    "read_session_resource",
    "publish_session_file",
    "read_file",
    "edit_file",
    "write_file",
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    "web_search",
    "web_fetch",
    "execute_python",
    "create_report_chart",
    "create_report_package",
    "render_report_package",
    "validate_report_package",
    "manage_editable_ppt",
    "create_pptx_with_ppt_master",
    "validate_pptx",
]


def test_jiangsu_declares_assistant_mode_and_reviewed_tools():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    assert "assistant" in context.manifest.frontend.agent_modes
    assert context.manifest.backend.agent_mode_tools["assistant"] == EXPECTED_TOOLS
    assert (
        context.manifest.backend.mode_prompt_files["assistant"]
        == "projects/jiangsu-ops/prompts/assistant.md"
    )


def test_jiangsu_assistant_mode_loads_project_prompt_and_tool_surface(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    assert get_tool_order("assistant") == EXPECTED_TOOLS
    prompt = build_react_system_prompt("assistant")

    assert "江苏省运维审核管理服务平台" in prompt
    assert "read_session_resource" in prompt
    assert "knowledge_qa_workflow" in prompt
    assert "bash" not in prompt
    assert "browser" not in prompt
    assert "call_sub_agent" not in prompt
    assert "broadcast_social_users" not in prompt


def test_jiangsu_assistant_tools_are_all_registered():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    registered = set(create_global_tool_registry(context=context).list_tools())

    assert set(EXPECTED_TOOLS).issubset(registered)


def test_jiangsu_ops_mode_includes_qc_review_tools():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    ops_tools = context.manifest.backend.agent_mode_tools["ops"]
    assert "jiangsu_submit_fault_work_order_review" in ops_tools
    assert "jiangsu_fetch_qc_task_history" in ops_tools
    assert "jiangsu_fetch_station_environment_history" in ops_tools


def test_jiangsu_fault_work_order_review_tool_is_registered():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    registered = set(create_global_tool_registry(context=context).list_tools())

    assert "jiangsu_submit_fault_work_order_review" in registered
