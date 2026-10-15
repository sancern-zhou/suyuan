# -*- coding: utf-8 -*-
"""LLM 失败小时桶计数器测试（fake Redis）。"""
import asyncio

import pytest

from app.services import llm_failure_counter
from app.services.llm_failover import LLMFailure, mark_provider_cooldown


class _FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def hincrby(self, key, field, amount=1):
        self._ops.append(("hincrby", key, field, amount))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self):
        for op in self._ops:
            if op[0] == "hincrby":
                _, key, field, amount = op
                self._store.setdefault(key, {})
                self._store[key][field] = int(self._store[key].get(field, 0)) + amount
            elif op[0] == "expire":
                self._store.setdefault(f"__ttl__{op[1]}", op[2])
        self._ops = []
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.fail = False

    def pipeline(self, transaction=True):
        if self.fail:
            raise ConnectionError("redis down")
        return _FakePipeline(self.store)

    async def hgetall(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return dict(self.store.get(key, {}))


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(llm_failure_counter, "_get_redis", lambda: fake)
    return fake


def test_record_and_read_buckets(fake_redis):
    asyncio.run(llm_failure_counter.record_llm_failure("p1", "rate_limit"))
    asyncio.run(llm_failure_counter.record_llm_failure("p1", "rate_limit"))
    asyncio.run(llm_failure_counter.record_llm_failure("p2", "timeout"))

    all_buckets = asyncio.run(llm_failure_counter.read_llm_failure_buckets(hours=2))

    assert all_buckets
    total = sum(bucket.get("total", 0) for bucket in all_buckets.values())
    assert total == 3
    assert any(
        fields.get("p1:rate_limit") == 2 for fields in all_buckets.values()
    )
    assert any(
        fields.get("p2:timeout") == 1 for fields in all_buckets.values()
    )


def test_record_silent_when_redis_down(fake_redis):
    fake_redis.fail = True
    # 不抛异常即通过（旁路计数不放大故障）
    asyncio.run(llm_failure_counter.record_llm_failure("p1", "rate_limit"))
    assert asyncio.run(llm_failure_counter.read_llm_failure_buckets(hours=1)) == {}


def test_mark_provider_cooldown_records_counter(fake_redis, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "llm_failover_cooldown_seconds", 60, raising=False)

    async def _scenario():
        # 生产中冷却标记都发生在 async 上下文里，计数通过 create_task 旁路执行。
        mark_provider_cooldown(
            "p1", LLMFailure("rate_limit", 429, None, "too many requests")
        )
        await asyncio.sleep(0.1)

    asyncio.run(_scenario())

    totals = [
        int(fields.get("total") or 0)
        for key, fields in fake_redis.store.items()
        if not key.startswith("__ttl__")
    ]
    assert sum(totals) == 1
