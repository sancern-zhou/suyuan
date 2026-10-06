import asyncio
from types import SimpleNamespace

import pytest

from app.agent.session import session_resolver
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool


@pytest.fixture(autouse=True)
def _isolated_workflow_cache(tmp_path, monkeypatch):
    """节点成果缓存指向临时目录：测试不读写真实 registry 缓存。"""
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root",
        lambda: tmp_path / "workflow_cache",
    )


def test_run_agent_workflow_schema_documents_free_form_dag():
    schema = RunAgentWorkflowTool().get_function_schema()
    description = schema["description"]
    properties = schema["parameters"]["properties"]

    for token in (
        "自主决定",
        "nodes",
        "dependencies",
        "task_contract",
        "result_schema",
        "expert_meteorology",
        "expert_analysis",
    ):
        assert token in description

    assert "workflow" in properties
    node_properties = properties["workflow"]["properties"]["nodes"]["items"]["properties"]
    assert node_properties["max_iterations"]["maximum"] == 120
    assert node_properties["timeout_seconds"]["minimum"] == 30
    assert "workflow_template" not in properties
    assert "template_options" not in properties
    assert schema["parameters"]["required"] == ["workflow"]
    node_schema = properties["workflow"]["properties"]["nodes"]["items"]["properties"]
    assert {"query", "expert", "report"}.issubset(set(node_schema["target_mode"]["enum"]))
    call_target_mode = CallSubAgentTool().get_function_schema()["parameters"]["properties"]["target_mode"]
    assert call_target_mode["enum"] == node_schema["target_mode"]["enum"]


def test_run_agent_workflow_schema_documents_target_mode_contract():
    schema = RunAgentWorkflowTool().get_function_schema()
    description = schema["description"]
    target_mode = schema["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]

    assert "能力与工具边界" in description
    assert "同源数据由一个节点获取，后续节点通过 dependencies 复用" in description
    assert {"query", "expert", "report"}.issubset(set(target_mode["enum"]))
    call_target_mode = CallSubAgentTool().get_function_schema()["parameters"]["properties"]["target_mode"]
    assert call_target_mode["enum"] == target_mode["enum"]


def test_run_agent_workflow_schema_requires_one_question_per_expert_node():
    schema = RunAgentWorkflowTool().get_function_schema()
    description = schema["description"]
    assert "一个专家节点只能回答一个分析问题" in description
    assert "deliverables 最多 3 项" in description


@pytest.mark.asyncio
async def test_run_agent_workflow_rejects_overloaded_expert_node():
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "overloaded-expert",
            "nodes": [{
                "task_id": "analysis-all",
                "target_mode": "expert_analysis",
                "goal": "完成所有分析",
                "task_contract": {
                    "deliverables": ["相关性", "超标统计", "时空对比", "趋势图"],
                },
            }],
        },
    )
    assert result["success"] is False
    assert "超过专家节点上限" in result["result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("node,expect", [
    (
        {"task_id": "met-all", "target_mode": "expert_meteorology", "goal": "气象集中研判"},
        "缺少 task_contract",
    ),
    (
        {"task_id": "analysis-all", "target_mode": "expert_analysis", "goal": "集中研判",
         "task_contract": {"protocol_version": "workflow.v1", "question": "成因"}},
        "缺少 deliverables",
    ),
    (
        {"task_id": "analysis-empty", "target_mode": "expert_analysis", "goal": "集中研判",
         "task_contract": {"protocol_version": "workflow.v1", "question": "成因", "deliverables": []}},
        "为空",
    ),
])
async def test_report_expert_node_requires_contract_with_deliverables(node, expect):
    """专家节点必须携带 task_contract.deliverables（1~3 项），缺失即整单拒绝。"""
    result = await RunAgentWorkflowTool().execute(
        workflow={"workflow_id": "granularity", "nodes": [node]},
    )
    assert result["success"] is False
    assert expect in result["result"]
    assert "拆" in result["result"]


def test_call_sub_agent_extracts_current_tool_result_file_handles():
    events = [{
        "type": "tool_result",
        "data": {
            "file_path": "backend/backend_data_registry/source.json",
            "report_file_paths": ["backend/backend_data_registry/report.json"],
            "result": {
                "data_file_paths": ["backend/backend_data_registry/calculated.json"],
                "resources": [{
                    "locator": {"path": "backend/backend_data_registry/chart.png"}
                }],
            },
        },
    }]

    assert CallSubAgentTool()._extract_file_paths(events) == [
        "backend/backend_data_registry/source.json",
        "backend/backend_data_registry/report.json",
        "backend/backend_data_registry/calculated.json",
        "backend/backend_data_registry/chart.png",
    ]


