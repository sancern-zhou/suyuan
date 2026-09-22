from app.agent.workflow.templates import build_report_analysis_workflow


def test_report_template_builds_parallel_sources_and_delivery_fanout():
    definition = build_report_analysis_workflow(
        workflow_id="report-1",
        source_tasks=[
            {"task_id": "air", "target_mode": "expert", "goal": "分析空气"},
            {"task_id": "weather", "target_mode": "expert", "goal": "分析气象"},
        ],
        synthesis_task={"task_id": "synthesis", "target_mode": "expert", "goal": "交叉分析"},
        delivery_tasks=[
            {"task_id": "charts", "target_mode": "chart", "goal": "生成图表"},
            {"task_id": "report", "target_mode": "report", "goal": "输出报告"},
        ],
    )
    by_id = {node["task_id"]: node for node in definition["nodes"]}
    assert by_id["synthesis"]["dependencies"] == ["air", "weather"]
    assert by_id["charts"]["dependencies"] == ["synthesis"]
    assert by_id["report"]["dependencies"] == ["synthesis"]
