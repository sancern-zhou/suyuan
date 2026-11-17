"""江西报告 DAG 项目子模式守门测试。

参照共享层 app/agent/workflow/project_policy_test.py 的模式：report 父策略
（agent_workflow_parents.report）把委派边界硬限制在三个噪声子模式，同时挡住
共享大气子模式与综合主模式；子模式为叶子节点，不可再委派或编排。
"""

from pathlib import Path

from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.delegation import delegation_error, is_leaf_mode
from app.agent.workflow.profiles import get_agent_profile
from app.agent.workflow.project_policy import prepare_node
from app.project_config.loader import load_project_context
from config.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[2]

NOISE_CHILD_MODES = (
    "noise_query_monitoring",
    "noise_query_evaluation",
    "noise_expert_analysis",
)


def test_report_parent_delegates_only_noise_children(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    for mode in NOISE_CHILD_MODES:
        assert delegation_error("report", [mode]) is None

    # 共享大气子模式与综合主模式一律拒绝
    for target in ("query_monitoring_station", "query_monitoring_city",
                   "query_forecast", "expert_meteorology", "expert_analysis"):
        error = delegation_error("report", [target])
        assert error is not None and "仅允许精简子 Agent" in error
    for target in ("query", "expert", "report"):
        error = delegation_error("report", [target])
        assert error is not None and "不允许作为子 Agent" in error


def test_noise_children_are_leaf_modes_and_cannot_delegate(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    for mode in NOISE_CHILD_MODES:
        assert is_leaf_mode(mode)
        assert not get_agent_profile(mode, profile="orchestrator").allow_delegation
        tools = get_tools_by_mode(mode)
        assert tools, f"{mode} must have explicit tool whitelist"
        assert "run_agent_workflow" not in tools
        assert "call_sub_agent" not in tools


def test_noise_children_prompts_load_with_delivery_contract(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    for mode in NOISE_CHILD_MODES:
        prompt = load_project_mode_prompt(mode, context=context)
        assert prompt is not None, f"{mode} prompt must be declared"
        assert "submit_result" in prompt
        assert "data_gaps" in prompt

    expert_prompt = load_project_mode_prompt("noise_expert_analysis", context=context)
    assert "counter_evidence" in expert_prompt
    assert "替代解释" in expert_prompt


def test_report_mode_is_integrator(monkeypatch):
    """报告父收敛为整合者：持编排工具，不持业务取数工具。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    report_tools = set(get_tools_by_mode("report"))
    assert "run_agent_workflow" in report_tools
    assert "call_sub_agent" not in report_tools
    noise_data_tools = {
        "get_jiangxi_noise_data", "get_jiangxi_noise_statistics", "get_jiangxi_noise_trends",
        "get_jiangxi_noise_events", "get_jiangxi_noise_alarm_analysis",
        "get_jiangxi_noise_compliance", "get_jiangxi_noise_runtime_status",
        "get_jiangxi_noise_directory", "search_jiangxi_noise_apis",
        "describe_jiangxi_noise_api", "call_jiangxi_noise_api",
        "execute_postgres_sql_query", "bash",
    }
    assert report_tools & noise_data_tools == set()


def test_report_system_prompt_injects_project_workflow_contract(monkeypatch):
    """report 声明父策略后，运行时自动注入项目内部工作流契约段。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = build_react_system_prompt("report")

    assert "项目内部工作流" in prompt
    for mode in NOISE_CHILD_MODES:
        assert mode in prompt


def test_expert_node_auto_gets_counter_evidence_schema(monkeypatch):
    """require_counter_evidence 生效：研判节点未显式传 result_schema 时自动注入反证结构。"""
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    node = {"target_mode": "noise_expert_analysis", "goal": "研判南昌夜间超标成因"}
    prepare_node(node)
    finding_properties = node["result_schema"]["properties"]["findings"]["items"]["properties"]
    assert "counter_evidence" in finding_properties
    assert "alternative_explanations" in finding_properties

    # 问数节点不注入反证结构，保持轻量交付
    query_node = {"target_mode": "noise_query_monitoring", "goal": "全省日值统计"}
    prepare_node(query_node)
    assert "result_schema" not in query_node
