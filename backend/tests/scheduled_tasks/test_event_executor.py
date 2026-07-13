import json

import pytest

from app.scheduled_tasks.event_output import parse_event_task_output
from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskStep
from app.scheduled_tasks.storage import ExecutionStorage, TaskStorage


def test_parser_accepts_fenced_broadcast_json(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")

    payload = {
        "success": True,
        "broadcast": {"message": "告警摘要", "media": [str(report)]},
    }
    output = parse_event_task_output(f"```json\n{json.dumps(payload)}\n```")

    assert output.success is True
    assert output.broadcast.message == "告警摘要"
    assert output.broadcast.media == [str(report)]


def test_parser_rejects_missing_attachment(tmp_path):
    missing = tmp_path / "missing.docx"

    with pytest.raises(ValueError, match="attachment does not exist"):
        parse_event_task_output(json.dumps({
            "success": True,
            "broadcast": {"message": "告警摘要", "media": [str(missing)]},
        }))


class FakeAgent:
    def __init__(self, report_path):
        self.report_path = report_path
        self.prompts = []

    async def analyze(self, prompt, **kwargs):
        self.prompts.append(prompt)
        payload = {
            "success": True,
            "broadcast": {
                "message": "告警摘要",
                "media": [str(self.report_path)],
            },
        }
        yield {
            "type": "final_response",
            "content": json.dumps(payload, ensure_ascii=False),
        }


@pytest.mark.asyncio
async def test_executor_appends_event_context_to_agent_prompt(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    agent = FakeAgent(report)
    task_storage = TaskStorage(storage_dir=tmp_path)
    execution_storage = ExecutionStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="event-task",
        name="event task",
        description="event task",
        execution_mode="social",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        steps=[TaskStep(step_id="report", description="report", agent_prompt="处理告警")],
    )
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=execution_storage,
        agent_factory=lambda: agent,
    )
    event = TaskEvent(
        event_id="alert-1",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )

    execution = await executor.execute_task(task, event=event)

    assert execution.trigger_type == "event"
    assert execution.event_id == "alert-1"
    assert "alert-1" in agent.prompts[0]
    assert "yuncheng.alert.created" in agent.prompts[0]
    assert "/tmp/evidence" in agent.prompts[0]
    assert "不要直接发送通知" in agent.prompts[0]
