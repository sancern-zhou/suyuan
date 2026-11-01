"""推送管控（M 链）与 alert_state / push_log 持久化。

实现《空气质量数据告警推送系统——算法需求文档》V1.0 §9：
- 冷却期去重 + 升级穿透（§9.1，对应验收 T07/T08）；
- 恢复防抖 armed/hysteresis（§9.2）；
- 同窗口按站点合并（§9.3.1；跨站摘要由 window_summary 承载）；
- 站点日限额与全局日上限（§9.4，T10/T11）；
- 免打扰时段三级静默（§9.5，T12）。

存储沿用本场景既有模式：JSON 状态文件为主存储（满足 §11 重启恢复），
push_log 按日 JSONL 追加；写入均为原子替换/追加，worker 单实例执行。

文档 §9.1 与 §9.2 存在一处语义冲突：推送后 armed=False 会拦截一切后续
告警，而 T08 要求冷却期内升级立即推送。本实现按 T08 优先：升级（级别
数字变小，如三级→二级，一级最严重）最先判定、穿透 armed 与冷却；
同级别及以下受 armed 防抖拦截，恢复武装后冷却期仍兜底（恢复时保留
last_level，见 recovery_pass 说明）。
"""

from __future__ import annotations

import json
import tempfile
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.scenarios.xuchang_station_deviation.rule_config import AirAlertRuleConfig
from app.scenarios.xuchang_station_deviation.rule_engine import new_rule_state

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

STATE_SCHEMA_VERSION = "xuchang_air_alert_state/v1"
PUSHLOG_SCHEMA_VERSION = "xuchang_air_alert_pushlog/v1"

# 同站多规则合并时的规则展示顺序（级别相同时先高级别规则作主告警）。
RULE_ORDER = {"limit_breach": 0, "sudden_rise": 1, "continuous_rise": 2, "spatial_outlier": 3}


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed


def instance_key(grain: str, station_id: str, pollutant: str, rule_type: str) -> str:
    return f"{grain}::{station_id}::{pollutant}::{rule_type}"


