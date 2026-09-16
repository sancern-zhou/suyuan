from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app.scheduled_tasks.models import TaskEvent
from app.scheduled_tasks.storage import EventClaimStorage


def _event(event_id: str = "event-1", minute: int = 0) -> TaskEvent:
    return TaskEvent(
        event_id=event_id,
        event_type="xuchang.station_deviation.alert_created",
        occurred_at=f"2026-07-13T16:{minute:02d}:00+08:00",
        attributes={"city": "许昌市"},
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
    assert restored.event_snapshot["attributes"]["city"] == "许昌市"


def test_failed_claim_can_be_retried_explicitly(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    storage.mark_status(claim.claim_id, "failed")

    assert storage.try_claim("task-1", _event()) is None
    retry = storage.retry_failed("task-1", "event-1")

    assert retry.status == "claimed"
    assert retry.attempt == 2


def test_retry_and_reopen_refresh_snapshot_with_latest_dispatch(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    assert claim.event_snapshot["attributes"] == {"city": "运城市"}

    storage.mark_status(claim.claim_id, "failed")
    latest = TaskEvent(
        event_id="event-1",
        event_type="yuncheng.alert.created",
        occurred_at="2026-07-13T16:05:00+08:00",
        attributes={"city": "运城市", "smart_event_dispatch_token": "token-2"},
        payload={"evidence_dir": "/tmp/evidence-2"},
    )
    retried = storage.retry_failed("task-1", "event-1", event=latest)
    assert retried.event_snapshot["attributes"]["smart_event_dispatch_token"] == "token-2"
    assert retried.event_snapshot["payload"]["evidence_dir"] == "/tmp/evidence-2"

    storage.mark_status(claim.claim_id, "succeeded")
    reopened = storage.reopen("task-1", "event-1", event=latest)
    assert reopened.status == "claimed"
    assert reopened.event_snapshot["attributes"]["smart_event_dispatch_token"] == "token-2"
    # Without an event the previous snapshot is preserved.
    storage.mark_status(claim.claim_id, "failed")
    again = storage.retry_failed("task-1", "event-1")
    assert again.event_snapshot["attributes"]["smart_event_dispatch_token"] == "token-2"


def test_latest_event_snapshot_can_drive_manual_execution(tmp_path):
    storage = EventClaimStorage(tmp_path)
    storage.try_claim("task-1", _event("event-1", minute=0))
    storage.try_claim("task-2", _event("event-2", minute=1))

    latest = storage.latest_event("xuchang.station_deviation.alert_created")

    assert latest.event_id == "event-2"


def test_stale_running_claim_can_be_failed_for_manual_retry(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    running = storage.mark_status(claim.claim_id, "running")

    recovered = storage.fail_stale_running(
        "task-1",
        "event-1",
        timeout_seconds=300,
        now=running.updated_at + timedelta(seconds=301),
    )

    assert recovered is not None
    assert recovered.status == "failed"


def test_fresh_running_claim_is_not_failed(tmp_path):
    storage = EventClaimStorage(tmp_path)
    claim = storage.try_claim("task-1", _event())
    running = storage.mark_status(claim.claim_id, "running")

    recovered = storage.fail_stale_running(
        "task-1",
        "event-1",
        timeout_seconds=300,
        now=running.updated_at + timedelta(seconds=299),
    )

    assert recovered is None
    assert storage.get("task-1", "event-1").status == "running"
