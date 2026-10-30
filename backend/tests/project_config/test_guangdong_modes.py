"""Guangdong agent-modes rollout: manifest, whitelists, prompts, workflow contract."""

import pytest

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.project_config.loader import load_project_context
from config.settings import settings


@pytest.fixture(autouse=True)
def _guangdong_project(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "guangdong")


def _guangdong_context():
    return load_project_context("guangdong")


def test_guangdong_manifest_declares_rollout_modes():
    manifest = _guangdong_context().manifest
    frontend_modes = set(manifest.frontend.agent_modes)
    assert {"gd_query", "knowledge", "station_fault_diagnosis", "operations_analysis"} <= frontend_modes
    children = set(manifest.backend.agent_workflow_modes)
    assert len(children) == 9
    # workflow 子模式不得出现在前台模式
    assert children.isdisjoint(frontend_modes)
    parent = manifest.backend.agent_workflow_parents["operations_analysis"]
    assert set(parent.child_modes) == children
    assert parent.max_concurrency == 3
    assert parent.max_nodes == 12
    # 节点预算放宽后（数据 20 轮/风险 24 轮），父级 DAG 截止时间同步放宽。
    assert parent.timeout_seconds == 1800


def test_guangdong_mode_prompt_files_exist():
    manifest = _guangdong_context().manifest
    for mode in manifest.backend.mode_prompt_files:
        prompt = load_project_mode_prompt(mode, context=_guangdong_context())
        assert prompt, f"empty prompt for {mode}"


def test_guangdong_frontend_modes_have_overrides():
    overrides = _guangdong_context().manifest.frontend.agent_mode_overrides
    for mode in ("gd_query", "ops", "knowledge", "station_fault_diagnosis", "operations_analysis"):
        override = overrides[mode]
        assert override.get("name"), mode
        assert override.get("welcome", {}).get("features"), mode


def test_gd_query_whitelist_is_semantic_layer_first():
    tools = get_tools_by_mode("gd_query")
    # 语义层与受控 SQL
    assert "guangdong_query_metrics" in tools
    assert "execute_guangdong_mart_sql" in tools
    # 站点目录解析
    assert "guangdong_station_catalog" in tools
    # 站点监测数据接口
    assert "query_gd_suncere_city_hour" in tools
    assert "query_station_standard_report" in tools
    # 图表与会话文件
    assert "create_business_chart" in tools
    assert "publish_session_file" in tools
    assert "ask_user_question" in tools
    # 问数模式不暴露知识图谱与委派
    assert "knowledge_graph_query" not in tools
    assert "run_agent_workflow" not in tools
    assert "call_sub_agent" not in tools
    # 江苏专属工具不得泄漏进广东模式
    assert "publish_report" not in tools
    assert "execute_jiangsu_mart_sql" not in tools


def test_station_fault_diagnosis_whitelist_is_graph_and_evidence_focused():
    tools = get_tools_by_mode("station_fault_diagnosis")
    assert "knowledge_graph_query" in tools
    assert "knowledge_graph_build" in tools
    assert "execute_guangdong_mart_sql" in tools
    assert "guangdong_station_catalog" in tools
    assert "ask_user_question" in tools
    assert "run_agent_workflow" not in tools


def test_operations_analysis_parent_delegates_and_children_cannot():
    manifest = _guangdong_context().manifest
    parent_tools = get_tools_by_mode("operations_analysis")
    assert "run_agent_workflow" in parent_tools
    assert "call_sub_agent" in parent_tools
    # 父模式是编排角色，不持有取数工具
    assert "execute_guangdong_mart_sql" not in parent_tools
    assert "guangdong_query_metrics" not in parent_tools

    delegation = {"run_agent_workflow", "call_sub_agent"}
    for child in manifest.backend.agent_workflow_modes:
        child_tools = get_tools_by_mode(child)
        assert child_tools, child
        assert delegation.isdisjoint(child_tools), child


def test_workflow_child_tool_surfaces_are_domain_scoped():
    tools_by_child = {
        child: set(get_tools_by_mode(child))
        for child in _guangdong_context().manifest.backend.agent_workflow_modes
    }
    data_children = [name for name in tools_by_child if name.startswith("gd_ops_data_")]
    for child in data_children:
        assert "execute_guangdong_mart_sql" in tools_by_child[child], child
        assert "create_business_chart" not in tools_by_child[child], child
    # 站点数据节点持站点目录解析工具，其他数据节点不持有
    assert "guangdong_station_catalog" in tools_by_child["gd_ops_data_station"]
    for child in data_children:
        if child != "gd_ops_data_station":
            assert "guangdong_station_catalog" not in tools_by_child[child], child
    for analysis_child in ("gd_ops_regular_analysis", "gd_ops_risk_analysis"):
        # 分析节点只消费共享数据，不持有取数工具
        assert "execute_guangdong_mart_sql" not in tools_by_child[analysis_child]
        assert "create_business_chart" in tools_by_child[analysis_child]


def test_gd_query_prompt_inherits_registry_caveats():
    prompt = build_react_system_prompt("gd_query")
    # 语言规范与关键口径红线进入系统提示词
    assert "不得出现" in prompt
    assert "未处理率" in prompt
    assert "推送范围" in prompt
    assert "不重算" in prompt


def test_operations_analysis_prompt_declares_budget_and_children():
    prompt = build_react_system_prompt("operations_analysis")
    for child in _guangdong_context().manifest.backend.agent_workflow_parents[
        "operations_analysis"
    ].child_modes:
        assert child in prompt
    assert "并发最多 3" in prompt
    assert "累计节点 12" in prompt


