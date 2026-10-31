"""配额重置自动续跑测试（schedule/scan/防循环，全 fake Redis，无外部依赖）。"""

import asyncio
import json
import time

import pytest

from app.agent.workflow import quota_resume as qr
from app.agent.workflow.quota_resume import (
    MAX_RESUME_ATTEMPTS,
    RESUME_MARGIN_SECONDS,
    scan_and_resume_due,
    schedule_quota_resume,
)


class FakeRedis:
    def __init__(self):
        self.zsets = {}
        self.hashes = {}

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    async def zrangebyscore(self, key, min_value, max_value, start=0, num=None):
        items = sorted(
            (score, member) for member, score in self.zsets.get(key, {}).items()
            if float(min_value) <= score <= float(max_value)
        )
        if num is not None:
            items = items[int(start):int(start) + int(num)]
        return [member for _, member in items]

    async def zrem(self, key, member):
        removed = self.zsets.get(key, {}).pop(member, None) is not None
        return 1 if removed else 0

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hdel(self, key, field):
        removed = self.hashes.get(key, {}).pop(field, None) is not None
        return 1 if removed else 0


class FakeStore:
    """WorkflowJobStore 形状的最小替身。"""

    def __init__(self):
        self.redis = FakeRedis()
        self.prefix = "test:workflow"
        self.enqueued = []

    async def enqueue(self, *, session_id, workflow_id, definition, snapshot):
        self.enqueued.append({"session_id": session_id, "workflow_id": workflow_id, "snapshot": snapshot})


def make_snapshot(reset_at, *, status="failed"):
    return {
        "workflow_id": "wf-1",
        "status": status,
        "quota_pause": {"reset_at": reset_at, "task_id": "air", "error": "402"},
        "definition": {"workflow_id": "wf-1", "nodes": []},
        "budget_state": {},
    }


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(qr, "get_workflow_job_store", lambda: fake)
    return fake


def patch_snapshot(monkeypatch, snapshot):
    async def loader(session_id, workflow_id):
        return snapshot
    monkeypatch.setattr(qr, "_load_workflow_snapshot", loader)


def test_schedule_writes_zset_with_margin(store):
    reset_at = time.time() + 3600
    assert asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
    zset = store.redis.zsets[f"{store.prefix}:quota_resume"]
    assert zset["s1:wf-1"] == pytest.approx(reset_at + RESUME_MARGIN_SECONDS)
    meta = json.loads(store.redis.hashes[f"{store.prefix}:quota_resume_meta"]["s1:wf-1"])
    assert meta["attempts"] == 0


def test_scan_dispatches_due_member_and_keeps_attempt_count(store, monkeypatch):
    reset_at = time.time() - 120  # 已到点（score = reset_at + 60s 余量）
    asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
    patch_snapshot(monkeypatch, make_snapshot(reset_at))

    dispatched = asyncio.run(scan_and_resume_due(store, now=time.time()))
    assert dispatched == 1
    assert len(store.enqueued) == 1
    assert store.enqueued[0]["workflow_id"] == "wf-1"
    zset = store.redis.zsets[f"{store.prefix}:quota_resume"]
    assert "s1:wf-1" not in zset
    # 同一 reset_at 再次失败时 schedule 继承 attempts=1（防循环计数）
    meta = json.loads(store.redis.hashes[f"{store.prefix}:quota_resume_meta"]["s1:wf-1"])
    assert meta["attempts"] == 1


def test_scan_reschedules_when_reset_at_changed(store, monkeypatch):
    old_reset = time.time() - 120
    new_reset = time.time() + 7200
    asyncio.run(schedule_quota_resume("s1", "wf-1", old_reset))
    patch_snapshot(monkeypatch, make_snapshot(new_reset))

    asyncio.run(scan_and_resume_due(store, now=time.time()))
    assert store.enqueued == []
    zset = store.redis.zsets[f"{store.prefix}:quota_resume"]
    assert zset["s1:wf-1"] == pytest.approx(new_reset + RESUME_MARGIN_SECONDS)
    meta = json.loads(store.redis.hashes[f"{store.prefix}:quota_resume_meta"]["s1:wf-1"])
    assert meta["reset_at"] == new_reset
    assert meta["attempts"] == 0


def test_anti_loop_caps_attempts_per_reset_at(store, monkeypatch):
    reset_at = time.time() - 120
    patch_snapshot(monkeypatch, make_snapshot(reset_at))
    for _ in range(MAX_RESUME_ATTEMPTS):
        assert asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
        asyncio.run(scan_and_resume_due(store, now=time.time()))
    # 第 MAX+1 次调度被拒绝：达到上限，留手动 resume
    assert not asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
    assert len(store.enqueued) == MAX_RESUME_ATTEMPTS


def test_scan_drops_member_when_snapshot_no_longer_quota_paused(store, monkeypatch):
    reset_at = time.time() - 120
    asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
    patch_snapshot(monkeypatch, {"workflow_id": "wf-1", "status": "failed"})

    asyncio.run(scan_and_resume_due(store, now=time.time()))
    assert store.enqueued == []
    assert "s1:wf-1" not in store.redis.zsets[f"{store.prefix}:quota_resume"]


def test_scan_drops_cancelled_or_budget_exhausted(store, monkeypatch):
    reset_at = time.time() - 120
    asyncio.run(schedule_quota_resume("s1", "wf-1", reset_at))
    patch_snapshot(monkeypatch, make_snapshot(reset_at, status="cancelled"))
    asyncio.run(scan_and_resume_due(store, now=time.time()))
    assert store.enqueued == []
    assert "s1:wf-1" not in store.redis.zsets[f"{store.prefix}:quota_resume"]


def test_scan_without_redis_returns_zero(monkeypatch):
    # Redis 不可用：fail-soft 返回 0，不抛异常
    from app.agent.workflow.jobs import get_workflow_job_store

    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(qr, "get_workflow_job_store", boom)
    assert asyncio.run(scan_and_resume_due()) == 0
    assert get_workflow_job_store  # 引用不触发
