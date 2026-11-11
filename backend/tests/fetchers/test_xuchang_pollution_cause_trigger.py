"""④污染原因分析触发抓取器单元测试：评估规则、幂等、事件发布。"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.fetchers import xuchang_pollution_cause_trigger as trigger
from app.scenarios.xuchang_pollution_cause import constants


def _rows(mapping: dict[str, float]) -> list[dict[str, object]]:
    return [{"city": city, "pm25": value} for city, value in mapping.items()]


TRIGGER_ROWS = _rows({
    "许昌市": 96.0, "郑州市": 80.0, "开封市": 70.0,
    "平顶山市": 75.0, "漯河市": 65.0, "周口市": 80.0,
    "洛阳市": 40.0,
})

BELOW_ROWS = _rows({
    "许昌市": 76.0, "郑州市": 80.0, "开封市": 70.0,
    "平顶山市": 75.0, "漯河市": 65.0, "周口市": 80.0,
})


def test_evaluate_trigger_triggered_above_threshold():
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), TRIGGER_ROWS, streak_days=1)
    # 均值 (80+70+75+65+80)/5 = 74 → 偏差约 29.7% ≥ 20% 触发
    assert evidence["neighbor_mean_pm25"] == 74.0
    assert evidence["deviation_percent"] == pytest.approx(29.7, abs=0.2)
    assert evidence["triggered"] is True
    assert evidence["streak_days"] == 2
    # 本数据集内许昌浓度最高，排第 1
    assert evidence["city_rank"] == 1
    assert evidence["city_rows"][0]["city"] == "许昌市"
    neighbor_flags = {
        row["city"]: (row["is_neighbor"], row["is_xuchang"]) for row in evidence["city_rows"]
    }
    assert neighbor_flags["许昌市"] == (False, True)
    assert neighbor_flags["郑州市"] == (True, False)
    assert neighbor_flags["洛阳市"] == (False, False)


def test_evaluate_trigger_below_threshold():
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), BELOW_ROWS)
    assert evidence["triggered"] is False
    assert evidence["streak_days"] == 0


def test_evaluate_trigger_missing_neighbors():
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), _rows({"许昌市": 60.0}))
    assert evidence["triggered"] is False
    assert evidence["neighbor_mean_pm25"] is None
    assert evidence["city_rows"][0]["is_xuchang"] is True


def test_read_streak_days_counts_consecutive_files(tmp_path):
    base = tmp_path / "xuchang_pollution_cause"
    for offset, triggered in ((1, True), (2, True), (3, False)):
        day = date(2026, 11, 10) - timedelta(days=offset)
        directory = base / f"{day:%Y%m%d}"
        directory.mkdir(parents=True)
        (directory / "trigger-evidence.json").write_text(
            json.dumps({"triggered": triggered}), encoding="utf-8"
        )
    assert trigger.read_streak_days(base, date(2026, 11, 10)) == 2


def test_city_matches_suffix_insensitive():
    assert trigger._city_matches("郑州市", "郑州市")
    assert trigger._city_matches("郑州", "郑州市")
    assert not trigger._city_matches("郑州市", "开封市")


class _FakeTaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event):
        self.events.append(event)


@pytest.fixture()
def patched_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(trigger, "get_data_registry", lambda: tmp_path)
    return tmp_path


def _patch_service(monkeypatch) -> _FakeTaskService:
    import app.scheduled_tasks as scheduled_tasks_module

    service = _FakeTaskService()
    monkeypatch.setattr(
        scheduled_tasks_module, "get_scheduled_task_service", lambda: service
    )
    return service


def test_fetch_and_store_publishes_event_once(patched_registry, monkeypatch):
    now = datetime(2026, 11, 11, 7, 30)
    monkeypatch.setattr(
        trigger, "load_city_daily_rows",
        lambda target_date: (TRIGGER_ROWS, "ssfb_city_day"),
    )
    service = _patch_service(monkeypatch)
    fetcher = trigger.XuchangPollutionCauseTriggerFetcher(now_factory=lambda: now)

    summary = asyncio.run(fetcher.fetch_and_store())
    assert summary["status"] == "triggered"
    assert summary["event_published"] is True
    assert len(service.events) == 1
    event = service.events[0]
    assert event.event_id == "xuchang-pollution-cause-20261110"
    assert event.event_type == constants.EVENT_TYPE
    assert event.attributes["target_date"] == "2026-11-10"
    assert event.payload["evidence_package_path"]
    assert event.payload["triggered"] is True

    # 幂等：证据文件已存在，直接跳过且不再发事件
    summary2 = asyncio.run(fetcher.fetch_and_store())
    assert summary2["status"] == "already_evaluated"
    assert len(service.events) == 1

    evidence_path = (
        patched_registry / "xuchang_pollution_cause" / "20261110" / "trigger-evidence.json"
    )
    assert evidence_path.exists()
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["triggered"] is True


def test_fetch_and_store_below_threshold_no_event(patched_registry, monkeypatch):
    now = datetime(2026, 11, 11, 7, 30)
    monkeypatch.setattr(
        trigger, "load_city_daily_rows",
        lambda target_date: (BELOW_ROWS, "ssfb_city_day"),
    )
    service = _patch_service(monkeypatch)
    fetcher = trigger.XuchangPollutionCauseTriggerFetcher(now_factory=lambda: now)

    summary = asyncio.run(fetcher.fetch_and_store())
    assert summary["status"] == "below_threshold"
    assert summary["event_published"] is False
    assert service.events == []


def test_no_data_day_skips(patched_registry, monkeypatch):
    now = datetime(2026, 11, 11, 7, 30)
    monkeypatch.setattr(
        trigger, "load_city_daily_rows", lambda target_date: ([], "ssfb_city_day")
    )
    fetcher = trigger.XuchangPollutionCauseTriggerFetcher(now_factory=lambda: now)
    summary = asyncio.run(fetcher.fetch_and_store())
    assert summary["status"] == "no_data"


def test_streak_carried_into_evidence(patched_registry, monkeypatch):
    """前一日证据标记触发时，今日评估应带出连续天数（前一日+当日）。"""
    now = datetime(2026, 11, 13, 7, 30)  # 评估目标日 = 2026-11-12
    previous_dir = patched_registry / "xuchang_pollution_cause" / "20261111"
    previous_dir.mkdir(parents=True)
    (previous_dir / "trigger-evidence.json").write_text(
        json.dumps({"triggered": True}), encoding="utf-8"
    )
    monkeypatch.setattr(
        trigger, "load_city_daily_rows",
        lambda target_date: (TRIGGER_ROWS, "ssfb_city_day"),
    )
    fetcher = trigger.XuchangPollutionCauseTriggerFetcher(now_factory=lambda: now)
    summary = asyncio.run(fetcher.fetch_and_store())
    assert summary["streak_days"] == 2
