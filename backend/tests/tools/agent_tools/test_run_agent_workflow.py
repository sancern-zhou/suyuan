import asyncio
from types import SimpleNamespace

import pytest

from app.agent.session import session_resolver
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool


def test_run_agent_workflow_schema_documents_report_dag_example():
    schema = RunAgentWorkflowTool().get_function_schema()
    description = schema["description"]

    for token in (
        "report_analysis_v1",
        "source_tasks",
        "synthesis_task",
        "task_contract",
        "result_schema",
        "dependencies",
    ):
        assert token in description

    properties = schema["parameters"]["properties"]
    assert "source_tasks" in properties["template_options"]["description"]
    assert "不接受 delivery_tasks" in properties["template_options"]["description"]
    assert "max_concurrency" in properties


def test_run_agent_workflow_schema_documents_target_mode_contract():
    schema = RunAgentWorkflowTool().get_function_schema()
    description = schema["description"]
    target_mode = schema["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]

    assert "能力与工具边界" in description
    assert "禁止同一数据源" in description
    assert {"query", "expert", "report"}.issubset(set(target_mode["enum"]))
    call_target_mode = CallSubAgentTool().get_function_schema()["parameters"]["properties"]["target_mode"]
    assert call_target_mode["enum"] == target_mode["enum"]


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
                "data": data,
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
    assert "## 上游节点产物" in context
    assert "backend/data/查询空气质量.json" in context
    assert "禁止对同一数据源重复查询" in context
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
    assert "分析空气质量" in merge_call["context_str"]
    assert "分析气象条件" in merge_call["context_str"]
    assert all(call["_force_isolated_session"] is True for call in calls)


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
async def test_run_agent_workflow_accepts_report_analysis_template(monkeypatch):
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
        workflow_template="report_analysis_v1",
        template_options={
            "workflow_id": "report-template-1",
            "source_tasks": [
                {"task_id": "air", "target_mode": "expert", "goal": "空气分析"},
                {"task_id": "weather", "target_mode": "expert", "goal": "气象分析"},
            ],
            "synthesis_task": {"target_mode": "expert", "goal": "交叉分析", "require_lineage": True},
        },
    )
    assert result["success"] is True
    assert result["data"]["report_analysis"]["status"] == "completed"
    assert result["data"]["report_analysis"]["synthesis_task_id"] == "synthesis"
    assert "node_results" not in result["data"]
    assert "node_lineage" not in result["data"]
    assert "snapshot" not in result["data"]
    assert all(call["target_mode"] != "report" for call in calls)


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
