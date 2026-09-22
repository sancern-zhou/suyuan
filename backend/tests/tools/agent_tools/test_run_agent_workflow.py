import pytest

from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool


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
    class FakeSubAgentTool:
        async def execute(self, **kwargs):
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
    assert result["data"]["node_lineage"]["synthesis"]["inputs"][0]["source_task_id"] == "air"
