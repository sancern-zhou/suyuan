"""Gold scoring and controlled comparison must not turn failures into wins."""
import pytest

from app.agent.workflow.evaluation import EvaluationRunner, ReplayChildModel, default_cases, score_result


def test_score_requires_observed_evidence_and_rejects_invalid_numbers():
    case = default_cases()[0]
    paths = {"air_甲市": "/tmp/case/air.json"}
    correct = {"facts": {"mean_pm25": 20}, "evidence": list(paths.values())}
    assert not score_result(case, correct, paths, set())["passed"]
    assert score_result(case, correct, paths, set(paths.values()))["passed"]
    for value in (True, float("nan"), float("inf"), 21, "20"):
        bad = {**correct, "facts": {"mean_pm25": value}}
        assert not score_result(case, bad, paths, set(paths.values()))["passed"]
    correct["evidence"].append("/tmp/other/source.json")
    assert not score_result(case, correct, paths, set(paths.values()))["passed"]


def test_joint_analysis_cannot_pass_with_a_causal_claim():
    case = default_cases()[2]
    paths = {name: f"/tmp/{name}.json" for name in case.datasets}
    result = {"facts": case.expected, "evidence": list(paths.values()), "causal_claim": "established"}
    assert not score_result(case, result, paths, set(paths.values()))["passed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("index", range(3))
async def test_replay_exercises_both_paths_without_fake_token_counts(index, tmp_path):
    case = default_cases()[index]
    for variant in ("direct", "dag"):
        runner = EvaluationRunner(case, variant, tmp_path / variant, ReplayChildModel())
        result = await runner.run(backend="replay", timeout=10)
        assert result["error"] is None
        assert result["quality"]["passed"]
        assert result["duplicate_acquisitions"] == 0
        assert result["usage"]["input_tokens"] is None
        assert result["node_count"] == (len(case.datasets) + int(case.mode == "expert") if variant == "dag" else 0)
        if variant == "dag" and case.mode == "expert":
            assert sum(call["tool"] == "read_file" for call in result["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_model_failure_is_reported_without_leaking_exception_text(tmp_path):
    class BrokenModel:
        async def chat_anthropic(self, **kwargs):
            raise ConnectionError("sensitive provider credential")
    runner = EvaluationRunner(default_cases()[0], "direct", tmp_path / "case", BrokenModel())
    result = await runner.run(backend="live", timeout=1)
    assert result["error"] == "ConnectionError"
    assert result["quality"]["passed"] is False
    assert "sensitive" not in str(result)


@pytest.mark.asyncio
async def test_child_cannot_call_dag_or_read_another_cases_file(tmp_path):
    runner = EvaluationRunner(default_cases()[0], "dag", tmp_path / "case", ReplayChildModel())
    with pytest.raises(ValueError, match="capabilities"):
        await runner.dispatch("run_agent_workflow", {}, mode="query_monitoring_city", parent=False)
    with pytest.raises(ValueError, match="fixture files"):
        await runner.business_tool("read_file", {"path": "/tmp/other.json"})
    assert "read_file" in {tool["name"] for tool in runner.schemas("query", parent=True)}
    assert "read_file" not in {tool["name"] for tool in runner.schemas("query_monitoring_city", parent=False)}


@pytest.mark.asyncio
async def test_live_loop_accepts_sdk_content_blocks_and_actual_usage(tmp_path):
    class SdkBlock:
        def model_dump(self, **kwargs):
            return {"type": "tool_use", "id": "done", "name": "submit_evaluation",
                    "input": {"facts": {}, "evidence": [], "summary": "no data"}}
    class Model:
        async def chat_anthropic(self, **kwargs):
            return {"content": [SdkBlock()], "model": "test-model",
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
    runner = EvaluationRunner(default_cases()[0], "direct", tmp_path / "sdk", Model())
    result = await runner.run(backend="live", timeout=1)
    assert result["error"] is None
    assert result["llm_calls"] == 1
    assert result["usage"]["input_tokens"] == 10
    assert not result["quality"]["passed"]


@pytest.mark.asyncio
async def test_live_child_receives_explicit_upstream_file_handles(tmp_path):
    seen = []
    class Model:
        async def chat_anthropic(self, **kwargs):
            seen.append(kwargs["messages"][0]["content"])
            return {"content": [{"type": "tool_use", "id": "done", "name": "submit_evaluation",
                                 "input": {"facts": {}, "evidence": [], "summary": "received"}}]}
    runner = EvaluationRunner(default_cases()[0], "dag", tmp_path / "handles", Model())
    path = runner.paths["air_甲市"]
    await runner.execute(target_mode="expert_analysis", goal="analyze upstream",
                         _upstream_handles=[{"source_task_id": "air", "file_path": path}])
    assert path in seen[0]
    assert "不把task_id当文件名" in seen[0]


@pytest.mark.asyncio
async def test_evaluation_dag_never_uses_deployment_workflow_registry(tmp_path, monkeypatch):
    class DeploymentRegistry:
        async def register(self, *args, **kwargs):
            pytest.fail("evaluation must not register with deployment Redis")
    monkeypatch.setattr("app.tools.agent_tools.run_agent_workflow.active_workflow_registry", DeploymentRegistry())
    runner = EvaluationRunner(default_cases()[0], "dag", tmp_path / "isolated", ReplayChildModel())
    assert runner.workflow_registry._store is None
    result = await runner.run(backend="replay", timeout=2)
    assert result["quality"]["passed"]
    assert await runner.workflow_registry.list() == []
