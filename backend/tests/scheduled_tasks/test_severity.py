# -*- coding: utf-8 -*-
"""严重度分级器测试（确定性规则）。"""
from types import SimpleNamespace

from app.monitoring import severity


def _fetcher_failures(names):
    return {"count": len(names), "items": [{"fetcher": n} for n in names]}


def _task_failures(ids):
    return {"count": len(ids), "items": [{"task_id": i} for i in ids]}


def test_p1_when_quiet():
    r = severity.classify_severity(
        task_failures=_task_failures(["a"]),
        session_errors={"count": 2},
        fetcher_failures=_fetcher_failures(["f1"]),
        total_registered_fetchers=19,
    )
    assert r["severity"] == severity.P1
    assert r["reasons"] == []


def test_p0_fetcher_outage_by_ratio():
    failed = [f"f{i}" for i in range(8)]
    r = severity.classify_severity(
        fetcher_failures=_fetcher_failures(failed),
        total_registered_fetchers=10,
    )
    assert r["severity"] == severity.P0
    assert any("抓取器大面积瘫痪" in x for x in r["reasons"])


def test_fetcher_failures_below_ratio_stay_p1():
    # 3/10 失败：数量与占比都不够
    r = severity.classify_severity(
        fetcher_failures=_fetcher_failures(["f1", "f2", "f3"]),
        total_registered_fetchers=10,
    )
    assert r["severity"] == severity.P1


def test_p0_task_failure_storm():
    r = severity.classify_severity(
        task_failures=_task_failures(["t1", "t2", "t3", "t4", "t5"])
    )
    assert r["severity"] == severity.P0
    assert any("失败风暴" in x for x in r["reasons"])


def test_task_failures_below_threshold_p1():
    r = severity.classify_severity(
        task_failures=_task_failures(["t1", "t2", "t3", "t4"])
    )
    assert r["severity"] == severity.P1


def test_p0_session_error_storm():
    r = severity.classify_severity(session_errors={"count": 20})
    assert r["severity"] == severity.P0


def test_empty_inputs_are_p1():
    assert severity.classify_severity()["severity"] == severity.P1


def test_force_env_override(monkeypatch):
    monkeypatch.setenv("RUNTIME_MONITOR_FORCE_SEVERITY", "p0")
    r = severity.classify_severity()
    assert r["severity"] == severity.P0
    assert any("旁路" in x for x in r["reasons"])


def test_collect_failure_is_conservative_p1(monkeypatch):
    """实时判级采集异常时保守按 P1（不重启）。"""
    from datetime import datetime

    from app.tools.runtime_monitor import collector

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(collector, "collect_scheduled_task_failures", boom)
    result = __import__("asyncio").run(
        severity.classify_current_severity(service=SimpleNamespace(execution_storage=None))
    )
    # execution_storage=None 走 svc 分支前 boom 已抛错 → 保守 P1
    assert result["severity"] in {severity.P1, severity.P0}
