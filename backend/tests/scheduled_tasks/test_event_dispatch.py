import json
from datetime import timedelta

import pytest

from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskStep
from app.scheduled_tasks.service import ScheduledTaskService
from app.scheduled_tasks.storage import (
    EventClaimStorage,
    ExecutionStorage,
    TaskStorage,
)


class FakeAgent:
    def __init__(self, factory):
        self.factory = factory

    async def analyze(self, prompt, **kwargs):
        yield {
            "type": "final_response",
            "content": json.dumps({
                "success": True,
                "broadcast": {
                    "message": "告警摘要",
                    "media": [str(self.factory.report_path)],
                },
            }, ensure_ascii=False),
        }


class FakeAgentFactory:
    def __init__(self, report_path):
        self.report_path = report_path
        self.call_count = 0

    def __call__(self):
        self.call_count += 1
        return FakeAgent(self)


class FakeDelivery:
    def __init__(self):
        self.valid = True
        self.empty = False
        self.fail_user_ids = set()
        self.target_batches = []

    async def resolve_recipients(self, target_user_ids):
        if not self.valid:
            return []
        return [
            {"user_id": user_id, "social_user_id": f"weixin:bot:{user_id}"}
            for user_id in target_user_ids
        ]

    async def deliver(self, *, recipients, **kwargs):
        user_ids = [recipient["user_id"] for recipient in recipients]
        self.target_batches.append(user_ids)
        if self.empty:
            return []
        return [
            {
                "user_id": recipient["user_id"],
                "social_user_id": recipient["social_user_id"],
                "sent": recipient["user_id"] not in self.fail_user_ids,
                "context_persisted": recipient["user_id"] not in self.fail_user_ids,
                "error": (
                    "send failed"
                    if recipient["user_id"] in self.fail_user_ids
                    else None
                ),
            }
            for recipient in recipients
        ]


