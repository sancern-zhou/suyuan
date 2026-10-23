# -*- coding: utf-8 -*-
"""运行监控数据采集与工具测试。"""
import asyncio
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB
from app.scheduled_tasks.models import ExecutionStatus, TaskExecution
from app.scheduled_tasks.storage.execution_storage_db import DatabaseExecutionStorage
from app.tools.runtime_monitor import collector


def _storage(tmp_path):
    """sqlite 存储夹具。

    runner 复用生产 run_db：collector 协程运行中会同步调 storage（嵌套
    DB 访问），run_db 在有活动 loop 时用独立线程执行，与生产行为一致。
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'executions.db'}",
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.new_event_loop()

    async def _prepare():
        async with engine.begin() as conn:
            await conn.run_sync(
                ScheduledTaskExecutionDB.__table__.create,
                checkfirst=True,
            )

    from app.db.sync_bridge import run_db

    loop.run_until_complete(_prepare())
    storage = DatabaseExecutionStorage(
        session_factory=factory,
        runner=run_db,
    )
    return engine, loop, storage


def _execution(
    execution_id: str,
    task_id: str,
    status: ExecutionStatus,
    started_at: datetime,
):
    return TaskExecution(
        execution_id=execution_id,
        task_id=task_id,
        task_name="测试任务",
        session_id=f"session-{execution_id}",
        status=status,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=30),
        duration_seconds=30.0,
        trigger_type="schedule",
        total_steps=1,
        completed_steps=1,
        error_message="boom" if status == ExecutionStatus.FAILED else None,
        steps=[],
    )


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# -- resolve_window -----------------------------------------------------

def test_resolve_window_manual_override(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        window = run(
            collector.resolve_window(storage, "task-monitor", None, window_minutes=30)
        )
        assert window["source"] == "manual"
        assert 25 < (window["end"] - window["start"]).total_seconds() / 60 <= 30
    finally:
        engine.dispose()
        loop.close()


def test_resolve_window_from_last_success(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        started = datetime.now() - timedelta(hours=3)
        storage.create(
            _execution("exec-old", "task-monitor", ExecutionStatus.SUCCESS, started)
        )
        window = run(
            collector.resolve_window(storage, "task-monitor", "exec-current", None)
        )
        assert window["source"] == "last_success"
        assert (
            abs((window["start"] - (started + timedelta(seconds=30))).total_seconds())
            < 5
        )
    finally:
        engine.dispose()
        loop.close()


def test_resolve_window_default_first_run(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        window = run(
            collector.resolve_window(storage, "task-monitor", "exec-current", None)
        )
        assert window["source"] == "default_first_run"
        assert abs((window["end"] - window["start"]).total_seconds() - 3600) < 5
    finally:
        engine.dispose()
        loop.close()


# -- collect_scheduled_task_failures ------------------------------------

def test_collect_task_failures_filters_status_and_self(tmp_path):
    engine, loop, storage = _storage(tmp_path)
    try:
        now = datetime.now()
        storage.create(
            _execution("f1", "task-a", ExecutionStatus.FAILED, now - timedelta(minutes=10))
        )
        storage.create(
            _execution("f2", "task-b", ExecutionStatus.TIMEOUT, now - timedelta(minutes=9))
        )
        storage.create(
            _execution("ok", "task-c", ExecutionStatus.SUCCESS, now - timedelta(minutes=8))
        )
        storage.create(
            _execution("self", "task-monitor", ExecutionStatus.FAILED, now - timedelta(minutes=7))
        )
        storage.create(
            _execution("old", "task-d", ExecutionStatus.FAILED, now - timedelta(hours=5))
        )

        result = run(
            collector.collect_scheduled_task_failures(
                storage,
                since=now - timedelta(hours=1),
                until=now,
                exclude_task_id="task-monitor",
            )
        )
        assert result["available"] is True
        assert result["count"] == 2
        assert {item["task_id"] for item in result["items"]} == {"task-a", "task-b"}
    finally:
        engine.dispose()
        loop.close()


# -- collect_fetcher_failures -------------------------------------------

def test_collect_fetcher_failures_reads_run_log(tmp_path, monkeypatch):
    from app.fetchers.base import run_log

    log_path = tmp_path / "fetcher_runs.jsonl"
    monkeypatch.setattr(run_log, "run_log_path", lambda: log_path)
    now = datetime.now()
    run_log.record_fetcher_run(
        fetcher="weather_fetcher",
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=4),
        status="success",
    )
    run_log.record_fetcher_run(
        fetcher="air_fetcher",
        started_at=now - timedelta(minutes=3),
        finished_at=now - timedelta(minutes=2),
        status="failed",
        error="connection timeout",
    )
    run_log.record_fetcher_run(
        fetcher="old_fetcher",
        started_at=now - timedelta(hours=5),
        finished_at=now - timedelta(hours=4),
        status="failed",
        error="old failure",
    )

    result = collector.collect_fetcher_failures(
        since=now - timedelta(hours=1), until=now
    )
    assert result["available"] is True
    assert result["count"] == 1
    assert result["items"][0]["fetcher"] == "air_fetcher"
    assert "timeout" in result["items"][0]["error"]


# -- collect_baidu_traffic_quota ----------------------------------------

def test_collect_baidu_quota_not_applicable_without_module(monkeypatch):
    # sys.modules 中置 None 会使后续 import 抛 ImportError，模拟非许昌部署。
    monkeypatch.setitem(
        sys.modules, "app.tools.xuchang.traffic_status.quota", None
    )
    result = run(collector.collect_baidu_traffic_quota())
    assert result == {"available": False, "applicable": False}


# -- tool ---------------------------------------------------------------

class _FakeService:
    def __init__(self, storage):
        self.execution_storage = storage


class _Stub:
    """可 await 的固定返回值。"""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _coro():
            return self._value

        return _coro().__await__()


def _tool_context(monkeypatch, task_id="task-monitor", execution_id="exec-9"):
    context = SimpleNamespace(
        scheduled_task_context={"task_id": task_id, "execution_id": execution_id}
    )
    empty = {"available": True, "count": 0, "items": []}
    monkeypatch.setattr(
        collector, "collect_agent_session_errors",
        lambda *, since, until: _Stub(empty),
    )
    monkeypatch.setattr(
        collector, "collect_fetcher_failures",
        lambda *, since, until: dict(empty),
    )
    monkeypatch.setattr(
        collector, "collect_llm_failures",
        lambda *, since: _Stub({"available": True, "count": 0, "buckets": {}}),
    )
    monkeypatch.setattr(
        collector, "collect_baidu_traffic_quota",
        lambda: _Stub({"available": False, "applicable": False}),
    )
    return context


def test_tool_requires_scheduled_task_context():
    from app.tools.runtime_monitor.tool import QueryRuntimeAnomaliesTool

    result = run(
        QueryRuntimeAnomaliesTool().execute(
            context=SimpleNamespace(scheduled_task_context=None)
        )
    )
    assert result["success"] is False
    assert "定时任务" in result["summary"]


def test_tool_success_no_anomalies(tmp_path, monkeypatch):
    from app.tools.runtime_monitor.tool import QueryRuntimeAnomaliesTool

    engine, loop, storage = _storage(tmp_path)
    monkeypatch.setattr(
        "app.scheduled_tasks.service.get_scheduled_task_service",
        lambda: _FakeService(storage),
    )
    context = _tool_context(monkeypatch)
    try:
        result = run(QueryRuntimeAnomaliesTool().execute(context=context))
        assert result["success"] is True
        data = result["data"]
        assert data["has_anomalies"] is False
        assert data["window"]["source"] == "default_first_run"
        assert data["scheduled_task_failures"]["count"] == 0
    finally:
        engine.dispose()
        loop.close()


def test_tool_reports_anomalies(tmp_path, monkeypatch):
    from app.tools.runtime_monitor.tool import QueryRuntimeAnomaliesTool

    engine, loop, storage = _storage(tmp_path)
    monkeypatch.setattr(
        "app.scheduled_tasks.service.get_scheduled_task_service",
        lambda: _FakeService(storage),
    )
    context = _tool_context(monkeypatch)
    try:
        storage.create(
            _execution(
                "f1", "task-x", ExecutionStatus.FAILED,
                datetime.now() - timedelta(minutes=5),
            )
        )
        result = run(QueryRuntimeAnomaliesTool().execute(context=context))
        assert result["success"] is True
        assert result["data"]["has_anomalies"] is True
        assert result["data"]["scheduled_task_failures"]["count"] == 1
        assert "存在异常" in result["summary"]
    finally:
        engine.dispose()
        loop.close()
