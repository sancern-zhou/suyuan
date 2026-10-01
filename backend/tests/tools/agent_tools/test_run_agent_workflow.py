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
        for node in result["data"]["snapshot"]["definition"]["nodes"]
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
                {"task_id": "weather", "target_mode": "expert_meteorology", "goal": "气象分析"},
                {"task_id": "analysis", "target_mode": "expert_analysis", "goal": "常规分析"},
            ],
        },
    )

    assert result["success"] is True
    by_mode = {call["target_mode"]: call for call in calls}
    assert by_mode["expert_meteorology"]["max_iterations"] == 15
    assert by_mode["expert_analysis"]["max_iterations"] == 20
    definitions = {
        node["payload"]["target_mode"]: node
        for node in result["data"]["snapshot"]["definition"]["nodes"]
    }
    assert definitions["expert_meteorology"]["timeout_seconds"] == 300
    assert definitions["expert_analysis"]["timeout_seconds"] == 360


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
    assert result["data"]["node_results"]["air"]["data"]["result_envelope"]["status"] == "completed"
    assert result["data"]["node_errors"] == {}
    assert set(result["data"]["node_lineage"]) == {"air", "weather", "synthesis"}
    assert all(call["target_mode"] != "report" for call in calls)


@pytest.mark.asyncio
async def test_run_agent_workflow_requires_workflow_definition():
    result = await RunAgentWorkflowTool().execute()
    assert result["success"] is False
    assert "workflow" in result["result"]


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
async def test_report_mode_enforces_node_mode_whitelist():
    async def fail_submit(**kwargs):
        raise AssertionError("sub agent must not be invoked")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        RunAgentWorkflowTool,
        "_build_sub_agent_tool",
        staticmethod(lambda: SimpleNamespace(execute=fail_submit)),
    )
    try:
        context = SimpleNamespace(runtime_mode="report", session_id="report_session_x")
        result = await RunAgentWorkflowTool().execute(
            context=context,
            workflow={
                "workflow_id": "report-1",
                "nodes": [
                    {"task_id": "met", "target_mode": "expert_meteorology", "goal": "气象研判"},
                    {"task_id": "legacy", "target_mode": "expert", "goal": "综合研判"},
                    {"task_id": "viz", "target_mode": "chart", "goal": "出图"},
                ],
            },
        )
    finally:
        monkeypatch.undo()
    assert result["success"] is False
    assert "仅允许 target_mode" in result["result"]
    assert "legacy" in result["result"] and "viz" in result["result"]


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
                {"task_id": "air", "target_mode": "query", "goal": "取数"},
                {"task_id": "met", "target_mode": "expert_meteorology", "goal": "气象研判"},
                {"task_id": "air-expert", "target_mode": "expert_analysis", "goal": "数据研判"},
            ],
        },
    )
    assert result["success"] is True
    assert set(calls) == {"query", "expert_meteorology", "expert_analysis"}