@pytest.mark.asyncio
async def test_run_agent_workflow_passes_upstream_file_handles_to_dependent_nodes(monkeypatch):
    calls = []

    class FakeSubAgentTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            data = {}
            if "查询" in kwargs["goal"]:
                data["file_paths"] = [f"backend/data/{kwargs['goal']}.json"]
            return {
                "status": "success",
                "success": True,
                "result": kwargs["goal"],
                "data": {
                    **data,
                    "result_envelope": {
                        "status": "completed",
                        "summary": "已完成空气质量查询",
                        "evidence": [{"ref_id": "air-1", "kind": "table"}],
                        "uncertainties": [],
                        "data_gaps": [],
                    },
                },
            }

    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: FakeSubAgentTool()),
    )
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "handles-1",
            "nodes": [
                {"task_id": "air", "target_mode": "query", "goal": "查询空气质量"},
                {
                    "task_id": "merge",
                    "target_mode": "expert",
                    "goal": "交叉分析",
                    "dependencies": ["air"],
                },
            ],
        },
    )

    assert result["success"] is True
    merge_call = next(call for call in calls if call["goal"] == "交叉分析")
    context = merge_call["context_str"]
    assert "## 上游节点结论摘要" in context
    assert "已完成空气质量查询" in context
    assert "backend/data/查询空气质量.json" not in context
    assert "tool_calls" not in context
    assert "不要根据摘要重新查询同一数据源" in context
    assert merge_call["_upstream_handles"][0]["handle_type"] == "file_path"


@pytest.mark.asyncio
async def test_run_agent_workflow_dispatches_parallel_nodes_and_injects_dependencies(monkeypatch):
    calls = []

    class FakeSubAgentTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {
                "status": "success",
                "success": True,
                "result": kwargs["goal"],
                "data": {"goal": kwargs["goal"]},
            }

    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: FakeSubAgentTool()),
    )
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "report-1",
            "nodes": [
                {"task_id": "air", "target_mode": "expert", "goal": "分析空气质量"},
                {"task_id": "weather", "target_mode": "expert", "goal": "分析气象条件"},
                {
                    "task_id": "merge",
                    "target_mode": "expert",
                    "goal": "交叉分析",
                    "dependencies": ["air", "weather"],
                },
            ],
        },
        max_concurrency=2,
    )

    assert result["success"] is True
    assert result["data"]["status"] == "succeeded"
    merge_call = next(call for call in calls if call["goal"] == "交叉分析")
    assert "分析空气质量" not in merge_call["context_str"]
    assert "分析气象条件" not in merge_call["context_str"]
    assert all(call["_force_isolated_session"] is True for call in calls)
    assert all(call["max_iterations"] == 30 for call in calls)
    assert all(
        node["timeout_seconds"] == 480
        for node in result["data"]["node_results"].values()
    )


@pytest.mark.asyncio
async def test_run_agent_workflow_applies_domain_expert_limits(monkeypatch):
    calls = []

    class FakeSubAgentTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {"status": "success", "success": True, "result": "ok", "data": {}}

    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: FakeSubAgentTool()),
    )
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "specialist-limits",
            "nodes": [
                {"task_id": "weather", "target_mode": "expert_meteorology", "goal": "气象分析",
                 "task_contract": {"protocol_version": "workflow.v1", "question": "静稳形势",
                                   "deliverables": ["静稳指数"]}},
                {"task_id": "analysis", "target_mode": "expert_analysis", "goal": "常规分析",
                 "task_contract": {"protocol_version": "workflow.v1", "question": "超标统计",
                                   "deliverables": ["超标频次统计"]}},
            ],
        },
    )

    assert result["success"] is True
    by_mode = {call["target_mode"]: call for call in calls}
    assert by_mode["expert_meteorology"]["max_iterations"] == 15
    assert by_mode["expert_analysis"]["max_iterations"] == 20
    views = result["data"]["node_results"]
    assert views["weather"]["target_mode"] == "expert_meteorology"
    assert views["weather"]["timeout_seconds"] == 300
    assert views["analysis"]["target_mode"] == "expert_analysis"
    assert views["analysis"]["timeout_seconds"] == 360


