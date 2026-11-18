"""江西 deferred tools 项目声明守门：query/expert opt-in，DAG 子模式不 opt-in。

2026-11-18 上下文优化：query/expert 两个综合模式白名单含全部 8 个
get_jiangxi_noise_* 域工具（schema 合计 ~23K 字符），经
backend.agent_mode_deferred_tools 声明存根化后每轮常驻省 ~21K 字符。
本测试锁定三件事：
1. 声明范围——只有 query/expert；三个报告 DAG 子模式是委派热路径
   （胖 schema 即身份工具），误声明会让每个 DAG 节点多付 tool_search 往返；
2. always_on 边界——只留分析与交付管道，域工具必须进存根候选；
3. 真实 opt-in 下的常驻预算——存根化显著缩量且单存根不超限。
"""
import json
from pathlib import Path
from types import SimpleNamespace

from app.agent.prompts import tool_registry
from app.agent.prompts.tool_registry import (
    DEFERRED_NEVER_STUB_TOOL_NAMES,
    compute_deferred_tool_names,
    get_tools_by_mode,
    resolve_deferred_tool_config,
)
from app.agent.tool_adapter import (
    DEFERRED_STUB_SCHEMA_CHAR_FLOOR,
    apply_deferred_tool_stubs,
    get_tool_schemas,
)
from app.project_config.loader import load_project_context

REPO_ROOT = Path(__file__).resolve().parents[3]

DOMAIN_TOOLS = frozenset(
    {
        "get_jiangxi_noise_data",
        "get_jiangxi_noise_statistics",
        "get_jiangxi_noise_trends",
        "get_jiangxi_noise_events",
        "get_jiangxi_noise_runtime_status",
        "get_jiangxi_noise_directory",
        "get_jiangxi_noise_alarm_analysis",
        "get_jiangxi_noise_compliance",
    }
)
# 分析与交付管道：几乎每轮必用、多轮复用，存根会让模型多付检索往返
PLUMBING_TOOLS = frozenset(
    {
        "execute_python",
        "execute_postgres_sql_query",
        "execute_echarts_python",
        "read_file",
        "grep",
        "edit_file",
        "list_session_resources",
    }
)
DAG_SUBMODES = ("noise_query_monitoring", "noise_query_evaluation", "noise_expert_analysis")


def _jiangxi_context():
    return load_project_context("jiangxi", repo_root=REPO_ROOT)


def _isolate_jiangxi_declaration(monkeypatch) -> None:
    """让 tool_registry 的运行时解析看到江西清单（与 PROJECT 环境变量解耦）。"""
    monkeypatch.setattr(tool_registry, "_load_project_context", _jiangxi_context)


def test_manifest_declares_query_and_expert_only():
    declared = _jiangxi_context().manifest.backend.agent_mode_deferred_tools
    assert set(declared.keys()) == {"query", "expert"}, (
        "deferred 声明范围变化需同步评估报告 DAG 子模式的委派往返成本"
    )
    for mode in ("query", "expert"):
        assert set(declared[mode]) == PLUMBING_TOOLS


def test_dag_submodes_are_not_opted_in():
    declared = _jiangxi_context().manifest.backend.agent_mode_deferred_tools
    for mode in DAG_SUBMODES:
        assert mode not in declared, (
            f"{mode} 是 report DAG 委派热路径，存根化会让每个节点多付 tool_search 往返"
        )


def test_resolver_and_candidate_set(monkeypatch):
    _isolate_jiangxi_declaration(monkeypatch)
    for mode in ("query", "expert"):
        config = resolve_deferred_tool_config(mode)
        assert config is not None, mode
        assert config.always_on == PLUMBING_TOOLS

        deferred = compute_deferred_tool_names(mode, config)
        mode_names = set(get_tools_by_mode(mode).keys())
        assert DOMAIN_TOOLS <= mode_names, "域工具白名单变化需同步本测试"
        assert DOMAIN_TOOLS <= deferred, "域工具必须进存根候选（上下文大头）"
        assert not (deferred & PLUMBING_TOOLS)
        assert not (deferred & DEFERRED_NEVER_STUB_TOOL_NAMES)
        assert deferred <= mode_names


def test_stub_application_budget(monkeypatch):
    _isolate_jiangxi_declaration(monkeypatch)
    for mode in ("query", "expert"):
        config = resolve_deferred_tool_config(mode)
        deferred = compute_deferred_tool_names(mode, config)
        schemas = get_tool_schemas(mode=mode)
        full_total = sum(len(json.dumps(s, ensure_ascii=False)) for s in schemas)

        resident, stubbed, _saved = apply_deferred_tool_stubs(
            schemas, deferred_names=deferred
        )
        resident_total = sum(len(json.dumps(s, ensure_ascii=False)) for s in resident)

        # 存根化只发生在 >600 字符工具上（三件套等小工具自动豁免，保持全 schema）
        stubbed_names = {
            s.get("name")
            for s in resident
            if s.get("parameters", {}).get("properties") == {}
        }
        assert "list_directory" in stubbed_names
        assert not (stubbed_names & PLUMBING_TOOLS)
        assert stubbed == len(stubbed_names) > 0

        # 常驻显著缩量（8 域工具 schema 合计 ~23K 字符，是本次优化的收益来源）
        assert resident_total < full_total * 0.65, (
            f"{mode} 常驻 {resident_total} 未显著低于全量 {full_total}，"
            "域工具可能未存根化或白名单结构变化"
        )


def test_small_catalog_tools_exempt_from_stubbing(monkeypatch):
    """三件套 ≤600 字符自动豁免：目录入口保持全 schema，不付检索往返。"""
    _isolate_jiangxi_declaration(monkeypatch)
    config = resolve_deferred_tool_config("query")
    deferred = compute_deferred_tool_names("query", config)
    schemas = {s["name"]: s for s in get_tool_schemas(mode="query")}
    resident, _stubbed, _saved = apply_deferred_tool_stubs(
        list(schemas.values()), deferred_names=deferred
    )
    by_name = {s["name"]: s for s in resident}
    for name in ("search_jiangxi_noise_apis", "describe_jiangxi_noise_api", "call_jiangxi_noise_api"):
        assert name in deferred  # 在候选集里
        assert len(json.dumps(by_name[name], ensure_ascii=False)) <= DEFERRED_STUB_SCHEMA_CHAR_FLOOR  # 但全 schema 常驻
