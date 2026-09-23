import pytest

from app.agent.workflow.templates import build_report_analysis_workflow


def test_report_template_builds_parallel_sources_and_expert_synthesis():
    definition = build_report_analysis_workflow(
        workflow_id="report-1",
        source_tasks=[
            {"task_id": "air", "target_mode": "expert", "goal": "分析空气"},
            {"task_id": "weather", "target_mode": "expert", "goal": "分析气象"},
        ],
        synthesis_task={"task_id": "synthesis", "target_mode": "expert", "goal": "交叉分析"},
    )
    by_id = {node["task_id"]: node for node in definition["nodes"]}
    assert by_id["synthesis"]["dependencies"] == ["air", "weather"]
    assert set(by_id) == {"air", "weather", "synthesis"}
    assert all(node["target_mode"] != "report" for node in definition["nodes"])


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_tasks": [{"task_id": "air", "target_mode": "chart", "goal": "查询"}]}, "source task"),
        ({"synthesis_task": {"target_mode": "report", "goal": "综合"}}, "synthesis task"),
        ({"delivery_tasks": [{"task_id": "report", "target_mode": "report", "goal": "成稿"}]}, "not supported"),
    ],
)
def test_report_template_enforces_declared_mode_contract(overrides, message):
    options = {
        "workflow_id": "report-contract",
        "source_tasks": [{"task_id": "air", "target_mode": "query", "goal": "查询"}],
        "synthesis_task": {"task_id": "synthesis", "target_mode": "expert", "goal": "综合"},
    }
    options.update(overrides)

    with pytest.raises(ValueError, match=message):
        build_report_analysis_workflow(**options)


def test_report_template_requires_synthesis_to_consume_every_source():
    with pytest.raises(ValueError, match="every source"):
        build_report_analysis_workflow(
            workflow_id="report-incomplete",
            source_tasks=[
                {"task_id": "air", "target_mode": "query", "goal": "查询空气"},
                {"task_id": "weather", "target_mode": "query", "goal": "查询气象"},
            ],
            synthesis_task={
                "task_id": "synthesis",
                "target_mode": "expert",
                "goal": "综合",
                "dependencies": ["air"],
            },
        )
