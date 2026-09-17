import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models.scheduled_task_models import ScheduledTaskExecutionDB
from app.scheduled_tasks.models import ExecutionStatus, StepExecution, TaskExecution
from app.scheduled_tasks.storage import create_execution_storage

DB_BACKEND_AVAILABLE = True
try:
    from app.scheduled_tasks.storage.execution_storage_db import (
        ExecutionStorageDB,
        _get_engine,
        _import_legacy_rows,
    )
except Exception:  # noqa: BLE001
    DB_BACKEND_AVAILABLE = False


def _execution(index: int, task_id: str, *, status=ExecutionStatus.SUCCESS) -> TaskExecution:
    started_at = datetime.now() - timedelta(minutes=index)
    return TaskExecution(
        execution_id=f"{task_id}-exec-{index}",
        task_id=task_id,
        task_name="入库验证",
        session_id=f"session-{index}",
        status=status,
        started_at=started_at,
        completed_at=(
            started_at + timedelta(seconds=120)
            if status != ExecutionStatus.RUNNING
            else None
        ),
        duration_seconds=120.0 if status != ExecutionStatus.RUNNING else None,
        total_steps=1,
        completed_steps=1 if status == ExecutionStatus.SUCCESS else 0,
        steps=[
            StepExecution(
                step_id="step-1",
                status=status,
                agent_prompt="生成报告",
                agent_response="报告已生成",
                tool_calls=[{"name": "create_report_package", "media": ["/tmp/x.png"]}],
            )
        ],
        trigger_type="event",
        event_id=f"event-{index}",
        event_type="xuchang.station_daily_pollution.review_completed",
        event_attributes={"city": "许昌市"},
    )


async def _delete_test_rows():
    from sqlalchemy import delete

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            delete(ScheduledTaskExecutionDB).where(
                ScheduledTaskExecutionDB.task_id.like("dbtest-%")
            )
        )


@pytest.fixture
def db_storage():
    if not DB_BACKEND_AVAILABLE:
        pytest.skip("execution db backend unavailable")
    storage = ExecutionStorageDB(import_legacy=False)
    yield storage
    # 只清理本测试写入的 dbtest- 前缀数据，不动真实历史记录
    storage._run(_delete_test_rows())


@pytest.mark.skipif(not DB_BACKEND_AVAILABLE, reason="execution db backend unavailable")
def test_crud_roundtrip_keeps_full_payload(db_storage):
    task_id = f"dbtest-{uuid.uuid4().hex[:8]}"
    execution = _execution(1, task_id)
    db_storage.create(execution)

    loaded = db_storage.get(execution.execution_id)
    assert loaded is not None
    assert loaded.task_id == task_id
    assert loaded.event_attributes == {"city": "许昌市"}
    assert loaded.steps[0].tool_calls[0]["name"] == "create_report_package"

    loaded.status = ExecutionStatus.FAILED
    loaded.error_message = "超时"
    db_storage.update(loaded)

    reloaded = db_storage.get(execution.execution_id)
    assert reloaded.status == ExecutionStatus.FAILED
    assert reloaded.error_message == "超时"


@pytest.mark.skipif(not DB_BACKEND_AVAILABLE, reason="execution db backend unavailable")
def test_history_is_not_trimmed_beyond_legacy_cap(db_storage):
    task_id = f"dbtest-{uuid.uuid4().hex[:8]}"
    for index in range(60):
        db_storage.create(_execution(index, task_id))

    records, total = db_storage.list_by_task_page(task_id, page=1, page_size=10)
    assert total == 60
    assert len(records) == 10
    # 无清理：全部历史可分页取回，且按开始时间倒序
    _, total_all = db_storage.list_recent_page(page=1, page_size=1)
    assert total_all >= 60
    assert records[0].started_at >= records[-1].started_at


@pytest.mark.skipif(not DB_BACKEND_AVAILABLE, reason="execution db backend unavailable")
def test_statistics_and_status_filter(db_storage):
    task_id = f"dbtest-{uuid.uuid4().hex[:8]}"
    db_storage.create(_execution(1, task_id, status=ExecutionStatus.SUCCESS))
    db_storage.create(_execution(2, task_id, status=ExecutionStatus.FAILED))
    db_storage.create(_execution(3, task_id, status=ExecutionStatus.RUNNING))

    stats = db_storage.get_statistics(task_id=task_id, days=7)
    assert stats["total"] == 3
    assert stats["success"] == 1
    assert stats["failed"] == 1
    assert stats["running"] == 1
    assert stats["avg_duration_seconds"] == 120.0

    running = db_storage.get_running_executions()
    assert any(item.execution_id == f"{task_id}-exec-3" for item in running)

    deleted = db_storage.delete_by_task(task_id)
    assert deleted == 3
    assert db_storage.get(f"{task_id}-exec-1") is None


@pytest.mark.skipif(not DB_BACKEND_AVAILABLE, reason="execution db backend unavailable")
def test_legacy_json_rows_import_once(db_storage, tmp_path):
    task_id = f"dbtest-legacy-{uuid.uuid4().hex[:8]}"
    legacy = tmp_path / "executions.json"
    legacy.write_text(
        __import__("json").dumps([_execution(1, task_id).model_dump(mode="json")]),
        encoding="utf-8",
    )

    imported = db_storage._run(
        _import_legacy_rows(__import__("json").loads(legacy.read_text(encoding="utf-8")))
    )
    assert imported == 1
    assert db_storage.get(f"{task_id}-exec-1") is not None

    # 重复导入幂等
    imported_again = db_storage._run(
        _import_legacy_rows(__import__("json").loads(legacy.read_text(encoding="utf-8")))
    )
    records, total = db_storage.list_by_task_page(task_id, page=1, page_size=10)
    assert total == 1


def test_factory_propagates_db_failure(monkeypatch):
    import app.scheduled_tasks.storage.execution_storage_db as db_module

    monkeypatch.setattr(db_module, "_engine", None)

    def _raise(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db_module, "create_async_engine", _raise)
    with pytest.raises(RuntimeError, match="db down"):
        create_execution_storage()
