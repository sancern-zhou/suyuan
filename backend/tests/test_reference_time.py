"""Tests for the agent reference-time freeze (AGENT_TIME_FREEZE_DATE)."""

from __future__ import annotations

from datetime import datetime

from app.utils.reference_time import (
    FREEZE_DATE_ENV,
    reference_freeze_date,
    reference_now,
)


def test_reference_now_unfrozen_follows_real_clock(monkeypatch):
    monkeypatch.delenv(FREEZE_DATE_ENV, raising=False)
    value = reference_now()
    real = datetime.now().astimezone()
    assert abs((real - value).total_seconds()) < 1
    assert value.tzinfo is not None


def test_reference_freeze_invalid_date_is_ignored(monkeypatch):
    monkeypatch.setenv(FREEZE_DATE_ENV, "2026-13-99")
    assert reference_freeze_date() is None
    value = reference_now()
    assert value.date() == datetime.now().astimezone().date()


def test_reference_now_pins_date_but_keeps_real_clock(monkeypatch):
    monkeypatch.setenv(FREEZE_DATE_ENV, "2026-09-16")
    value = reference_now()
    real = datetime.now().astimezone()
    assert (value.year, value.month, value.day) == (2026, 9, 16)
    assert (value.hour, value.minute) == (real.hour, real.minute)
    assert value.utcoffset() == real.utcoffset()
    assert value.strftime("%Y-%m-%d %H:%M:%S").startswith("2026-09-16")
