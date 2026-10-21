import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.delegation import delegation_error
from app.agent.workflow.protocol import validate_result_schema
from app.agent.workflow.target_mode_contract import target_mode_values
from app.project_config.loader import load_project_context
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool
from config.settings import settings


@pytest.fixture
def jiangsu(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")
    return load_project_context("jiangsu-ops")


def test_internal_roles_have_distinct_tools_and_remain_hidden(jiangsu):
    modes = jiangsu.manifest.backend.agent_workflow_modes
    assert len(modes) == 10
    assert set(modes).isdisjoint(jiangsu.manifest.frontend.agent_modes)
    for mode in modes:
        tools = set(get_tools_by_mode(mode))
        assert not tools & {"run_agent_workflow", "call_sub_agent", "create_report_package", "publish_report",
                            "submit_task_review", "jiangsu_execute_device_control", "jiangsu_prepare_fault_work_order"}
        assert load_project_mode_prompt(mode)
        assert delegation_error(mode, ["assistant"])
    for mode in ("jiangsu_ops_regular_analysis", "jiangsu_ops_risk_analysis"):
        assert not any(name.startswith(("jiangsu_fetch", "execute_jiangsu", "execute_smart_event", "jiangsu_query"))
                       for name in get_tools_by_mode(mode))
    assert "jiangsu_fetch_fault_work_order_detail" in get_tools_by_mode("jiangsu_ops_evidence")


def test_data_modes_are_split_by_domain_tools(jiangsu):
    """数据准备子模式按数据域拆分：域工具只出现在自己的模式里，跨域取数必须另建节点。"""
    data_modes = {mode: set(get_tools_by_mode(mode))
                  for mode in jiangsu.manifest.backend.agent_workflow_modes
                  if mode.startswith("jiangsu_ops_data_")}
    assert set(data_modes) == {
        "jiangsu_ops_data_workorder", "jiangsu_ops_data_alarm", "jiangsu_ops_data_inspection",
        "jiangsu_ops_data_qc", "jiangsu_ops_data_device", "jiangsu_ops_data_station",
        "jiangsu_ops_data_rates"}
    assert "execute_jiangsu_mart_sql" in data_modes["jiangsu_ops_data_workorder"]
    # 2026-10-19: 语义层指标工具是全部数据域的公共取数通道；
    # 统计/率值必须走目录，明细才走受控数据集，避免各节点自造聚合 SQL。
    for mode, tools in data_modes.items():
        assert "jiangsu_query_metrics" in tools, mode
    domain_owners = {
        "execute_smart_event_sql_query": "jiangsu_ops_data_alarm",
        "jiangsu_fetch_qc_task_status": "jiangsu_ops_data_qc",
        "jiangsu_fetch_qc_task_history": "jiangsu_ops_data_qc",
        "jiangsu_fetch_station_environment_history": "jiangsu_ops_data_device",
        "jiangsu_fetch_station_directory": "jiangsu_ops_data_station",
        "jiangsu_fetch_attendance_records": "jiangsu_ops_data_station",
        "jiangsu_analyze_work_order_tracks": "jiangsu_ops_data_station",
        "jiangsu_query_statistics": "jiangsu_ops_data_rates",
    }
    for tool_name, owner in domain_owners.items():
        holders = {mode for mode, tools in data_modes.items() if tool_name in tools}
        assert holders == {owner}, (tool_name, holders)


def test_parent_mode_is_orchestration_and_reporting_only(jiangsu):
    """父模式取数一律委派子 Agent；2026-10-13 起仅放行 execute_python 作分析兜底。"""
    tools = set(get_tools_by_mode("operations_analysis"))
    assert {"run_agent_workflow", "call_sub_agent"} <= tools
    assert not any(
        name.startswith(("jiangsu_fetch", "execute_jiangsu", "execute_smart_event", "jiangsu_query",
                         "jiangsu_analyze", "create_business_chart", "knowledge_graph"))
        for name in tools
    )
    assert "execute_python" in tools


def test_schema_refreshes_when_project_changes(jiangsu, monkeypatch):
    tool = RunAgentWorkflowTool()
    modes = set(jiangsu.manifest.backend.agent_workflow_modes)
    schema = tool.get_function_schema()
    enum = schema["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]["enum"]
    assert modes <= set(enum)
    monkeypatch.setattr(settings, "project_id", "default")
    assert modes.isdisjoint(target_mode_values())
    enum = tool.get_function_schema()["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]["enum"]
    assert modes.isdisjoint(enum)


def test_parent_function_schema_exposes_only_its_internal_roles(jiangsu, monkeypatch):
    from app.agent.tool_adapter import get_tool_schemas
    from app.tools import create_global_tool_registry

    monkeypatch.setattr("app.agent.tool_adapter.global_tool_registry", create_global_tool_registry(context=jiangsu))

    schemas = get_tool_schemas(mode="operations_analysis")
    schema = next(schema for schema in schemas if schema["name"] == "run_agent_workflow")
    target = schema["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]
    assert set(target["enum"]) == set(jiangsu.manifest.backend.agent_workflow_modes)
    assert "query_monitoring_station" not in schema["description"]


def task(task_id, mode, dependencies=()):
    return {"task_id": task_id, "target_mode": mode, "goal": task_id,
            "dependencies": list(dependencies), "task_contract": {
                "protocol_version": "workflow.v1", "task_type": "expert_analysis", "question": task_id,
                "scope": {"time_range": {"start": "2026-09-01", "end": "2026-09-30"},
                          "objects": ["省控站点"], "metric_definitions": "Fault工单，无超期率"},
                "required_evidence": ["共享工单记录"], "deliverables": ["结论和证据"],
            }}


@pytest.mark.asyncio
async def test_real_dag_parallel_analysis_and_extension_reuse_sources(jiangsu, monkeypatch, tmp_path):
    calls = []
    snapshots = {}
    reached = set()
    both = asyncio.Event()
    source = tmp_path / "orders.csv"
    source.write_text("station,failures\na,2\n")

    class Child:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            goal = kwargs["goal"]
            if goal in {"coverage", "risk"}:
                reached.add(goal)
                if len(reached) == 2:
                    both.set()
                await asyncio.wait_for(both.wait(), 2)
                assert any(handle.get("file_path") == str(source) for handle in kwargs["_upstream_handles"])
            assert kwargs["result_schema"]["x-evidence-references"]
            assert kwargs["task_contract"]["result_schema"] == kwargs["result_schema"]
            result = {"status": "completed", "findings": [{"statement": goal, "evidence_ids": ["e1"], "counter_evidence": [], "alternative_explanations": []}],
                      "evidence": [{"id": "e1", "source": "共享工单记录", "locator": str(source)}],
                      "uncertainties": [], "data_gaps": []}
            assert validate_result_schema(result, kwargs["result_schema"]) == []
            return {"status": "success", "success": True, "result": goal,
                    "data": {"structured_result": result, "result_envelope": result, "file_paths": [str(source)]}}

    class Registry:
        async def register(self, *args, **kwargs):
            pass

        async def unregister(self, *args):
            pass

    from app.agent.workflow import journal
    journal_class = journal.WorkflowJournal
    monkeypatch.setattr(journal, "WorkflowJournal", lambda: journal_class(tmp_path / "journal.db"))
    monkeypatch.setattr("app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(RunAgentWorkflowTool, "_build_sub_agent_tool", staticmethod(Child))
    monkeypatch.setattr(RunAgentWorkflowTool, "_build_workflow_registry", staticmethod(Registry))
    monkeypatch.setattr(RunAgentWorkflowTool, "_write_full_results", staticmethod(lambda *args: None))
    monkeypatch.setattr(RunAgentWorkflowTool, "_persist_parent_snapshot",
                        staticmethod(lambda context, snapshot: snapshots.update({snapshot["workflow_id"]: deepcopy(snapshot)})))

    async def load(context, workflow_id):
        return snapshots.get(workflow_id)

    monkeypatch.setattr(RunAgentWorkflowTool, "_load_parent_snapshot", staticmethod(load))
    context = SimpleNamespace(runtime_mode="operations_analysis", session_id="isolated-dag-test")
    workflow = {"workflow_id": "monthly", "nodes": [task("data", "jiangsu_ops_data_workorder"),
                task("coverage", "jiangsu_ops_regular_analysis", ["data"]),
                task("risk", "jiangsu_ops_risk_analysis", ["data"])]}
    # Worker checkpoints may wrap payloads. A caller's loose nested schema
    # must not shadow the enforced project result contract.
    data_node = workflow["nodes"][0]
    workflow["nodes"][0] = {"task_id": "data", "payload": {
        **{key: value for key, value in data_node.items() if key != "task_id"},
        "result_schema": {"type": "object"},
    }}
    result = await RunAgentWorkflowTool().execute(context=context, workflow=workflow, max_concurrency=8)
    assert result["success"], result
    assert reached == {"coverage", "risk"}
    assert snapshots["monthly"]["max_concurrency"] == 3
    assert snapshots["monthly"]["definition"]["budget"]["max_nodes"] == 16
    extension = {"expected_revision": result["data"]["revision"], "reason": "核验具体工单冲突",
                 "nodes": [task("verify", "jiangsu_ops_evidence", ["risk"])]}
    extended = await RunAgentWorkflowTool().execute(context=context, workflow={"workflow_id": "monthly"}, extension=extension)
    assert extended["success"], extended
    assert [call["goal"] for call in calls].count("data") == 1
    assert [call["goal"] for call in calls].count("coverage") == 1
    assert [call["goal"] for call in calls].count("risk") == 1
    assert calls[-1]["goal"] == "verify"


@pytest.mark.asyncio
async def test_missing_contract_and_out_of_scope_delegation_fail_before_children(jiangsu):
    value = task("risk", "jiangsu_ops_risk_analysis")
    value.pop("task_contract")
    tool = RunAgentWorkflowTool()
    result = await tool.execute(context=SimpleNamespace(runtime_mode="operations_analysis"), workflow={"nodes": [value]})
    assert not result["success"]
    assert "task_contract" in result["summary"]
    result = await tool.execute(context=SimpleNamespace(runtime_mode="assistant"),
                                workflow={"nodes": [task("risk", "jiangsu_ops_risk_analysis")]})
    assert not result["success"]


def test_all_internal_tools_are_registered(jiangsu):
    from app.tools import create_global_tool_registry

    registry = set(create_global_tool_registry(context=jiangsu).list_tools())
    for mode in jiangsu.manifest.backend.agent_workflow_modes:
        missing = set(get_tools_by_mode(mode)) - registry
        assert not missing, (mode, missing)


def test_risk_results_require_counter_evidence_and_alternatives(jiangsu):
    from app.agent.workflow.project_policy import prepare_node

    value = task("risk", "jiangsu_ops_risk_analysis")
    prepare_node(value)
    result = {"status": "completed", "findings": [{"statement": "需要核验", "evidence_ids": ["e1"]}],
              "evidence": [{"id": "e1", "source": "records", "locator": "row 1"}],
              "uncertainties": [], "data_gaps": []}
    errors = validate_result_schema(result, value["result_schema"])
    assert {error["path"] for error in errors} == {
        "$.findings[0].counter_evidence", "$.findings[0].alternative_explanations"}
    result["findings"][0].update(counter_evidence=[], alternative_explanations=["通信中断仍需核验"])
    assert validate_result_schema(result, value["result_schema"]) == []
