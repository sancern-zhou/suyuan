"""Query/expert parents share DAG capability while specialist children stay bounded."""

from types import SimpleNamespace
import pytest

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.capabilities import build_child_capability_policy
from app.agent.workflow.delegation import LEAF_MODES, build_delegation_contract, delegation_error
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool


@pytest.fixture(autouse=True)
def isolated_workflows(monkeypatch, tmp_path):
    from app.agent.workflow.registry import ActiveWorkflowRegistry
    monkeypatch.setattr(RunAgentWorkflowTool, "_build_workflow_registry", staticmethod(ActiveWorkflowRegistry))
    monkeypatch.setattr("app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr("app.agent.workflow.journal.get_data_registry", lambda: tmp_path)


def test_parent_tools_and_project_prompt_receive_delegation_guidance(monkeypatch):
    monkeypatch.setattr("app.agent.prompts.tool_registry._get_project_tool_names_by_mode", lambda mode: None)
    monkeypatch.setattr("app.agent.prompts.tool_registry._get_project_disabled_tool_names", lambda: [])
    monkeypatch.setattr("app.agent.prompts.prompt_builder.load_project_mode_prompt", lambda mode: "项目职责边界")
    # 【2026-10-30】query/expert 父模式委派收敛为 call_sub_agent，run_agent_workflow 下线。
    for mode in ("query", "expert"):
        tools = get_tools_by_mode(mode)
        assert "run_agent_workflow" not in tools
        assert "call_sub_agent" in tools
        prompt = build_react_system_prompt(mode, available_tools=list(tools))
        assert "项目职责边界" in prompt
        assert "精简子 Agent 委派" in prompt
        assert "query_monitoring_station" in prompt
        assert "能一次批量取数时优先批量查询" in prompt
        assert "run_agent_workflow" not in prompt
        assert "DAG 会增加模型调用" not in prompt
    assert "expert_meteorology" in build_react_system_prompt("expert")
    # Data-source catalogs can mention expert routing; only the delegation contract
    # determines which child types the query parent is authorized to call.
    assert "expert_meteorology" not in build_delegation_contract("query", ["run_agent_workflow"])
    # 仅保留 call_sub_agent 的父模式：契约不引导 run_agent_workflow / DAG 概念。
    call_only_contract = build_delegation_contract("query", ["call_sub_agent"])
    assert "run_agent_workflow" not in call_only_contract
    assert "call_sub_agent 委派子 Agent" in call_only_contract
    assert "精简子 Agent 与依赖工作流" not in build_react_system_prompt("query", available_tools=["execute_python"])


def test_leaf_registries_strip_both_delegation_tools():
    for mode in LEAF_MODES:
        assert not {"run_agent_workflow", "call_sub_agent"}.intersection(get_tools_by_mode(mode))
    restricted = build_child_capability_policy(allow_delegation=False).filter_registry(
        {"run_agent_workflow": object(), "call_sub_agent": object(), "execute_python": object()},
    )
    assert set(restricted) == {"execute_python"}
    assert delegation_error("query", ["query_forecast"]) is None
    assert delegation_error("query", ["expert_analysis"])
    assert delegation_error("expert", ["expert_analysis"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,target", [
    ("query", "expert_analysis"), ("query", "report"),
    ("expert", "expert"), ("expert_analysis", "query_forecast"),
])
async def test_direct_and_dag_calls_reject_scope_escape(mode, target):
    context = SimpleNamespace(runtime_mode=mode)
    direct = await CallSubAgentTool().execute(context=context, target_mode=target, goal="test")
    assert direct["success"] is False
    dag = await RunAgentWorkflowTool().execute(context=context, workflow={
        "nodes": [{"task_id": "n", "target_mode": target, "goal": "test",
                   "task_contract": {"deliverables": ["结果"]}}],
    })
    assert dag["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,target", [
    ("query", "query_monitoring_station"), ("query", "query_monitoring_city"),
    ("query", "query_forecast"), ("expert", "expert_analysis"), ("expert", "expert_meteorology"),
])
async def test_parent_dag_dispatches_narrow_child_with_its_mode(mode, target, monkeypatch, tmp_path):
    monkeypatch.setattr("app.agent.workflow.result_cache._cache_root", lambda: tmp_path)
    calls = []
    class Child:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {"success": True, "status": "success", "data": {}}
    monkeypatch.setattr(RunAgentWorkflowTool, "_build_sub_agent_tool", staticmethod(Child))
    result = await RunAgentWorkflowTool().execute(
        context=SimpleNamespace(runtime_mode=mode),
        workflow={"nodes": [{"task_id": "n", "target_mode": target, "goal": "test",
                             "task_contract": {"deliverables": ["结果"]}}]},
    )
    assert result["success"] is True
    assert calls[0]["target_mode"] == target
    assert calls[0]["context"].runtime_mode == mode
