# -*- coding: utf-8 -*-
"""Fetcher 运行留痕（JSONL）测试。"""
from datetime import datetime, timedelta

from app.fetchers.base import run_log


def test_record_and_read_roundtrip(tmp_path, monkeypatch):
    log_path = tmp_path / "fetcher_runs.jsonl"
    monkeypatch.setattr(run_log, "run_log_path", lambda: log_path)

    started = datetime(2026, 10, 15, 7, 0, 0)
    run_log.record_fetcher_run(
        fetcher="f1",
        started_at=started,
        finished_at=started + timedelta(seconds=30),
        status="success",
    )
    run_log.record_fetcher_run(
        fetcher="f2",
        started_at=started + timedelta(minutes=5),
        finished_at=started + timedelta(minutes=6),
        status="failed",
        error="boom " * 200,  # 超长错误被截断
    )

    records = run_log.read_recent_runs()
    assert [r["fetcher"] for r in records] == ["f2", "f1"]  # 新→旧
    assert records[0]["status"] == "failed"
    assert len(records[0]["error"]) <= 500
    assert records[1]["error"] is None


def test_read_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run_log, "run_log_path", lambda: tmp_path / "missing.jsonl"
    )
    assert run_log.read_recent_runs() == []


def test_trim_keeps_recent_records(tmp_path, monkeypatch):
    log_path = tmp_path / "fetcher_runs.jsonl"
    monkeypatch.setattr(run_log, "run_log_path", lambda: log_path)
    monkeypatch.setattr(run_log, "_MAX_FILE_BYTES", 1)  # 强制每次写入都触发检查
    monkeypatch.setattr(run_log, "_KEEP_RECORDS", 3)

    base = datetime(2026, 10, 15, 0, 0, 0)
    for index in range(6):
        run_log.record_fetcher_run(
            fetcher=f"f{index}",
            started_at=base + timedelta(minutes=index),
            finished_at=base + timedelta(minutes=index, seconds=10),
            status="success",
        )

    records = run_log.read_recent_runs()
    assert [r["fetcher"] for r in records] == ["f5", "f4", "f3"]


def test_record_failure_does_not_raise(tmp_path, monkeypatch):
    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(run_log, "run_log_path", _boom)
    run_log.record_fetcher_run(  # 不抛异常即通过
        fetcher="f1",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        status="success",
    )
