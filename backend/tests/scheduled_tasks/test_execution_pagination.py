from datetime import datetime, timedelta

from app.api.scheduled_task_routes import _execution_summary
from app.scheduled_tasks.models import (
    ExecutionStatus,
    StepExecution,
    TaskExecution,
)
from app.scheduled_tasks.storage import ExecutionStorage


def _execution(index: int, task_id: str = "task-1") -> TaskExecution:
    started_at = datetime(2026, 1, 1) + timedelta(minutes=index)
    return TaskExecution(
        execution_id=f"execution-{index}",
        task_id=task_id,
        task_name="告警分析",
        session_id=f"session-{index}",
        status=ExecutionStatus.SUCCESS,
        started_at=started_at,
        total_steps=1,
        completed_steps=1,
        steps=[
            StepExecution(
                step_id="step-1",
                status=ExecutionStatus.SUCCESS,
                agent_prompt="分析告警",
                agent_response="报告已保存到 /tmp/reports/alert-analysis.pdf",
                agent_thoughts=["不应出现在列表响应中"],
                tool_calls=[{"name": "expensive-payload"}],
                result_visuals=[{"file_name": "trend.png"}],
            )
        ],
    )


def test_execution_storage_paginates_after_filtering_and_sorting(tmp_path):
    storage = ExecutionStorage(tmp_path)
    for index in range(15):
        storage.create(_execution(index))
    storage.create(_execution(99, task_id="other-task"))

    records, total = storage.list_by_task_page("task-1", page=2, page_size=10)

    assert total == 15
    assert [record.execution_id for record in records] == [
        "execution-4",
        "execution-3",
        "execution-2",
        "execution-1",
        "execution-0",
    ]


def test_execution_summary_omits_heavy_step_details_and_keeps_artifacts():
    summary = _execution_summary(_execution(1)).model_dump(mode="json")

    assert "steps" not in summary
    assert "event_attributes" not in summary
    assert "delivery_results" not in summary
    assert summary["artifacts"] == ["trend.png", "alert-analysis.pdf"]
