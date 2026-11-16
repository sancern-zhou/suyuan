# -*- coding: utf-8 -*-
"""任务级自愈工具测试（fake Redis / fake 服务 / fake 调度器）。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.monitoring import anomaly_emitter
from app.tools.runtime_monitor import self_heal


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.fail = False

    async def set(self, key, value, nx=False, ex=None):
        if self.fail:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def incr(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return key in self.store


class _FakeTaskStorage:
    def __init__(self, tasks):
        self._tasks = tasks

    def get(self, task_id):
        return self._tasks.get(task_id)


class _FakeExecutionStorage:
    def __init__(self, recent):
        self._recent = recent

    def list_by_task(self, task_id, limit=10, status=None):
        return self._recent.get(task_id, [])


class _FakeService:
    def __init__(self, tasks, recent):
        self.task_storage = _FakeTaskStorage(tasks)
        self.execution_storage = _FakeExecutionStorage(recent)
        self.retried: list[str] = []

    async def execute_task_now(self, task_id):
        self.retried.append(task_id)
        return SimpleNamespace(status="success")


def _task(task_id="task_biz", tags=None, trigger_type="schedule", enabled=True):
    return SimpleNamespace(
        task_id=task_id,
        name="业务任务",
        tags=tags or [],
        trigger_type=trigger_type,
        enabled=enabled,
    )


def _ctx():
    return SimpleNamespace(
        scheduled_task_context={"task_id": "task_runtime_monitor", "execution_id": "exec-1"}
    )


@pytest.fixture()
def env(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(anomaly_emitter, "_get_redis", lambda: fake_redis)

    service = _FakeService(
        tasks={"task_biz": _task()},
        recent={"task_biz": [SimpleNamespace(status="failed")]},
    )
    monkeypatch.setattr(
        "app.scheduled_tasks.service.get_scheduled_task_service", lambda: service
    )
    return fake_redis, service


def test_gate_rejects_non_scheduled_context(env):
    result = asyncio.run(self_heal.retry_scheduled_task_tool.execute(context=None, task_id="task_biz"))
    assert result["success"] is False
    assert "定时任务执行上下文" in result["summary"]


def test_retry_success_runs_in_background(env):
    _, service = env
    result = asyncio.run(
        self_heal.retry_scheduled_task_tool.execute(context=_ctx(), task_id="task_biz")
    )
    assert result["success"] is True
    # create_task 已调度，让事件循环跑完后台协程
    asyncio.run(asyncio.sleep(0))
    assert service.retried == ["task_biz"]


def test_retry_cooldown_blocks_second_attempt(env):
    _, service = env
    ctx = _ctx()
    first = asyncio.run(self_heal.retry_scheduled_task_tool.execute(context=ctx, task_id="task_biz"))
    second = asyncio.run(self_heal.retry_scheduled_task_tool.execute(context=ctx, task_id="task_biz"))
    assert first["success"] is True
    assert second["success"] is False
    assert "冷却" in second["summary"]
    asyncio.run(asyncio.sleep(0))
    assert service.retried == ["task_biz"]


def test_retry_daily_limit_refuses(env):
    fake_redis, service = env
    day_key = f"monitor:selfheal:day:task:task_biz:{__import__('datetime').datetime.now().strftime('%Y%m%d')}"
    fake_redis.store[day_key] = self_heal.SELF_HEAL_DAILY_LIMIT
    result = asyncio.run(
        self_heal.retry_scheduled_task_tool.execute(context=_ctx(), task_id="task_biz")
    )
    assert result["success"] is False
    assert "人工" in result["summary"]
    assert service.retried == []


@pytest.mark.parametrize(
    "task,recent,keyword",
    [
        (_task(tags=["runtime-monitor"]), [SimpleNamespace(status="failed")], "监控任务自身"),
        (_task(trigger_type="event"), [SimpleNamespace(status="failed")], "事件驱动"),
        (_task(enabled=False), [SimpleNamespace(status="failed")], "禁用"),
        (_task(), [SimpleNamespace(status="success")], "已成功"),
        (_task(), None, "不存在"),  # recent=None 时 list_by_task 返回 []，任务在 tasks 里不存在
    ],
)
def test_retry_guards(env, task, recent, keyword):
    _, service = env
    if keyword == "不存在":
        result = asyncio.run(
            self_heal.retry_scheduled_task_tool.execute(context=_ctx(), task_id="task_missing")
        )
    else:
        service.task_storage._tasks["task_biz"] = task
        service.execution_storage._recent["task_biz"] = recent or []
        result = asyncio.run(
            self_heal.retry_scheduled_task_tool.execute(context=_ctx(), task_id="task_biz")
        )
    assert result["success"] is False
    assert keyword in result["summary"]
    assert service.retried == []


def test_retry_redis_failure_refuses(env):
    fake_redis, service = env
    fake_redis.fail = True
    result = asyncio.run(
        self_heal.retry_scheduled_task_tool.execute(context=_ctx(), task_id="task_biz")
    )
    assert result["success"] is False
    assert "缰绳" in result["summary"]
    assert service.retried == []


class _FakeFetcher:
    def __init__(self, status="idle"):
        self.status = SimpleNamespace(value=status)


class _FakeScheduler:
    def __init__(self, fetchers):
        self.fetchers = fetchers
        self.triggered: list[str] = []

    async def run_now(self, name):
        self.triggered.append(name)


@pytest.fixture()
def fetcher_env(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(anomaly_emitter, "_get_redis", lambda: fake_redis)
    scheduler = _FakeScheduler({"air_fetcher": _FakeFetcher()})
    monkeypatch.setattr(
        "app.services.lifecycle_manager.get_fetcher_scheduler", lambda: scheduler
    )
    return fake_redis, scheduler


def test_trigger_fetcher_success(fetcher_env):
    _, scheduler = fetcher_env
    result = asyncio.run(
        self_heal.trigger_fetcher_tool.execute(context=_ctx(), fetcher_name="air_fetcher")
    )
    assert result["success"] is True
    asyncio.run(asyncio.sleep(0))
    assert scheduler.triggered == ["air_fetcher"]


def test_trigger_fetcher_guards(fetcher_env, monkeypatch):
    _, scheduler = fetcher_env
    # 调度器不可用
    monkeypatch.setattr(
        "app.services.lifecycle_manager.get_fetcher_scheduler", lambda: None
    )
    result = asyncio.run(
        self_heal.trigger_fetcher_tool.execute(context=_ctx(), fetcher_name="air_fetcher")
    )
    assert result["success"] is False and "worker" in result["summary"]
    # 不存在
    monkeypatch.setattr(
        "app.services.lifecycle_manager.get_fetcher_scheduler", lambda: scheduler
    )
    result = asyncio.run(
        self_heal.trigger_fetcher_tool.execute(context=_ctx(), fetcher_name="nope")
    )
    assert result["success"] is False and "不存在" in result["summary"]
    # 被禁用
    scheduler.fetchers["paused"] = _FakeFetcher(status="disabled")
    result = asyncio.run(
        self_heal.trigger_fetcher_tool.execute(context=_ctx(), fetcher_name="paused")
    )
    assert result["success"] is False and "禁用" in result["summary"]
    assert scheduler.triggered == []