@pytest.mark.asyncio
async def test_run_agent_workflow_rejects_invalid_nodes():
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "invalid",
            "nodes": [{"task_id": "missing-goal", "target_mode": "expert"}],
        }
    )
    assert result["success"] is False
    assert "缺少 target_mode 或 goal" in result["result"]


@pytest.mark.asyncio
async def test_run_agent_workflow_returns_node_envelopes(monkeypatch):
    calls = []

    class FakeSubAgentTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {
                "status": "success",
                "success": True,
                "result": kwargs["goal"],
                "data": {
                    "result_envelope": {
                        "status": "completed",
                        "summary": kwargs["goal"],
                        "outputs": {},
                        "evidence": [{"source": kwargs["goal"]}],
                        "artifacts": [],
                    }
                },
            }

    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: FakeSubAgentTool()),
    )
    result = await RunAgentWorkflowTool().execute(
        workflow={
            "workflow_id": "report-1",
            "nodes": [
                {"task_id": "air", "target_mode": "expert", "goal": "空气分析"},
                {"task_id": "weather", "target_mode": "expert", "goal": "气象分析"},
                {
                    "task_id": "synthesis",
                    "target_mode": "expert",
                    "goal": "交叉分析",
                    "dependencies": ["air", "weather"],
                },
            ],
        },
    )
    assert result["success"] is True
    assert result["data"]["status"] == "succeeded"
    assert result["data"]["node_results"]["air"]["result_envelope"]["status"] == "completed"
    assert result["data"]["node_errors"] == {}
    assert set(result["data"]["node_lineage"]) == {"air", "weather", "synthesis"}
    assert all(call["target_mode"] != "report" for call in calls)


@pytest.mark.asyncio
async def test_run_agent_workflow_requires_workflow_definition():
    result = await RunAgentWorkflowTool().execute()
    assert result["success"] is False
    assert "workflow" in result["result"]


@pytest.mark.asyncio
async def test_run_agent_workflow_returns_compact_view_and_persists_full_results(monkeypatch, tmp_path):
    """父 Agent 只拿紧凑视图（findings 数值+句柄），全文落盘并登记资源。"""
    import json as _json

    monkeypatch.setattr(
        "app.utils.path_config.get_sessions_dir",
        lambda: tmp_path / "sessions",
    )
    embedded_json = (
        "```json\n"
        + _json.dumps({
            "status": "completed_with_gaps",
            "findings": [{"statement": "内嵌重复，不应进摘要"}],
            "padding": "x" * 5000,
        }, ensure_ascii=False)
        + "\n```"
    )
    answer = "## 核心判断\n\n无轻度以上污染。\n\n" + embedded_json

    class FakeSubAgentTool:
        async def execute(self, **kwargs):
            return {
                "status": "success",
                "success": True,
                "result": answer,
                "data": {
                    "file_paths": [
                        "backend/backend_data_registry/sessions/child/data/memo.md"
                    ],
                    "resource_refs": [{
                        "resource_id": "res-1",
                        "source_session_id": "child-1",
                    }],
                    "structured_result": {
                        "status": "completed_with_gaps",
                        "findings": [
                            {"statement": "PM2.5 与 CO 小时相关系数 r=0.62", "evidence_ids": ["ev-1"]},
                            {"statement": "污染峰值出现在 09-30 14时、58.5 μg/m³"},
                        ],
                        "evidence": [{"ref_id": "ev-1", "kind": "table", "label": "相关矩阵"}],
                    },
                    "result_envelope": {
                        "status": "completed_with_gaps",
                        "summary": "分析完成。\n" + embedded_json,
                        "evidence": [],
                        "data_gaps": ["组分数据缺测"],
                    },
                },
                "metadata": {
                    "iterations": 3,
                    "thought": "t" * 3000,
                    "capability_policy": {"a": 1},
                },
            }

    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: FakeSubAgentTool()),
    )
    context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "compact-1",
            "nodes": [{
                "task_id": "corr",
                "target_mode": "expert_analysis",
                "goal": "相关性分析",
                "max_iterations": 20,
                "timeout_seconds": 360,
                "task_contract": {
                    "protocol_version": "workflow.v1",
                    "question": "相关性",
                    "deliverables": ["相关矩阵"],
                },
            }],
        },
    )

    assert result["success"] is True
    data = result["data"]
    assert "snapshot" not in data
    view = data["node_results"]["corr"]
    findings_text = _json.dumps(view["result_envelope"]["findings"], ensure_ascii=False)
    assert "r=0.62" in findings_text
    assert "58.5" in findings_text
    assert "```json" not in view["result_envelope"]["summary"]
    assert view["resource_ids"] == ["res-1"]
    assert view["iterations"] == 3
    assert view["max_iterations"] == 20
    assert view["result_envelope"]["data_gaps"] == ["组分数据缺测"]
    assert "thought" not in _json.dumps(view, ensure_ascii=False)
    # 全文落盘到统一资源目录并登记为会话资源
    assert data["full_results"]["path"].endswith("workflow_compact-1_node_results.json")
    declared = [
        item for item in result["resources"]
        if item.get("metadata", {}).get("workflow_id") == "compact-1"
    ]
    assert declared and declared[0]["kind"] == "data"
    full_path = (
        tmp_path / "sessions" / "agent_session_report_session_x" / "data"
        / "workflow_compact-1_node_results.json"
    )
    full = _json.loads(full_path.read_text(encoding="utf-8"))
    assert (
        full["node_results"]["corr"]["data"]["structured_result"]["findings"][0]["statement"]
        == "PM2.5 与 CO 小时相关系数 r=0.62"
    )
    assert full["node_results"]["corr"]["metadata"]["thought"] == "t" * 3000


