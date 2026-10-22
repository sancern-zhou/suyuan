from pathlib import Path

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tool_order
from app.project_config.loader import load_project_context
from app.tools import create_global_tool_registry
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[3]
# 2026-10-21 随 main 合入 assistant 角色契约：项目只声明角色白名单内的能力，
# 专业执行（写文件/图表/报告包/PPT/知识库问答）收敛到委托路径。
EXPECTED_TOOLS = [
    "list_session_resources",
    "read_session_resource",
    "publish_session_file",
    "read_file",
    "edit_file",
    "web_search",
    "web_fetch",
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

    # 交互提问由共享层自动追加（INTERACTIVE_QUESTION_MODES）；角色白名单补充
    # 记忆/技能/委托/日程能力，任务与教练管理固定殿后（main 2026-10 角色契约）。
    role_extras = [
        "manage_assistant_memory",
        "list_skills",
        "view_skill",
        "call_sub_agent",
        "run_agent_workflow",
        "manage_assistant_schedule",
        "send_notification",
        "manage_assistant_runs",
        "session_search",
        "manage_assistant_tasks",
        "manage_assistant_coaching",
    ]
    assert get_tool_order("assistant") == EXPECTED_TOOLS + ["ask_user_question"] + role_extras
    prompt = build_react_system_prompt("assistant")

    assert "江苏省运维审核管理服务平台" in prompt
    assert "read_session_resource" in prompt
    assert "call_sub_agent" in prompt
    assert "bash" not in prompt
    assert "browser" not in prompt
    assert "broadcast_social_users" not in prompt


def test_jiangsu_assistant_tools_are_all_registered():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    registered = set(create_global_tool_registry(context=context).list_tools())

    assert set(EXPECTED_TOOLS).issubset(registered)


def test_jiangsu_ops_mode_includes_qc_review_tools():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    ops_tools = context.manifest.backend.agent_mode_tools["ops"]
    assert "submit_task_review" in ops_tools
    # 站房告警/动环历史/质控清单证据已并入 jiangsu_fetch_review_evidence 的 modules；
    # 质控任务明细面板仍由 jiangsu_fetch_qc_task_status 提供下钻。
    assert "jiangsu_fetch_review_evidence" in ops_tools
    assert "jiangsu_fetch_qc_task_status" in ops_tools


def test_jiangsu_fault_work_order_review_tool_is_registered():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    registered = set(create_global_tool_registry(context=context).list_tools())

    assert "submit_task_review" in registered


def test_jiangsu_geography_resolver_tool_is_registered_and_exposed():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    registered = set(create_global_tool_registry(context=context).list_tools())

    assert "jiangsu_resolve_geography" in registered
    assert "jiangsu_resolve_geography" in context.manifest.backend.tools
    assert "jiangsu_resolve_geography" in context.manifest.backend.agent_mode_tools["jiangsu_query"]