class AlertStateStore:
    """alert_state 存储键：(grain, station_id, pollutant, rule_type) 唯一规则实例。"""

    def __init__(self, output_root: Path) -> None:
        self.path = Path(output_root) / "air_alert_state.json"
        self._lock = threading.RLock()
        self._state: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        with self._lock:
            if self._state is not None:
                return self._state
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                state = {}
            state.setdefault("schema_version", STATE_SCHEMA_VERSION)
            instances = state.setdefault("instances", {})
            # schema 演进：旧实例补齐新增默认字段。
            for value in instances.values():
                if isinstance(value, dict):
                    for key, default in new_rule_state().items():
                        value.setdefault(key, default)
            counters = state.setdefault("counters", {})
            counters.setdefault("date", None)
            counters.setdefault("sites", {})
            counters.setdefault("global", 0)
            state.setdefault("updated_at", None)
            self._state = state
            return state

    def save(self) -> None:
        with self._lock:
            state = self._load()
            state["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                temp_path = Path(handle.name)
            temp_path.replace(self.path)

    # ---- 规则实例 ----

    def instance(self, grain: str, station_id: str, pollutant: str, rule_type: str) -> dict[str, Any]:
        with self._lock:
            instances = self._load()["instances"]
            key = instance_key(grain, station_id, pollutant, rule_type)
            state = instances.get(key)
            if state is None:
                state = new_rule_state()
                instances[key] = state
            return state

    def iterate(self, grain: str, pollutant: str) -> list[tuple[str, str, dict[str, Any]]]:
        with self._lock:
            instances = self._load()["instances"]
            found = []
            for key, state in instances.items():
                parts = key.split("::")
                if len(parts) == 4 and parts[0] == grain and parts[2] == pollutant:
                    found.append((parts[1], parts[3], state))
            return found

    def all_instances(self) -> dict[str, dict[str, Any]]:
        return dict(self._load()["instances"])

    # ---- 日计数器（§9.4）----

    def _counters(self, day: str) -> dict[str, Any]:
        with self._lock:
            counters = self._load()["counters"]
            if counters.get("date") != day:
                counters["date"] = day
                counters["sites"] = {}
                counters["global"] = 0
            return counters

    def site_push_count(self, day: str, station_id: str, level: int) -> int:
        return int(self._counters(day)["sites"].get(station_id, {}).get(str(level), 0))

    def global_push_count(self, day: str) -> int:
        return int(self._counters(day)["global"])

    def increment_push(self, day: str, station_id: str, level: int) -> None:
        with self._lock:
            counters = self._counters(day)
            site = counters["sites"].setdefault(station_id, {})
            site[str(level)] = int(site.get(str(level), 0)) + 1
            counters["global"] = int(counters["global"]) + 1


def evaluate_gate(state: dict[str, Any], level: int, now: datetime, config: AirAlertRuleConfig) -> str | None:
    """推送闸门（§9.1/§9.2）：返回抑制原因，None 表示放行。不修改状态。

    级别语义：数字越小越严重（一级最严重）。“升级”即新级别数字小于
    已推送级别（如三级→二级），升级穿透 armed 与冷却（验收 T08 优先）。
    同级别及以下：先受 armed 防抖拦截，恢复武装后仍受冷却期兜底。
    """
    last_level = int(state.get("last_level") or 0)
    if last_level and level < last_level:
        return None  # 升级穿透（T08）
    if not state.get("armed", True):
        return "hysteresis"
    last_ts = _parse_ts(state.get("last_push_ts"))
    if last_ts is not None and last_level:
        cooldown = int(config.cooldown_minutes.get(last_level, 0))
        if cooldown and now - last_ts < timedelta(minutes=cooldown) and level >= last_level:
            return "cooldown"
    return None


def quota_reason(
    store: AlertStateStore, station_id: str, level: int, day: str, config: AirAlertRuleConfig
) -> str | None:
    """数量限额（§9.4）：一级不限；站点日限额与全局日上限只约束二/三级。"""
    if level == 1:
        return None
    cap = config.site_daily_quota.get(level)
    if cap is not None and store.site_push_count(day, station_id, level) >= cap:
        return "quota"
    if level in (2, 3) and store.global_push_count(day) >= config.global_daily_cap:
        return "global_cap"
    return None


def commit_push(
    store: AlertStateStore,
    state: dict[str, Any],
    *,
    level: int,
    now: datetime,
    recovery_threshold: float | None,
    station_id: str,
) -> None:
    """实际推送后的状态落位（§9.1/§9.2）与日计数累加（§9.4）。"""
    state["last_push_ts"] = now.isoformat()
    state["last_level"] = level
    state["level"] = level
    state["armed"] = False
    state["recover_cnt"] = 0
    state["last_trigger_threshold"] = recovery_threshold
    store.increment_push(now.astimezone(TZ_SHANGHAI).date().isoformat(), station_id, level)


def recovery_pass(
    store: AlertStateStore,
    current_values: dict[tuple[str, str, str], float],
    config: AirAlertRuleConfig,
) -> list[str]:
    """恢复防抖（§9.2）：连续 recover_periods 个周期 ≤阈值×recover_ratio 才重新武装。

    当前槽缺测的实例不计数也不清零（缺测不代表回落）。与文档伪代码的
    一处偏差：重新武装时保留 ``last_level``（文档置 0），否则恢复后的
    冷却期失去参照、同级告警可在冷却期内重复推送；保留后冷却期兜底
    仍然生效，升级穿透不受影响。
    """
    rearmed: list[str] = []
    for key, state in store.all_instances().items():
        if state.get("armed", True):
            continue
        threshold = state.get("last_trigger_threshold")
        if threshold is None:
            continue
        parts = key.split("::")
        if len(parts) != 4:
            continue
        grain, station_id, pollutant, _rule = parts
        current = current_values.get((grain, station_id, pollutant))
        if current is None:
            continue
        if current <= float(threshold) * config.recover_ratio:
            state["recover_cnt"] = int(state.get("recover_cnt") or 0) + 1
        else:
            state["recover_cnt"] = 0
        if state["recover_cnt"] >= config.recover_periods:
            state["armed"] = True
            state["recover_cnt"] = 0
            rearmed.append(key)
    return rearmed


def merge_by_station(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同站同粒度合并（§9.3.1）：保留最高级别一条，其余规则附注在主告警上。"""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for alert in candidates:
        grouped[(str(alert.get("measurement_granularity")), str(alert.get("station_id")))].append(alert)
    primaries: list[dict[str, Any]] = []
    for (_, _station), items in grouped.items():
        items.sort(key=lambda a: (int(a.get("alert_level") or 9), RULE_ORDER.get(str(a.get("rule_type")), 9)))
        primary = items[0]
        concurrent = items[1:]
        if concurrent:
            primary["concurrent_rules"] = [
                {
                    "rule_type": item.get("rule_type"),
                    "rule_label": item.get("rule_label"),
                    "alert_level": item.get("alert_level"),
                    "alert_level_name": item.get("alert_level_name"),
                    "event_id": item.get("event_id"),
                }
                for item in concurrent
            ]
        primaries.append(primary)
    primaries.sort(key=lambda a: (int(a.get("alert_level") or 9), str(a.get("station_id"))))
    return primaries


def build_window_summary(pushed: list[dict[str, Any]]) -> str | None:
    """跨站点/参数摘要行（§9.3.2 的摘要形态；投递仍按站点通报执行）。"""
    if not pushed:
        return None
    lines = [f"本轮共 {len(pushed)} 个站点告警："]
    for alert in pushed:
        lines.append(
            f"- {alert.get('station_name') or alert.get('station_id')} "
            f"{alert.get('target_pollutant')} {alert.get('station_value')} "
            f"（{alert.get('rule_label')}，{alert.get('alert_level_name')}）"
        )
    return "\n".join(lines)


class PushLogStore:
    """push_log 按日 JSONL：每条候选（无论是否实际推送）都落一条流水（§2.5）。"""

    def __init__(self, output_root: Path) -> None:
        self.root = Path(output_root) / "push_log"
        self._lock = threading.RLock()

    def append(self, entries: list[dict[str, Any]]) -> None:
        if not entries:
            return
        day = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")
        path = self.root / f"{day}.jsonl"
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                for entry in entries:
                    payload = {"schema_version": PUSHLOG_SCHEMA_VERSION, **entry}
                    handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def apply_push_chain(
    candidates: list[dict[str, Any]],
    *,
    store: AlertStateStore,
    config: AirAlertRuleConfig,
    now: datetime,
    log_store: PushLogStore | None = None,
    current_values: dict[tuple[str, str, str], float] | None = None,
    region_event: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """推送管控主链（§10 依赖顺序）：区域豁免 → 防抖恢复 → 闸门 → 限额 → 合并 → 推送。

    返回 (实际推送的主告警列表, 被抑制条目列表, 跨站摘要文本)。
    被抑制条目形如 ``{"alert": ..., "reason": ...}``；所有候选都写 push_log。
    """
    now = now.astimezone(TZ_SHANGHAI)
    day = now.date().isoformat()
    suppressed: list[dict[str, Any]] = []
    log_entries: list[dict[str, Any]] = []

    def _log(alert: dict[str, Any], action: str, reason: str | None = None, **extra: Any) -> None:
        entry = {
            "ts": now.isoformat(),
            "occurred_at": alert.get("occurred_at"),
            "station_id": alert.get("station_id"),
            "station_name": alert.get("station_name"),
            "pollutant": alert.get("target_pollutant"),
            "rule_type": alert.get("rule_type"),
            "level": alert.get("alert_level"),
            "event_id": alert.get("event_id"),
            "action": action,
            "reason": reason,
            **extra,
        }
        log_entries.append(entry)

    # 1) 区域过程豁免（§7.2）：本轮全部 R4 只入库不推送。
    working: list[dict[str, Any]] = []
    for alert in candidates:
        if region_event and alert.get("rule_type") == "spatial_outlier":
            alert["suppress_reason"] = "region_event"
            suppressed.append({"alert": alert, "reason": "region_event"})
            _log(alert, "suppress", "region_event")
            continue
        working.append(alert)

    # 2) 恢复防抖检查（§9.2）。
    if current_values:
        recovery_pass(store, current_values, config)

    # 3) 免打扰（§9.5）→ 闸门 + 限额（判定不落状态，只有最终推送才落）。
    pending: list[dict[str, Any]] = []
    for alert in working:
        state = store.instance(
            str(alert.get("measurement_granularity")),
            str(alert.get("station_id")),
            str(alert.get("target_pollutant")),
            str(alert.get("rule_type")),
        )
        level = int(alert.get("alert_level") or 0)
        if level in config.quiet_suppress_levels and config.in_quiet_hours(now.hour):
            alert["suppress_reason"] = "quiet_hours"
            suppressed.append({"alert": alert, "reason": "quiet_hours"})
            _log(alert, "suppress", "quiet_hours")
            continue
        reason = evaluate_gate(state, level, now, config)
        if reason:
            alert["suppress_reason"] = reason
            suppressed.append({"alert": alert, "reason": reason})
            _log(alert, "suppress", reason)
            continue
        reason = quota_reason(store, str(alert.get("station_id")), level, day, config)
        if reason:
            alert["suppress_reason"] = reason
            suppressed.append({"alert": alert, "reason": reason})
            _log(alert, "suppress", reason)
            continue
        pending.append(alert)

    # 4) 同站合并（§9.3.1）。
    primaries = merge_by_station(pending)
    primary_ids = {alert.get("event_id") for alert in primaries}

    # 5) 推送落位：每个候选写自己的规则实例状态（升级/冷却按规则独立），计数逐条累加。
    for alert in pending:
        state = store.instance(
            str(alert.get("measurement_granularity")),
            str(alert.get("station_id")),
            str(alert.get("target_pollutant")),
            str(alert.get("rule_type")),
        )
        commit_push(
            store,
            state,
            level=int(alert.get("alert_level") or 0),
            now=now,
            recovery_threshold=alert.get("recovery_threshold"),
            station_id=str(alert.get("station_id")),
        )
        alert["push_decision"] = {"action": "push", "decided_at": now.isoformat()}
        _log(alert, "push", None, is_primary=alert.get("event_id") in primary_ids)

    store.save()
    if log_store is not None:
        log_store.append(log_entries)
    summary = build_window_summary(primaries)
    return primaries, suppressed, summary