@pytest.mark.asyncio
async def test_persist_parent_snapshot_uses_mode_aware_resolver(monkeypatch):
    loaded_modes = []
    saved_modes = []

    class FakeSession:
        session_id = "report_session_x"
        metadata: dict = {}

    async def fake_load(session_id, *, mode=None, include_messages=True):
        loaded_modes.append((session_id, mode, include_messages))
        return FakeSession()

    async def fake_save(session, *, mode=None, update_timestamp=True):
        saved_modes.append(mode)
        return True

    monkeypatch.setattr(session_resolver, "load_session_for_mode", fake_load)
    monkeypatch.setattr(session_resolver, "save_session_metadata_for_mode", fake_save)

    emitted = []
    context = SimpleNamespace(
        session_id="report_session_x",
        runtime_mode="report",
        workflow_event_sink=emitted.append,
    )
    snapshot = {"workflow_id": "wf-1", "status": "running"}

    RunAgentWorkflowTool._persist_parent_snapshot(context, snapshot)
    pending = list(getattr(context, "workflow_persistence_tasks", set()))
    assert pending
    await asyncio.gather(*pending)

    assert loaded_modes == [("report_session_x", "report", False)]
    assert saved_modes == ["report"]
    assert context.workflow_persistence_tasks == set()
    assert emitted and emitted[0]["workflow_id"] == "wf-1"
    assert FakeSession.metadata["workflow_coordinators"]["wf-1"] == snapshot
    assert "workflow_coordinator" not in FakeSession.metadata


@pytest.mark.asyncio
async def test_persist_parent_snapshot_ignores_missing_session(monkeypatch):
    async def fake_load(session_id, *, mode=None, include_messages=True):
        return None

    async def fake_save(session, *, mode=None, update_timestamp=True):
        raise AssertionError("save must not be called when session is missing")

    monkeypatch.setattr(session_resolver, "load_session_for_mode", fake_load)
    monkeypatch.setattr(session_resolver, "save_session_metadata_for_mode", fake_save)

    context = SimpleNamespace(session_id="missing", runtime_mode="report")
    RunAgentWorkflowTool._persist_parent_snapshot(context, {"workflow_id": "wf-x"})
    pending = list(getattr(context, "workflow_persistence_tasks", set()))
    await asyncio.gather(*pending)


