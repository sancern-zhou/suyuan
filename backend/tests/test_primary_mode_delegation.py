import pytest
from types import SimpleNamespace

from app.agent.workflow.delegation import delegation_error
from app.agent.workflow.target_mode_contract import target_mode_values, build_target_mode_contract
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode


@pytest.mark.parametrize("parent", ["assistant", "social", "report", "query", "expert", "ops"])
@pytest.mark.parametrize("target", ["query", "expert", "report"])
def test_primary_modes_rejected_for_every_parent(parent, target):
    assert delegation_error(parent, [target])
    assert target not in target_mode_values()
    assert f"- {target}：" not in build_target_mode_contract()


def test_specific_children_remain_available():
    children = ["query_monitoring_station", "query_monitoring_city", "query_forecast", "expert_meteorology", "expert_analysis"]
    assert set(children).issubset(target_mode_values())
    assert delegation_error("assistant", children) is None
    assert delegation_error("report", children) is None


def test_assistant_supports_tasks_office_and_technical_answers():
    tools = get_tools_by_mode("assistant")
    assert {"manage_scheduled_tasks", "create_scheduled_task", "create_report_package", "execute_python"}.issubset(tools)
    prompt = build_react_system_prompt("assistant")
    assert 'target_mode="report"' not in prompt
    assert 'target_mode="query"' not in prompt
    assert 'target_mode="expert"' not in prompt
    assert 'target_mode="chart"' not in prompt
    assert "技术问题时，允许" in prompt


def test_tool_schemas_only_expose_child_roles():
    from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    direct = CallSubAgentTool().get_function_schema()["parameters"]["properties"]["target_mode"]["enum"]
    dag = RunAgentWorkflowTool().get_function_schema()["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]["enum"]
    assert {"query", "expert", "report"}.isdisjoint(direct)
    assert direct == dag


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["query", "expert", "report"])
async def test_direct_and_dag_calls_cannot_bypass_schema(target):
    from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
    context = SimpleNamespace(runtime_mode="assistant", session_id="boundary-test")
    result = await CallSubAgentTool().execute(context=context, target_mode=target, goal="处理任务")
    assert not result["success"] and "不允许作为子 Agent" in result["summary"]
    result = await RunAgentWorkflowTool().execute(context=context, workflow={
        "workflow_id": "blocked", "nodes": [{"task_id": "blocked", "target_mode": target, "goal": "处理任务"}],
    })
    assert not result["success"] and "不允许作为子 Agent" in result["summary"]
