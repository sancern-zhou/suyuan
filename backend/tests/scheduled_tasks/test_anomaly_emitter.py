# -*- coding: utf-8 -*-
"""运行异常事件发射器测试（fake Redis + fake 服务）。"""
import asyncio

import pytest

from app.monitoring import anomaly_emitter


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
        if self.fail:
            raise ConnectionError("redis down")
        return key in self.store

    async def delete(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.pop(key, None) is not None


class _FakeService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event, **kwargs):
        self.events.append(event)


@pytest.fixture()
def env(monkeypatch):
    fake_redis = _FakeRedis()
    fake_service = _FakeService()

    async def _fake_resolve():
        return fake_service

    monkeypatch.setattr(anomaly_emitter, "_get_redis", lambda: fake_redis)
    monkeypatch.setattr(anomaly_emitter, "_resolve_service", _fake_resolve)
    return fake_redis, fake_service


class _Task:
    def __init__(self, task_id="task_biz", name="业务任务", tags=None):
        self.task_id = task_id
        self.name = name
        self.tags = tags or []


class _Execution:
    def __init__(self, trigger_type="scheduled", status="failed", error="boom"):
        self.trigger_type = trigger_type
        self.status = status
        self.error_message = error


def test_task_failure_emits_once_then_cooldown_suppresses(env):
    _, service = env
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
    assert len(service.events) == 1
    attrs = service.events[0].attributes
    assert attrs["source"] == "scheduled_task"
    assert attrs["task_id"] == "task_biz"
    assert attrs["window_failures"] == 1
    assert service.events[0].event_type == anomaly_emitter.EVENT_TYPE

    # 冷却期内重复失败：不发射，但窗口计数继续累加
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
    assert len(service.events) == 1


def test_task_failure_cooldown_release_republishes_with_count(env):
    fake_redis, service = env
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
    # 模拟冷却期满：清掉冷却锁，保留窗口计数
    fake_redis.store.pop("monitor:evtcd:task:task_biz")
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
    assert len(service.events) == 2
    assert service.events[1].attributes["window_failures"] == 2


def test_monitor_task_and_non_scheduled_trigger_excluded(env):
    _, service = env
    monitor = _Task(task_id="task_runtime_monitor", tags=["runtime-monitor", "watchdog"])
    asyncio.run(anomaly_emitter.emit_task_failure(monitor, _Execution()))
    # 手动触发有人在场、事件触发已在链路内留痕，均不发射
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution(trigger_type="manual")))
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution(trigger_type="event")))
    assert service.events == []


def test_fetcher_single_failure_below_threshold(env):
    _, service = env
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    assert service.events == []  # 连续失败 1 次不触发


def test_fetcher_consecutive_failures_emit_and_cooldown(env):
    _, service = env
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    assert len(service.events) == 1
    attrs = service.events[0].attributes
    assert attrs["source"] == "fetcher"
    assert attrs["fetcher"] == "air_fetcher"
    assert attrs["consecutive_failures"] == 2

    # 冷却期内继续失败：不重复发射
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    assert len(service.events) == 1


def test_fetcher_success_resets_streak(env):
    _, service = env
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    asyncio.run(anomaly_emitter.reset_fetcher_streak("air_fetcher"))
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    assert service.events == []  # 计数被清零后重新从 1 数起


def test_redis_failure_degrades_silently(env):
    fake_redis, service = env
    fake_redis.fail = True
    # Redis 故障：不抛异常、不发射（宁漏勿扰，小时级巡检兜底）
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
    asyncio.run(anomaly_emitter.emit_fetcher_failure("air_fetcher", "timeout"))
    asyncio.run(anomaly_emitter.reset_fetcher_streak("air_fetcher"))
    assert service.events == []


def test_no_service_available_is_noop(env, monkeypatch):
    async def _none():
        return None

    monkeypatch.setattr(anomaly_emitter, "_resolve_service", _none)
    # web 进程无定时任务服务：静默
    asyncio.run(anomaly_emitter.emit_task_failure(_Task(), _Execution()))
