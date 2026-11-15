# -*- coding: utf-8 -*-
"""服务级操作工具测试（P0 硬门禁 / 缰绳 / 守护进程交互）。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.monitoring import severity
from app.tools.runtime_monitor import service_ops


def _ctx():
    return SimpleNamespace(
        scheduled_task_context={"task_id": "task_runtime_monitor_realtime", "execution_id": "e1"}
    )


@pytest.fixture()
def p0_verdict(monkeypatch):
    async def fake():
        return {"severity": "p0", "reasons": ["抓取器大面积瘫痪：6 个抓取器失败"]}

    monkeypatch.setattr(severity, "classify_current_severity", fake)


@pytest.fixture()
def redis_ok(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.store:
                return None
            self.store[key] = value
            return True

        async def incr(self, key):
            self.store[key] = int(self.store.get(key, 0)) + 1
            return self.store[key]

        async def expire(self, key, ttl):
            return True

    fake = FakeRedis()
    monkeypatch.setattr(service_ops, "_check_restart_reins", _make_reins(fake))
    return fake


def _make_reins(fake):
    async def reins(service):
        acquired = await fake.set(
            f"cd:{service}", "1", nx=True, ex=service_ops.RESTART_COOLDOWN_SECONDS
        )
        if not acquired:
            return "冷却"
        return None

    return reins


def test_gate_rejects_non_scheduled_context():
    r = asyncio.run(
        service_ops.restart_service_tool.execute(
            context=None, service="web", reason="test"
        )
    )
    assert r["success"] is False
    assert "定时任务" in r["summary"]


def test_restart_denied_when_not_p0(p0_verdict, monkeypatch):
    async def p1():
        return {"severity": "p1", "reasons": []}

    monkeypatch.setattr(severity, "classify_current_severity", p1)
    r = asyncio.run(
        service_ops.restart_service_tool.execute(
            context=_ctx(), service="web", reason="看起来很糟"
        )
    )
    assert r["success"] is False
    assert "未达 P0" in r["summary"]


def test_restart_denied_without_daemon_token(p0_verdict, redis_ok, monkeypatch):
    monkeypatch.setattr(service_ops, "_daemon_endpoint", lambda: ("http://x", ""))
    r = asyncio.run(
        service_ops.restart_service_tool.execute(
            context=_ctx(), service="web", reason="P0 修复完成"
        )
    )
    assert r["success"] is False
    assert "未配置" in r["summary"]


def test_restart_success_with_p0_and_daemon(p0_verdict, redis_ok, monkeypatch):
    monkeypatch.setattr(service_ops, "_daemon_endpoint", lambda: ("http://x", "tok"))

    def fake_post(base, token, path, payload, timeout=240):
        assert path == "/restart" and token == "tok"
        assert payload["service"] == "web"
        return {
            "success": True,
            "results": [{"service": "web", "healthy": True, "rolled_back": False}],
        }

    monkeypatch.setattr(service_ops, "_post", fake_post)
    r = asyncio.run(
        service_ops.restart_service_tool.execute(
            context=_ctx(), service="web", reason="P0：抓取器全挂，已修复"
        )
    )
    assert r["success"] is True
    assert r["data"]["healthy"] is True
    assert "P0 依据" in r["summary"]


def test_restart_reports_unhealthy_and_rollback(p0_verdict, redis_ok, monkeypatch):
    monkeypatch.setattr(service_ops, "_daemon_endpoint", lambda: ("http://x", "tok"))

    def fake_post(base, token, path, payload, timeout=240):
        return {
            "success": True,
            "results": [{"service": "worker", "healthy": False, "rolled_back": True}],
        }

    monkeypatch.setattr(service_ops, "_post", fake_post)
    r = asyncio.run(
        service_ops.restart_service_tool.execute(
            context=_ctx(), service="worker", reason="P0 修复后重启"
        )
    )
    assert r["success"] is True
    assert r["data"]["healthy"] is False
    assert "健康核实未通过" in r["summary"] and "回滚" in r["summary"]


def test_reins_cooldown_blocks_second_restart(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.store:
                return None
            self.store[key] = value
            return True

        async def incr(self, key):
            self.store[key] = int(self.store.get(key, 0)) + 1
            return self.store[key]

        async def expire(self, key, ttl):
            return True

    from app.monitoring import anomaly_emitter

    fake = FakeRedis()
    monkeypatch.setattr(anomaly_emitter, "_get_redis", lambda: fake)
    first = asyncio.run(service_ops._check_restart_reins("web"))
    second = asyncio.run(service_ops._check_restart_reins("web"))
    assert first is None
    assert second is not None and "冷却" in second