@pytest.fixture
def agent_factory(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    return FakeAgentFactory(report)


@pytest.fixture
def fake_delivery():
    return FakeDelivery()


@pytest.fixture
def service(tmp_path, agent_factory, fake_delivery):
    return ScheduledTaskService(
        agent_factory=agent_factory,
        task_storage=TaskStorage(tmp_path),
        execution_storage=ExecutionStorage(tmp_path),
        claim_storage=EventClaimStorage(tmp_path),
        event_delivery=fake_delivery,
    )


@pytest.fixture
def event_task():
    return ScheduledTask(
        task_id="event-task",
        name="event task",
        description="event task",
        execution_mode="social",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        event_filters={"city": "运城市"},
        broadcast_enabled=True,
        target_user_ids=["admin-1", "admin-2"],
        steps=[TaskStep(
            step_id="report",
            description="report",
            agent_prompt="report",
        )],
    )


def _event(event_id="alert-1"):
    return TaskEvent(
        event_id=event_id,
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )


@pytest.mark.asyncio
async def test_unmatched_event_does_not_create_agent(service, agent_factory):
    result = await service.publish_event(TaskEvent(
        event_id="event-1",
        event_type="other.event",
    ), wait=True)

    assert result.matched_task_ids == []
    assert agent_factory.call_count == 0


@pytest.mark.asyncio
async def test_matching_event_runs_agent_once_and_broadcasts_to_two_users(
    service,
    event_task,
    agent_factory,
    fake_delivery,
):
    service.create_task(event_task)

    first = await service.publish_event(_event(), wait=True)
    second = await service.publish_event(_event(), wait=True)

    assert first.accepted_task_ids == [event_task.task_id]
    assert second.duplicate_task_ids == [event_task.task_id]
    assert agent_factory.call_count == 1
    assert fake_delivery.target_batches == [["admin-1", "admin-2"]]
    execution = service.execution_storage.get(first.execution_ids[0])
    assert execution.status.value == "success"
    assert len(execution.delivery_results) == 2


@pytest.mark.asyncio
async def test_manual_event_dispatch_can_be_limited_to_one_task(
    service,
    event_task,
    agent_factory,
):
    service.create_task(event_task)
    other = event_task.model_copy(update={
        "task_id": "other-event-task",
        "name": "other event task",
    })
    service.create_task(other)

    result = await service.publish_event(
        _event("manual-one"),
        wait=True,
        target_task_id=event_task.task_id,
    )

    assert result.matched_task_ids == [event_task.task_id]
    assert agent_factory.call_count == 1


@pytest.mark.asyncio
async def test_force_retry_recovers_stale_running_claim(
    service,
    event_task,
    agent_factory,
):
    service.create_task(event_task)
    claim = service.claim_storage.try_claim(event_task.task_id, _event("stale"))
    running = service.claim_storage.mark_status(claim.claim_id, "running")
    fail_stale_running = service.claim_storage.fail_stale_running
    service.claim_storage.fail_stale_running = lambda *args, **kwargs: (
        fail_stale_running(
            *args,
            **kwargs,
            now=running.updated_at + timedelta(seconds=301),
        )
    )

    result = await service.publish_event(
        _event("stale"),
        wait=True,
        force_retry=True,
    )

    assert result.accepted_task_ids == [event_task.task_id]
    assert agent_factory.call_count == 1
    assert service.claim_storage.get(event_task.task_id, "stale").attempt == 2


@pytest.mark.asyncio
async def test_no_valid_recipients_fails_before_agent(
    service,
    event_task,
    agent_factory,
    fake_delivery,
):
    fake_delivery.valid = False
    service.create_task(event_task)

    result = await service.publish_event(_event("alert-no-users"), wait=True)

    claim = service.claim_storage.get(event_task.task_id, "alert-no-users")
    execution = service.execution_storage.get(result.execution_ids[0])
    assert agent_factory.call_count == 0
    assert claim.status == "failed"
    assert execution.status.value == "failed"
    assert "no active bound WeChat recipients" in execution.error_message


@pytest.mark.asyncio
async def test_empty_delivery_result_fails_event_instead_of_false_success(
    service,
    event_task,
    fake_delivery,
):
    fake_delivery.empty = True
    service.create_task(event_task)

    result = await service.publish_event(_event("empty-delivery"), wait=True)

    claim = service.claim_storage.get(event_task.task_id, "empty-delivery")
    execution = service.execution_storage.get(result.execution_ids[0])
    assert claim.status == "failed"
    assert execution.status.value == "failed"
    assert "no recipient results" in execution.error_message


@pytest.mark.asyncio
async def test_retry_delivery_does_not_rerun_agent(
    service,
    event_task,
    agent_factory,
    fake_delivery,
):
    fake_delivery.fail_user_ids = {"admin-2"}
    service.create_task(event_task)
    dispatched = await service.publish_event(_event("partial-delivery"), wait=True)
    initial_agent_calls = agent_factory.call_count
    fake_delivery.fail_user_ids.clear()

    result = await service.retry_failed_delivery(dispatched.execution_ids[0])

    assert result["success"] is True
    assert result["retried_user_ids"] == ["admin-2"]
    assert fake_delivery.target_batches[-1] == ["admin-2"]
    assert agent_factory.call_count == initial_agent_calls


@pytest.mark.asyncio
async def test_total_delivery_failure_keeps_agent_claim_succeeded_for_delivery_retry(
    service,
    event_task,
    agent_factory,
    fake_delivery,
):
    fake_delivery.fail_user_ids = {"admin-1", "admin-2"}
    service.create_task(event_task)

    dispatched = await service.publish_event(_event("total-delivery-failure"), wait=True)

    execution = service.execution_storage.get(dispatched.execution_ids[0])
    claim = service.claim_storage.get(event_task.task_id, "total-delivery-failure")
    assert execution.status.value == "success"
    assert claim.status == "succeeded"
    assert agent_factory.call_count == 1


@pytest.mark.asyncio
async def test_retry_delivery_with_no_longer_valid_recipient_reports_failure(
    service,
    event_task,
    fake_delivery,
):
    fake_delivery.fail_user_ids = {"admin-2"}
    service.create_task(event_task)
    dispatched = await service.publish_event(_event("recipient-disabled"), wait=True)
    fake_delivery.valid = False

    result = await service.retry_failed_delivery(dispatched.execution_ids[0])

    assert result["success"] is False
    assert result["retried_user_ids"] == ["admin-2"]
    assert result["delivery_results"] == []
