from concurrent.futures import ThreadPoolExecutor

from app.scheduled_tasks.models import TaskEvent
from app.scheduled_tasks.storage import EventClaimStorage


def _event(event_id: str = "event-1", minute: int = 0) -> TaskEvent:
    return TaskEvent(
        event_id=event_id,
        event_type="yuncheng.alert.created",
        occurred_at=f"2026-07-13T16:{minute:02d}:00+08:00",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )


def test_only_one_claim_wins_for_same_task_and_event(tmp_path):
    storage = EventClaimStorage(tmp_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: storage.try_claim("task-1", _event()), range(8))
        )

    assert sum(result is not None for result in results) == 1


def test_claim_status_survives_new_storage_instance(tmp_path):
    first = EventClaimStorage(tmp_path)
    claim = first.try_claim("task-1", _event())
    first.mark_status(claim.claim_id, "succeeded", execution_id="exec-1")

    restored = EventClaimStorage(tmp_path).get("task-1", "event-1")

    assert restored.status == "succeeded"
    assert restored.execution_id == "exec-1"
    assert restored.event_snapshot["attributes"]["city"] == "运城市"


def test_failed_claim_can_be_retried_explicitly(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    storage.mark_status(claim.claim_id, "failed")

    assert storage.try_claim("task-1", _event()) is None
    retry = storage.retry_failed("task-1", "event-1")

    assert retry.status == "claimed"
    assert retry.attempt == 2


def test_latest_event_snapshot_can_drive_manual_execution(tmp_path):
    storage = EventClaimStorage(tmp_path)
    storage.try_claim("task-1", _event("event-1", minute=0))
    storage.try_claim("task-2", _event("event-2", minute=1))

    latest = storage.latest_event("yuncheng.alert.created")

    assert latest.event_id == "event-2"
