"""持续盯守智能体的第一阶段：近阈值证据、过程状态与影子决策。

正式告警仍由既有规则和推送链决定。本模块只记录观察与 LLM 建议，
不向任何推送通道写入消息。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig
from app.scenarios.xuchang_station_deviation.rule_engine import (
    GRANULARITY_5MIN,
    hourly_levels,
    slot_of,
    valid_value,
)

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
ACTIONS = {"watch", "boundary_notice", "merge", "escalate", "recover", "close"}
WATCH_RULE = "spatial_outlier"


def _enabled() -> bool:
    return os.getenv("XUCHANG_WATCHKEEPING_SHADOW_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def collect_boundary_observations(
    rows: list[dict[str, Any]],
    *,
    target_slot: datetime,
    config: AirAlertRuleConfig,
    ratio_floor: float = 0.90,
) -> list[dict[str, Any]]:
    """输出当前槽接近 OL 门槛的事实，不改变 OL 连续槽或正式告警状态。"""
    levels = hourly_levels(
        rows, slot_of(target_slot, "hour") - timedelta(hours=1), None
    )
    observations: list[dict[str, Any]] = []
    for pollutant, column in (("PM10", "pm10"), ("SO2", "so2"), ("NO2", "no2"), ("CO", "co")):
        values: dict[str, tuple[float, dict[str, Any]]] = {}
        for row in rows:
            if row.get("data_source") != "minute":
                continue
            timestamp = row.get("data_time")
            if not isinstance(timestamp, datetime) or slot_of(timestamp, GRANULARITY_5MIN) != target_slot:
                continue
            value = valid_value(row, column)
            station_id = str(row.get("station_id") or "")
            if value is not None and station_id:
                values[station_id] = (value, row)
        for station_id, (value, row) in sorted(values.items()):
            peers = [item[0] for sid, item in values.items() if sid != station_id]
            level = levels.get((station_id, pollutant))
            if len(values) < config.min_region_stations or not peers or level is None:
                continue
            peer_mean = sum(peers) / len(peers)
            if peer_mean <= 0:
                continue
            ratio, absolute = config.thresholds(pollutant, WATCH_RULE, level)
            threshold = max(peer_mean * ratio, absolute)
            delta = value - peer_mean
            if delta <= 0 or threshold <= 0:
                continue
            threshold_ratio = delta / threshold
            if not ratio_floor <= threshold_ratio < 1.0:
                continue
            observations.append({
                "station_id": station_id,
                "station_name": row.get("name") or row.get("station_name") or station_id,
                "pollutant": pollutant,
                "occurred_at": target_slot.isoformat(),
                "station_value": value,
                "peer_mean": round(peer_mean, 3),
                "absolute_delta": round(delta, 3),
                "deviation_percent": round(delta / peer_mean * 100, 1),
                "threshold": round(threshold, 3),
                "threshold_ratio": round(threshold_ratio, 3),
                "air_quality_level": level,
                "peer_station_count": len(peers),
            })
    return observations


class WatchkeepingStore:
    """以站点×因子为过程键，原子保存跨调度轮次状态与影子决策流水。"""

    def __init__(self, output_root: Path) -> None:
        self.root = Path(output_root) / "watchkeeping"
        self.state_path = self.root / "state.json"

    def load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            state = {}
        state.setdefault("schema_version", "xuchang_watchkeeping/v1")
        state.setdefault("processes", {})
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(self.state_path)

    def append(self, entries: list[dict[str, Any]]) -> None:
        if not entries:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        day = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")
        with (self.root / f"shadow-{day}.jsonl").open("a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


class WatchkeepingAgent:
    """影子值守：LLM 建议只落日志，执行层没有边界消息推送能力。"""

    def __init__(self, output_root: Path, *, llm_service: Any = None) -> None:
        self.store = WatchkeepingStore(output_root)
        self.llm_service = llm_service

    @staticmethod
    def _load(push_log: Path, now: datetime) -> dict[str, int]:
        counts = {30: 0, 60: 0}
        path = push_log / f"{now:%Y%m%d}.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return counts
        for line in lines:
            try:
                entry = json.loads(line)
                decided = datetime.fromisoformat(entry["ts"])
                minutes = (now - decided).total_seconds() / 60
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            if entry.get("action") != "push" or minutes < 0:
                continue
            for window in counts:
                if minutes <= window:
                    counts[window] += 1
        return counts

    async def _decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "你是许昌国控站空气浓度值守员。只根据给定事实判断边界观察，不得认定正式告警。"
            "近期告警少且异常持续时可建议 boundary_notice；告警密集时可 merge 或 watch；"
            "异常持续并增强可 escalate；减弱可 recover；结束可 close。"
            "只输出 JSON：{\"action\":\"watch|boundary_notice|merge|escalate|recover|close\","
            "\"reason\":\"不超过100字的事实理由\",\"priority\":\"low|normal|high\","
            "\"next_review_minutes\":5}。不得编造气象、质控或来源结论。\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )
        if self.llm_service is None:
            from app.services.llm_service import LLMService
            self.llm_service = LLMService()
        answer = await self.llm_service.call_llm_with_json_response(prompt, max_retries=1)
        if not isinstance(answer, dict) or answer.get("action") not in ACTIONS:
            raise ValueError("invalid_watchkeeping_action")
        answer["next_review_minutes"] = 5
        answer["reason"] = str(answer.get("reason") or "")[:100]
        answer["priority"] = answer.get("priority") if answer.get("priority") in {"low", "normal", "high"} else "normal"
        return answer

    async def observe(self, result: dict[str, Any], output_root: Path) -> dict[str, Any]:
        now = datetime.fromisoformat(result["target_hour"])
        state = self.store.load()
        processes = state["processes"]
        current_keys = set()
        decisions = []
        for observation in result.get("watch_observations", []):
            key = f"{observation['station_id']}::{observation['pollutant']}"
            current_keys.add(key)
            process = processes.setdefault(key, {
                "station_id": observation["station_id"], "pollutant": observation["pollutant"],
                "status": "watching", "first_seen_at": observation["occurred_at"],
                "near_streak": 0, "decision_count": 0,
            })
            process["near_streak"] = int(process.get("near_streak") or 0) + 1
            process["last_seen_at"] = observation["occurred_at"]
            process["last_observation"] = observation
            process["status"] = "watching"
            if process["near_streak"] < 2:
                continue
            payload = {
                "observation": observation, "process": process,
                "recent_push_counts": self._load(output_root / "push_log", now),
                "shadow_only": True,
            }
            try:
                decision = await self._decide(payload)
            except Exception as exc:
                decision = {"action": "watch", "reason": "值守判断不可用，保留观察", "priority": "low", "next_review_minutes": 5}
                logger.warning("xuchang_watchkeeping_decision_failed", error_type=type(exc).__name__)
            process["decision_count"] = int(process.get("decision_count") or 0) + 1
            process["last_decision"] = decision
            decisions.append({"process_key": key, "decision": decision, "shadow": True})
        for key, process in processes.items():
            if key not in current_keys and process.get("status") == "watching":
                process["status"] = "recovering"
                process["near_streak"] = 0
                process["recovering_since"] = now.isoformat()
            elif process.get("status") == "recovering":
                try:
                    recovering_since = datetime.fromisoformat(process["recovering_since"])
                except (KeyError, ValueError, TypeError):
                    recovering_since = now
                if now - recovering_since >= timedelta(minutes=15):
                    process["status"] = "closed"
        for alert in result.get("alerts", []):
            key = f"{alert.get('station_id')}::{alert.get('target_pollutant')}"
            if key in processes:
                processes[key]["status"] = "alerted"
                processes[key]["formal_event_id"] = alert.get("event_id")
        state["updated_at"] = now.isoformat()
        self.store.save(state)
        self.store.append(decisions)
        return {"decisions": decisions, "process_count": len(processes), "shadow": True}
