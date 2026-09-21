import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB
from app.scheduled_tasks.models.result import TaskResult
from app.scheduled_tasks.storage.task_result_storage_db import (
    DatabaseTaskResultStorage,
    task_result_db_enabled,
)


def _result(index: int, task_id: str = "task-1", **overrides) -> TaskResult:
    payload = dict(
        execution_id=f"execution-{index}",
        task_id=task_id,
        task_name="日报",
        session_id=f"session-{index}",
        status="success",
        started_at=datetime.now() - timedelta(days=1) + timedelta(minutes=index),
        completed_at=datetime.now() - timedelta(days=1) + timedelta(minutes=index, seconds=30),
        city="许昌市",
        station_id=f"station-{index}",
        station_name="许昌ymc",
        pollutant="PM2.5",
        conclusion=f"结论 {index}",
        conclusion_source="distilled",
        findings=["发现1"],
        image_paths=["/data/a.png"],
        document_paths=["/data/report.docx"],
        evidence_package_paths=["/data/evidence/episode.json"],
        report_refs=[{"kind": "report", "ref": "r1"}],
        trigger_type="scheduled",
        extra={"case": {"conclusion": "x"}},
    )
    payload.update(overrides)
    return TaskResult(**payload)


def _storage(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'results.db'}",
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.new_event_loop()

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(
                ScheduledTaskResultDB.__table__.create,
                checkfirst=True,
            )

    loop.run_until_complete(_prepare())
    storage = DatabaseTaskResultStorage(
        session_factory=factory,
        runner=loop.run_until_complete,
    )
    return engine, loop, storage


def test_task_result_storage_roundtrip_and_filters(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        storage.upsert(_result(0))
        storage.upsert(_result(1))
        storage.upsert(_result(2))
        storage.upsert(_result(3, task_id="other-task", city="郑州市", pollutant="O3"))

        records, total = storage.query_page(task_id="task-1")
        assert total == 3
        assert [record.execution_id for record in records] == [
            "execution-2",
            "execution-1",
            "execution-0",
        ]

        records, total = storage.query_page(city="郑州市")
        assert total == 1
        assert records[0].execution_id == "execution-3"

        records, total = storage.query_page(pollutant="PM2.5", page=1, page_size=2)
        assert total == 3
        assert len(records) == 2

        record = storage.get("execution-0")
        assert record is not None
        assert record.conclusion == "结论 0"
        assert record.image_paths == ["/data/a.png"]
        assert record.document_paths == ["/data/report.docx"]
        assert record.evidence_package_paths == ["/data/evidence/episode.json"]
        assert record.extra == {"case": {"conclusion": "x"}}

        storage.upsert(_result(0, conclusion="更新结论"))
        assert storage.get("execution-0").conclusion == "更新结论"

        assert storage.delete_by_task("task-1") == 3
        assert storage.get("execution-0") is None
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_task_result_db_enabled_gate(monkeypatch):
    monkeypatch.delenv("SCHEDULED_TASK_RESULT_STORAGE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert task_result_db_enabled() is False

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    assert task_result_db_enabled() is True

    monkeypatch.setenv("SCHEDULED_TASK_RESULT_STORAGE", "off")
    assert task_result_db_enabled() is False
