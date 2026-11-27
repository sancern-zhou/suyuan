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

# 许昌 55 < 60（normal 档 30%）；相邻五市均值 42.4 → 偏差 29.7%，
# 超过 20% 但未达 30%，按新规则不触发
NORMAL_TIER_BELOW_ROWS = _rows({
    "许昌市": 55.0, "郑州市": 40.0, "开封市": 45.0,
    "平顶山市": 42.0, "漯河市": 44.0, "周口市": 41.0,
})

NORMAL_TIER_TRIGGER_ROWS = _rows({
    "许昌市": 58.0, "郑州市": 40.0, "开封市": 45.0,
    "平顶山市": 42.0, "漯河市": 44.0, "周口市": 41.0,
})


def test_resolve_threshold_tier():
    # 轻度污染及以上（新标准日均 ≥ 60）：20% 档
    assert trigger.resolve_threshold_tier(60.0) == (
        constants.TRIGGER_RATIO_THRESHOLD_LIGHT_POLLUTION, "light_pollution_or_above"
    )
    assert trigger.resolve_threshold_tier(96.0)[1] == "light_pollution_or_above"
    # 未达界限：默认 30% 档
    assert trigger.resolve_threshold_tier(59.9) == (
        constants.TRIGGER_RATIO_THRESHOLD, "normal"
    )
    assert trigger.resolve_threshold_tier(None) == (
        constants.TRIGGER_RATIO_THRESHOLD, "normal"
    )


def test_evaluate_trigger_triggered_above_threshold():
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), TRIGGER_ROWS, streak_days=1)
    # 均值 (80+70+75+65+80)/5 = 74 → 偏差约 29.7%；许昌 96 ≥ 60 属轻度
    # 污染及以上，按 20% 档判定 → 触发
    assert evidence["neighbor_mean_pm25"] == 74.0
    assert evidence["deviation_percent"] == pytest.approx(29.7, abs=0.2)
    assert evidence["triggered"] is True
    assert evidence["pollution_level_tier"] == "light_pollution_or_above"
    assert evidence["ratio_threshold"] == pytest.approx(0.20)
    assert evidence["default_ratio_threshold"] == pytest.approx(0.30)
    assert evidence["light_pollution_pm25_limit"] == 60.0
    assert "30%以上" in evidence["rule_description"]
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


def test_evaluate_trigger_normal_tier_between_thresholds_not_triggered():
    """许昌 < 60 时用 30% 档：偏差 20~30% 区间不触发（旧 20% 规则会触发）。"""
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), NORMAL_TIER_BELOW_ROWS)
    # 均值 (40+45+42+44+41)/5 = 42.4 → 偏差约 29.7%
    assert evidence["neighbor_mean_pm25"] == pytest.approx(42.4, abs=0.1)
    assert evidence["deviation_percent"] == pytest.approx(29.7, abs=0.2)
    assert evidence["pollution_level_tier"] == "normal"
    assert evidence["ratio_threshold"] == pytest.approx(0.30)
    assert evidence["triggered"] is False


def test_evaluate_trigger_normal_tier_triggered_above_30():
    """许昌 < 60 且偏差 ≥ 30%：按默认档触发。"""
    evidence = trigger.evaluate_trigger(date(2026, 11, 10), NORMAL_TIER_TRIGGER_ROWS)
    # 均值 42.4 → 偏差约 36.8%
    assert evidence["deviation_percent"] == pytest.approx(36.8, abs=0.2)
    assert evidence["pollution_level_tier"] == "normal"
    assert evidence["ratio_threshold"] == pytest.approx(0.30)
    assert evidence["triggered"] is True


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
    assert summary["pollution_level_tier"] == "light_pollution_or_above"
    assert summary["ratio_threshold"] == pytest.approx(0.20)
    assert summary["event_published"] is True
    assert len(service.events) == 1
    event = service.events[0]
    assert event.event_id == "xuchang-pollution-cause-20261110"
    assert event.event_type == constants.EVENT_TYPE
    assert event.attributes["target_date"] == "2026-11-10"
    assert event.attributes["pollution_level_tier"] == "light_pollution_or_above"
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