def test_guangdong_report_mode_is_integrator_focused():
    manifest = _guangdong_context().manifest
    # 2026-10-30 对标许昌：report 走全量接管白名单，不再用 extras 追加直查工具
    assert "report" in manifest.backend.agent_mode_tools
    assert "report" not in manifest.backend.agent_mode_extra_tools
    tools = get_tools_by_mode("report")
    # 整合者工具面：资源、文件、图表、排名核算、收口与 DAG 委托
    assert {
        "list_session_resources",
        "read_session_resource",
        "publish_session_file",
        "read_file",
        "write_file",
        "edit_file",
        "create_business_chart",
        "execute_python",
        "analyze_city_pollutant_rankings",
        "create_report_package",
        "run_agent_workflow",
        "list_skills",
        "view_skill",
        "ask_user_question",
    }.issubset(tools)
    # 主 Agent 不直接执行业务数据查询
    assert {
        "get_5min_data",
        "query_gd_suncere_city_hour",
        "query_gd_suncere_city_day",
        "query_gd_suncere_district_day",
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_gd_suncere_district_report",
        "query_station_standard_report",
        "query_station_standard_yoy_report",
        "station_operation_daily",
        "execute_sql_query",
        "query_xcai_city_history",
    }.isdisjoint(tools)
    # 编排者不持有源码检索与重型执行工具（对标许昌守卫）
    assert {"bash", "grep", "list_directory", "search_files", "execute_echarts_python"}.isdisjoint(tools)
    assert "call_sub_agent" not in tools
    assert "render_report_package" not in tools
    assert "validate_report_package" not in tools


def test_guangdong_report_prompt_is_project_override():
    manifest = _guangdong_context().manifest
    assert manifest.backend.mode_prompt_files.get("report") == (
        "projects/guangdong/prompts/report.md"
    )
    prompt = build_react_system_prompt("report")
    # 整合者定位与 DAG 委托
    assert "报告整合者" in prompt
    assert "不直接执行业务数据查询" in prompt
    assert "run_agent_workflow" in prompt
    # 七类叶子模式全部声明，综合兜底禁止
    for mode in (
        "query_monitoring_station",
        "query_monitoring_city",
        "query_forecast",
        "query_component",
        "expert_meteorology",
        "expert_analysis",
        "expert_component",
    ):
        assert mode in prompt
    assert "query_monitoring）兜底" in prompt
    # 广东口径：区域展开、报表包字段、排名工具、完成标记
    assert "珠三角" in prompt
    assert "pM2_5_Decimal" in prompt
    assert "analyze_city_pollutant_rankings" in prompt
    assert "<!-- report_final_complete -->" in prompt
    # 直查时代的计划模板流程随白名单一并下线
    assert "backend_data_registry" not in prompt
    assert "计划模板" not in prompt


def test_report_pipeline_data_tools_reach_query_leaf_nodes():
    # 原报告主模式直查的报表包/5分钟工具必须能在问数叶子节点使用：
    # 模式白名单（extras）与固定流程阶段表（mode_workflows）成对配置
    city_tools = set(get_tools_by_mode("query_monitoring_city"))
    station_tools = set(get_tools_by_mode("query_monitoring_station"))
    for name in (
        "query_gd_suncere_city_hour",
        "query_gd_suncere_city_day",
        "query_gd_suncere_district_day",
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_gd_suncere_district_report",
    ):
        assert name in city_tools, name
    for name in (
        "query_station_standard_report",
        "query_station_standard_yoy_report",
        "get_5min_data",
    ):
        assert name in station_tools, name

    from app.agent.workflow.mode_workflows import get_mode_workflow

    city_phase = get_mode_workflow("query_monitoring_city").phases[0]
    station_phase = get_mode_workflow("query_monitoring_station").phases[0]
    assert set(city_phase.allowed_tools).issuperset({
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_gd_suncere_district_report",
    })
    assert set(station_phase.allowed_tools).issuperset({
        "query_station_standard_report",
        "query_station_standard_yoy_report",
        "get_5min_data",
    })


def test_ops_mode_is_audit_focused_with_lean_whitelist():
    manifest = _guangdong_context().manifest
    # ops 对标江苏改为审核专用全量白名单，不走共享基线叠加
    assert "ops" in manifest.backend.agent_mode_tools
    assert "ops" not in manifest.backend.agent_mode_extra_tools
    tools = get_tools_by_mode("ops")
    # 审核链路与语义层口径核对
    assert "ops_audit_fetch_dataset" in tools
    assert "ops_audit_run_rules" in tools
    assert "execute_guangdong_mart_sql" in tools
    assert "guangdong_query_metrics" in tools
    assert "guangdong_station_catalog" in tools
    assert "execute_ops_sql_query" in tools
    # 工具面收敛：共享运维基线中的分析/画板/PPT 类工具不再进入
    assert "create_drawio_board" not in tools
    assert "generate_map" not in tools
    assert "create_pptx_with_ppt_master" not in tools
    assert "web_search" not in tools
    prompt = build_react_system_prompt("ops")
    # 审核定位与保留的绩效/巡检对照口径
    assert "运维工单审核" in prompt
    assert "例行工单审核" in prompt
    assert "故障工单人工复核" in prompt
    assert "平台考核口径原值" in prompt
    assert "转工单率分母" in prompt