@pytest.mark.asyncio
async def test_non_report_mode_allows_expert_nodes(monkeypatch):
    async def fake_execute(self, **kwargs):
        return {
            "status": "success",
            "success": True,
            "result": kwargs["goal"],
            "data": {"result_envelope": {"status": "completed", "summary": kwargs["goal"], "evidence": [], "artifacts": []}},
        }

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="assistant", session_id="assistant_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "assistant-1",
            "nodes": [
                {"task_id": "air", "target_mode": "expert", "goal": "综合研判"},
            ],
        },
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_report_mode_allows_whitelisted_modes(monkeypatch):
    calls = []

    async def fake_execute(self, **kwargs):
        calls.append(kwargs["target_mode"])
        return {
            "status": "success",
            "success": True,
            "result": kwargs["goal"],
            "data": {"result_envelope": {"status": "completed", "summary": kwargs["goal"], "evidence": [], "artifacts": []}},
        }

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "report-wl",
            "nodes": [
                {"task_id": "air", "target_mode": "query_monitoring_station", "goal": "站点监测取数"},
                {"task_id": "met", "target_mode": "expert_meteorology", "goal": "气象研判",
                 "task_contract": {"protocol_version": "workflow.v1", "question": "静稳形势",
                                   "deliverables": ["静稳指数与输送通道结论"]}},
                {"task_id": "air-expert", "target_mode": "expert_analysis", "goal": "数据研判",
                 "task_contract": {"protocol_version": "workflow.v1", "question": "超标统计",
                                   "deliverables": ["超标频次与时空对比"]}},
            ],
        },
    )
    assert result["success"] is True
    assert set(calls) == {"query_monitoring_station", "expert_meteorology", "expert_analysis"}


@pytest.mark.asyncio
async def test_report_mode_rejects_generic_monitoring_nodes(monkeypatch):
    """报告编排不再使用综合问数兜底：query_monitoring 节点整单拒绝并要求先确认层级。"""
    executed = []

    async def fake_execute(self, **kwargs):
        executed.append(kwargs["target_mode"])
        raise AssertionError("sub agent must not be invoked")

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "report-monitoring",
            "nodes": [
                {"task_id": "air", "target_mode": "query_monitoring", "goal": "监测取数"},
            ],
        },
    )
    assert result["success"] is False
    assert "query_monitoring_station" in result["result"]
    assert "query_monitoring_city" in result["result"]
    assert "向用户确认" in result["result"]
    assert "air" in result["result"]
    assert executed == []


@pytest.mark.asyncio
async def test_report_mode_rejects_generic_query_nodes(monkeypatch):
    """报告编排不再暴露综合问数：query 节点整单拒绝并指路 query_monitoring/query_forecast。"""
    executed = []

    async def fake_execute(self, **kwargs):
        executed.append(kwargs["target_mode"])
        raise AssertionError("sub agent must not be invoked")

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "report-query",
            "nodes": [
                {"task_id": "air", "target_mode": "query", "goal": "取数"},
            ],
        },
    )
    assert result["success"] is False
    assert "query_monitoring" in result["result"]
    assert "query_forecast" in result["result"]
    assert "air" in result["result"]
    assert executed == []


@pytest.mark.asyncio
async def test_report_mode_rejects_non_dag_specialist_nodes(monkeypatch):
    """报告 DAG 不能借节点模式绕过取数/领域专家白名单。"""
    async def fake_execute(self, **kwargs):
        raise AssertionError("sub agent must not be invoked")

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "report-invalid-mode",
            "nodes": [{"task_id": "writer", "target_mode": "report", "goal": "成稿"}],
        },
    )
    assert result["success"] is False
    assert "writer" in result["result"]
    assert "仅允许" in result["result"]


@pytest.mark.asyncio
async def test_non_report_mode_still_allows_generic_query(monkeypatch):
    """非报告父模式（assistant/social 等）仍可使用综合 query。"""
    calls = []

    async def fake_execute(self, **kwargs):
        calls.append(kwargs["target_mode"])
        return {
            "status": "success",
            "success": True,
            "result": kwargs["goal"],
            "data": {"result_envelope": {"status": "completed", "summary": kwargs["goal"], "evidence": [], "artifacts": []}},
        }

    monkeypatch.setattr(CallSubAgentTool, "execute", fake_execute)
    context = SimpleNamespace(runtime_mode="assistant", session_id="assistant_session_x")
    result = await RunAgentWorkflowTool().execute(
        context=context,
        workflow={
            "workflow_id": "assistant-wf",
            "nodes": [
                {"task_id": "air", "target_mode": "query", "goal": "取数"},
            ],
        },
    )
    assert result["success"] is True
    assert calls == ["query"]
