import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig
from app.scenarios.xuchang_station_deviation.watchkeeping import (
    WatchkeepingAgent,
    collect_boundary_observations,
)

TZ = ZoneInfo("Asia/Shanghai")
STATIONS = ("a", "b", "c", "d", "e", "f")


def _rows(slot: datetime, target: float, peers: float) -> list[dict]:
    rows = []
    for station in STATIONS:
        rows.append({
            "station_id": station, "name": station, "data_source": "hour",
            "data_time": slot - timedelta(hours=1), "pm10": 60,
        })
        rows.append({
            "station_id": station, "name": station, "data_source": "minute",
            "data_time": slot, "pm10": target if station == "a" else peers,
        })
    return rows


def test_collects_near_threshold_without_touching_formal_streak():
    slot = datetime(2026, 11, 21, 16, 30, tzinfo=TZ)
    observations = collect_boundary_observations(
        _rows(slot, 58, 40), target_slot=slot, config=AirAlertRuleConfig(),
    )

    assert len(observations) == 1
    item = observations[0]
    assert item["station_id"] == "a"
    assert item["absolute_delta"] == 18
    assert item["threshold"] == 20
    assert item["threshold_ratio"] == 0.9
    assert "streak_cnt" not in item


def test_excludes_formal_and_low_value_observations():
    slot = datetime(2026, 11, 21, 16, 30, tzinfo=TZ)
    config = AirAlertRuleConfig()
    assert collect_boundary_observations(_rows(slot, 60, 40), target_slot=slot, config=config) == []
    assert collect_boundary_observations(_rows(slot, 55, 40), target_slot=slot, config=config) == []


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    async def call_llm_with_json_response(self, prompt, max_retries=1):
        self.prompts.append(prompt)
        return self.answer


@pytest.mark.asyncio
async def test_shadow_agent_persists_process_and_decision_without_pushing(tmp_path):
    llm = FakeLLM({"action": "boundary_notice", "reason": "告警较少且连续接近门槛", "priority": "normal"})
    agent = WatchkeepingAgent(tmp_path, llm_service=llm)
    result = {
        "target_hour": "2026-11-21T16:35:00+08:00",
        "watch_observations": [{
            "station_id": "1012A", "station_name": "望田路111号", "pollutant": "PM10",
            "occurred_at": "2026-11-21T16:35:00+08:00", "threshold_ratio": 0.928,
        }],
        "alerts": [],
    }
    # 同一过程上一轮已观察一次，本轮才请求值守判断。
    state = agent.store.load()
    state["processes"]["1012A::PM10"] = {
        "station_id": "1012A", "pollutant": "PM10", "status": "watching",
        "first_seen_at": "2026-11-21T16:30:00+08:00", "near_streak": 1,
    }
    agent.store.save(state)

    outcome = await agent.observe(result, tmp_path)

    assert outcome["decisions"][0]["decision"]["action"] == "boundary_notice"
    assert outcome["shadow"] is True
    saved = agent.store.load()["processes"]["1012A::PM10"]
    assert saved["near_streak"] == 2
    assert saved["last_decision"]["action"] == "boundary_notice"
    log = next((tmp_path / "watchkeeping").glob("shadow-*.jsonl"))
    assert json.loads(log.read_text(encoding="utf-8"))["shadow"] is True
    assert "shadow_only" in llm.prompts[0]


@pytest.mark.asyncio
async def test_llm_failure_defaults_to_watch_and_formal_alert_remains_unchanged(tmp_path):
    class FailedLLM:
        async def call_llm_with_json_response(self, prompt, max_retries=1):
            raise RuntimeError("timeout")

    agent = WatchkeepingAgent(tmp_path, llm_service=FailedLLM())
    formal = {"station_id": "1012A", "target_pollutant": "PM10", "event_id": "formal-event"}
    result = {
        "target_hour": "2026-11-21T17:15:00+08:00",
        "watch_observations": [{
            "station_id": "1012A", "station_name": "望田路111号", "pollutant": "PM10",
            "occurred_at": "2026-11-21T17:15:00+08:00", "threshold_ratio": 0.95,
        }],
        "alerts": [formal],
    }
    state = agent.store.load()
    state["processes"]["1012A::PM10"] = {"near_streak": 1, "status": "watching"}
    agent.store.save(state)

    outcome = await agent.observe(result, tmp_path)

    assert outcome["decisions"][0]["decision"]["action"] == "watch"
    assert result["alerts"] == [formal]
    assert agent.store.load()["processes"]["1012A::PM10"]["status"] == "alerted"
    assert agent.store.load()["processes"]["1012A::PM10"]["formal_event_id"] == "formal-event"
