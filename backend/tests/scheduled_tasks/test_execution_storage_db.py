import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB
from app.scheduled_tasks.models import ExecutionStatus, TaskExecution
from app.scheduled_tasks.storage.execution_storage_db import (
    DatabaseExecutionStorage,
    execution_db_enabled,
)


def _execution(index: int, task_id: str = "task-1") -> TaskExecution:
    started_at = datetime.now() - timedelta(days=1) + timedelta(minutes=index)
    return TaskExecution(
        execution_id=f"execution-{index}",
        task_id=task_id,
        task_name="告警分析",
        session_id=f"session-{index}",
        status=ExecutionStatus.SUCCESS,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=30),
        duration_seconds=30.0,
        trigger_type="event",
        total_steps=1,
        completed_steps=1,
        steps=[],
    )


def _storage(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'executions.db'}",
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.new_event_loop()

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(ScheduledTaskExecutionDB.metadata.create_all)

    loop.run_until_complete(_prepare())
    storage = DatabaseExecutionStorage(
        session_factory=factory,
        runner=loop.run_until_complete,
    )
    return engine, loop, storage


def test_database_execution_storage_roundtrip(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        for index in range(3):
            storage.create(_execution(index))
        storage.create(_execution(99, task_id="other-task"))

        records, total = storage.list_by_task_page("task-1", page=1, page_size=10)
        assert total == 3
        assert [record.execution_id for record in records] == [
            "execution-2",
            "execution-1",
            "execution-0",
        ]

        recent, recent_total = storage.list_recent_page(page=1, page_size=2)
        assert recent_total == 4
        assert len(recent) == 2

        execution = storage.get("execution-0")
        assert execution is not None
        execution.status = ExecutionStatus.FAILED
        storage.update(execution)
        assert storage.get("execution-0").status == ExecutionStatus.FAILED

        assert storage.delete_by_task("other-task") == 1
        assert storage.get("execution-99") is None

        stats = storage.get_statistics(task_id="task-1", days=30)
        assert stats["total"] == 3
        assert stats["success"] == 2
        assert stats["failed"] == 1

        assert storage.get_running_executions() == []
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_database_execution_storage_update_requires_existing(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        try:
            storage.update(_execution(0))
        except ValueError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError("update should fail for a missing execution")
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_execution_db_enabled_defaults(monkeypatch):
    monkeypatch.delenv("SCHEDULED_TASK_EXECUTION_STORAGE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    assert execution_db_enabled() is True

    monkeypatch.setenv("SCHEDULED_TASK_EXECUTION_STORAGE", "file")
    assert execution_db_enabled() is False

    monkeypatch.setenv("SCHEDULED_TASK_EXECUTION_STORAGE", "db")
    assert execution_db_enabled() is True

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SCHEDULED_TASK_EXECUTION_STORAGE", raising=False)
    assert execution_db_enabled() is False
