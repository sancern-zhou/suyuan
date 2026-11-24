"""推送管控（M 链）与 alert_state / push_log 持久化（判据修订版）。

规则总表只定义了三类规则、阈值和冷却期；本模块保留既有运营层：
恢复防抖、免打扰、日限额、同站合并，并按新口径改造：

- 单站 DS/CL/OL 按站点 + 因子共享通知冷却；窗口取最后一次实际
  推送规则的冷却期。多站 MR 独立，不读写单站共享冷却状态；
- 升级例外（#23）：污染等级升高立即再报，穿透防抖/冷却/免打扰（夜间
  升级也必须叫人），挂到首条事件上；
- 优先级排序（#24）：DS > CL > OL，同一站同一因子同一窗口按优先级逐条
  过闸门、取第一条能推送的；高优先级被拦截时低优先级可顶上，不再连坐；
- 不再有告警级别；所有状态、流水和通报只记录规则类型 + 污染等级。
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

from app.scenarios.xuchang_station_deviation.rule_config import (
    LEVEL_CODES,
    POLLUTANT_ORDER,
    AirAlertRuleConfig,
    normalize_level,
)
from app.scenarios.xuchang_station_deviation.rule_engine import new_rule_state

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

STATE_SCHEMA_VERSION = "xuchang_air_alert_state/v3"
PUSHLOG_SCHEMA_VERSION = "xuchang_air_alert_pushlog/v2"
SINGLE_STATION_RULES = frozenset({"sudden_rise", "continuous_rise", "spatial_outlier"})


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


def notification_group_key(grain: str, station_id: str, pollutant: str) -> str:
    return f"{grain}::{station_id}::{pollutant}"


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
            state.setdefault("notification_groups", {})
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

    def notification_group(self, grain: str, station_id: str, pollutant: str) -> dict[str, Any]:
        with self._lock:
            groups = self._load()["notification_groups"]
            return groups.setdefault(notification_group_key(grain, station_id, pollutant), {})

    # ---- 日计数器（按站点，不再按告警级别）----

    def _counters(self, day: str) -> dict[str, Any]:
        with self._lock:
            counters = self._load()["counters"]
            if counters.get("date") != day:
                counters["date"] = day
                counters["sites"] = {}
                counters["global"] = 0
            return counters

    def site_push_count(self, day: str, station_id: str) -> int:
        return int(self._counters(day)["sites"].get(station_id, 0))

    def global_push_count(self, day: str) -> int:
        return int(self._counters(day)["global"])

    def increment_push(self, day: str, station_id: str) -> None:
        with self._lock:
            counters = self._counters(day)
            counters["sites"][station_id] = int(counters["sites"].get(station_id, 0)) + 1
            counters["global"] = int(counters["global"]) + 1


def upgrade_info(state: dict[str, Any], air_quality_level: str | None) -> dict[str, Any]:
    """冷却期内污染等级升高：返回升级标识（#23）。"""
    current = LEVEL_CODES.get(str(air_quality_level)) if air_quality_level else None
    previous = LEVEL_CODES.get(str(state.get("last_air_level"))) if state.get("last_air_level") else None
    if current is not None and previous is not None and current > previous:
        return {
            "is_upgrade": True,
            "upgrade_from_level": state.get("last_air_level"),
            "upgrade_to_level": air_quality_level,
        }
    return {}


def evaluate_gate(
    state: dict[str, Any],
    *,
    rule_type: str,
    pollutant: str,
    air_quality_level: str | None,
    now: datetime,
    config: AirAlertRuleConfig,
) -> str | None:
    """推送闸门：升级穿透 → 防抖 → 冷却。返回抑制原因，None 表示放行。"""
    current = LEVEL_CODES.get(str(air_quality_level)) if air_quality_level else None
    previous = LEVEL_CODES.get(str(state.get("last_air_level"))) if state.get("last_air_level") else None
    if current is not None and previous is not None and current > previous:
        return None  # #23 升级例外
    if not state.get("armed", True):
        return "hysteresis"
    last_ts = _parse_ts(state.get("last_push_ts"))
    cooldown = config.cooldown_for(rule_type, pollutant)
    if last_ts is not None and cooldown and now - last_ts < timedelta(minutes=cooldown):
        return "cooldown"
    return None


def renotify_due(
    state: dict[str, Any],
    *,
    rule_type: str,
    pollutant: str,
    now: datetime,
    config: AirAlertRuleConfig,
) -> bool:
    """滞回心跳：未恢复但距上次推送已满一个冷却窗口（窗口值=规则总表
    冷却期列）→ 强制再报一条"持续提醒"，避免同一过程长时间静默抑制。"""
    if not config.hysteresis_renotify:
        return False
    cooldown = config.cooldown_for(rule_type, pollutant)
    if cooldown <= 0:
        return False
    last_ts = _parse_ts(state.get("last_push_ts"))
    return last_ts is not None and now - last_ts >= timedelta(minutes=cooldown)


def shared_cooldown_reason(
    group_state: dict[str, Any], *, now: datetime, config: AirAlertRuleConfig
) -> str | None:
    last_ts = _parse_ts(group_state.get("last_push_ts"))
    cooldown = config.cooldown_for(
        str(group_state.get("last_rule_type") or ""),
        str(group_state.get("pollutant") or ""),
    )
    if last_ts is not None and cooldown and now - last_ts < timedelta(minutes=cooldown):
        return "shared_cooldown"
    return None


def quota_reason(
    store: AlertStateStore, station_id: str, day: str, config: AirAlertRuleConfig
) -> str | None:
    """数量限额：站点日上限与全局日上限（规则总表未定义，保留运营层）。"""
    if store.site_push_count(day, station_id) >= config.site_daily_quota:
        return "quota"
    if store.global_push_count(day) >= config.global_daily_cap:
        return "global_cap"
    return None


def commit_push(
    store: AlertStateStore,
    state: dict[str, Any],
    *,
    event_id: str,
    air_quality_level: str | None,
    now: datetime,
    recovery_threshold: float | None,
    station_id: str,
) -> None:
    """实际推送后的状态落位与日计数累加。"""
    if not state.get("first_event_id"):
        state["first_event_id"] = event_id
    state["last_push_ts"] = now.isoformat()
    state["last_air_level"] = air_quality_level
    state["armed"] = False
    state["recover_cnt"] = 0
    state["last_trigger_threshold"] = recovery_threshold
    store.increment_push(now.astimezone(TZ_SHANGHAI).date().isoformat(), station_id)


def recovery_pass(
    store: AlertStateStore,
    recovery_metrics: dict[tuple[str, str, str, str], float],
    config: AirAlertRuleConfig,
) -> list[str]:
    """恢复防抖：连续 recover_periods 个周期 ≤ 阈值×recover_ratio 才重新武装。

    ``recovery_metrics`` 的键是 (grain, station_id, pollutant, rule_type)，值
    必须与对应规则的阈值同口径（OL 为相对其余站均值的偏差，DS/CL 为相对
    基线的增量），不能用原始浓度——否则恢复判断永远不成立。
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
        grain, station_id, pollutant, rule = parts
        current = recovery_metrics.get((grain, station_id, pollutant, rule))
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


def _evaluate_chronic_outlier_state(
    state: dict[str, Any], config: AirAlertRuleConfig, now: datetime
) -> None:
    """按 OL 命中历史维护长期系统性偏差状态。"""
    if not config.ol_chronic_enabled:
        return
    cutoff = now.date() - timedelta(days=config.ol_chronic_lookback_days - 1)
    last_hit = _parse_ts(state.get("ol_last_hit_day"))
    if (
        state.get("ol_chronic_active")
        and last_hit is not None
        and (now.date() - last_hit.date()).days > config.ol_chronic_recovery_days
    ):
        state["ol_chronic_active"] = False
        state["ol_chronic_since"] = None
        state["ol_chronic_reference_delta"] = None
    history = [
        item for item in state.get("ol_history", [])
        if _parse_ts(item.get("occurred_at")) is not None
        and _parse_ts(item["occurred_at"]).date() >= cutoff
    ]
    state["ol_history"] = history
    if not state.get("ol_chronic_active") and (
        last_hit is None or (now.date() - last_hit.date()).days <= config.ol_chronic_recovery_days
    ):
        days = {_parse_ts(item["occurred_at"]).date() for item in history}
        if len(history) >= config.ol_chronic_min_events and len(days) >= config.ol_chronic_min_days:
            deltas = sorted(float(item["absolute_delta"]) for item in history)
            state["ol_chronic_active"] = True
            state["ol_chronic_since"] = now.isoformat()
            state["ol_chronic_reference_delta"] = deltas[len(deltas) // 2]


def _chronic_outlier_reason(
    alert: dict[str, Any], state: dict[str, Any], config: AirAlertRuleConfig
) -> str | None:
    """识别并记录 OL 历史；慢性状态仅放行等级升级或幅度显著加重。"""
    if not config.ol_chronic_enabled or alert.get("rule_type") != "spatial_outlier":
        return None
    occurred_at = _parse_ts(alert.get("occurred_at"))
    if occurred_at is None:
        return None
    delta = float(alert.get("absolute_delta") or 0.0)
    history = state.setdefault("ol_history", [])
    history.append({"occurred_at": occurred_at.isoformat(), "absolute_delta": delta})
    state["ol_last_hit_day"] = occurred_at.date().isoformat()
    if alert.get("air_quality_level") and state.get("last_air_level") is None:
        state["last_air_level"] = alert.get("air_quality_level")
    if not state.get("ol_chronic_active"):
        return None
    reference = state.get("ol_chronic_reference_delta")
    if reference and delta >= float(reference) * config.ol_chronic_escalation_ratio:
        alert["chronic_escalation"] = True
        alert["chronic_reference_delta"] = reference
        return None
    return "chronic_outlier"


def merge_by_station(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同站合并：按站点 + 粒度合并为一条通报，跨因子只影响通报组织，
    不改变 #24 已完成的优先级选择。"""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for alert in candidates:
        grouped[(str(alert.get("measurement_granularity")), str(alert.get("station_id")))].append(alert)
    primaries: list[dict[str, Any]] = []
    for items in grouped.values():
        items.sort(key=lambda a: (
            int(a.get("rule_priority") or 9),
            POLLUTANT_ORDER.get(str(a.get("target_pollutant")), 9),
            str(a.get("event_id")),
        ))
        primary = items[0]
        concurrent = items[1:]
        if concurrent:
            primary["concurrent_rules"] = [
                {
                    "rule_type": item.get("rule_type"),
                    "rule_label": item.get("rule_label"),
                    "air_quality_level": item.get("air_quality_level"),
                    "event_id": item.get("event_id"),
                    "target_pollutant": item.get("target_pollutant"),
                }
                for item in concurrent
            ]
        primaries.append(primary)
    primaries.sort(key=lambda a: (
        int(a.get("rule_priority") or 9),
        str(a.get("station_id")),
    ))
    return primaries


def build_window_summary(pushed: list[dict[str, Any]]) -> str | None:
    if not pushed:
        return None
    lines = [f"本轮共 {len(pushed)} 个站点告警："]
    for alert in pushed:
        lines.append(
            f"- {alert.get('station_name') or alert.get('station_id')} "
            f"{alert.get('target_pollutant')} {alert.get('station_value')} "
            f"（{alert.get('rule_label')}，{alert.get('air_quality_level') or '等级未知'}）"
        )
    return "\n".join(lines)


class PushLogStore:
    """push_log 按日 JSONL：每条候选（无论是否实际推送）都落一条流水。"""

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
    recovery_metrics: dict[tuple[str, str, str, str], float] | None = None,
    pre_suppressed: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """推送管控主链：引擎抑制留痕 → 恢复防抖 → #24 优先级逐条过闸门
    （升级穿透免打扰/防抖/冷却）→ 同站合并 → 推送。

    ``pre_suppressed`` 是引擎层（如 CL 区域合并）已决定抑制的候选，本链只
    负责把它们与链内抑制一并写入推送流水（不推送、不占冷却、不占限额）。
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
            "rule_priority": alert.get("rule_priority"),
            "air_quality_level": alert.get("air_quality_level"),
            "event_id": alert.get("event_id"),
            "action": action,
            "reason": reason,
            **extra,
        }
        log_entries.append(entry)

    # 0) 引擎层抑制留痕（CL 区域合并等）：只写流水，不进推送闸门。
    for item in pre_suppressed or []:
        alert = item["alert"]
        alert.setdefault("suppress_reason", item["reason"])
        merged_into = alert.get("merged_into_event_id")
        _log(
            alert,
            "suppress",
            item["reason"],
            **({"merged_into_event_id": merged_into} if merged_into else {}),
        )
        suppressed.append(item)

    # 1) 恢复防抖检查。
    if recovery_metrics:
        recovery_pass(store, recovery_metrics, config)
    for key, state in store.all_instances().items():
        if key.endswith("::spatial_outlier"):
            _evaluate_chronic_outlier_state(state, config, now)
    store.save()

    # 2) #24 优先级 + 闸门：同站同因子同窗口的候选按 DS>CL>OL 逐条过闸门，
    #    取第一条能推送的；其余候选以 priority 抑制留痕。全部被闸门拦截时，
    #    各自保留真实抑制原因（高优先级被拦不再连坐低优先级）。
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for alert in candidates:
        grouped[(
            str(alert.get("measurement_granularity")),
            str(alert.get("station_id")),
            str(alert.get("target_pollutant")),
        )].append(alert)
    pending: list[dict[str, Any]] = []
    for items in grouped.values():
        items.sort(key=lambda a: (int(a.get("rule_priority") or 9), str(a.get("event_id"))))
        for index, alert in enumerate(items):
            rule_type = str(alert.get("rule_type") or "")
            pollutant = str(alert.get("target_pollutant") or "")
            station_id = str(alert.get("station_id") or "")
            grain = str(alert.get("measurement_granularity"))
            state = store.instance(grain, station_id, pollutant, rule_type)
            notification_group = (
                store.notification_group(grain, station_id, pollutant)
                if rule_type in SINGLE_STATION_RULES else None
            )
            _evaluate_chronic_outlier_state(state, config, now)
            chronic_reason = _chronic_outlier_reason(alert, state, config)
            upgrade = upgrade_info(state, alert.get("air_quality_level"))
            if upgrade:
                alert.update(upgrade)
                alert["upgrade_of_event_id"] = state.get("first_event_id")
            if chronic_reason and not upgrade:
                alert["suppress_reason"] = chronic_reason
                suppressed.append({"alert": alert, "reason": chronic_reason})
                _log(alert, "suppress", chronic_reason)
                continue
            # 免打扰只拦常规再报；#23 升级例外（等级升高）夜间也必须叫人。
            # MR 等级穿透（2026-11-22 定版）：轻度及以上的多站同步抬升代表
            # 区域过程，夜间静默会造成"区域事件静默、未覆盖单站照常外发"
            # 的口径倒挂（11-22 22:00 实例：MR 被静默、两条单站 CL 外发）。
            mr_quiet_pierce = (
                rule_type == "multi_station_rise"
                and int(config.mr_quiet_pierce_level_code or 0) > 0
                and LEVEL_CODES.get(normalize_level(alert.get("air_quality_level")), 2)
                >= int(config.mr_quiet_pierce_level_code)
            )
            if not upgrade and not mr_quiet_pierce and config.quiet_suppresses(rule_type) and config.in_quiet_hours(now.hour):
                alert["suppress_reason"] = "quiet_hours"
                suppressed.append({"alert": alert, "reason": "quiet_hours"})
                _log(alert, "suppress", "quiet_hours")
                continue
            # MR 低幅度档（涉事站全为优档且主站幅度不足全阈值）→ 摘要口径，不推送。
            if rule_type == "multi_station_rise" and (alert.get("detail") or {}).get("mr_tier") == "digest":
                alert["suppress_reason"] = "mr_digest"
                suppressed.append({"alert": alert, "reason": "mr_digest"})
                _log(alert, "suppress", "mr_digest")
                continue
            reason = evaluate_gate(
                state,
                rule_type=rule_type,
                pollutant=pollutant,
                air_quality_level=alert.get("air_quality_level"),
                now=now,
                config=config,
            )
            if reason == "hysteresis" and renotify_due(
                state, rule_type=rule_type, pollutant=pollutant, now=now, config=config,
            ):
                # 滞回心跳放行：同一偏离过程的持续提醒（非新事件）。
                alert["is_renotify"] = True
                alert["renotify_of_event_id"] = state.get("first_event_id")
                alert["renotify_window_minutes"] = config.cooldown_for(rule_type, pollutant)
                reason = None
            if reason:
                alert["suppress_reason"] = reason
                suppressed.append({"alert": alert, "reason": reason})
                _log(alert, "suppress", reason)
                continue
            if not upgrade and notification_group is not None:
                shared_reason = shared_cooldown_reason(notification_group, now=now, config=config)
                if shared_reason:
                    alert["suppress_reason"] = shared_reason
                    suppressed.append({"alert": alert, "reason": shared_reason})
                    _log(alert, "suppress", shared_reason)
                    continue
            reason = quota_reason(store, station_id, day, config)
            if reason:
                alert["suppress_reason"] = reason
                suppressed.append({"alert": alert, "reason": reason})
                _log(alert, "suppress", reason)
                continue
            # 本候选通过全部闸门 → 组内赢家；其余候选以 priority 抑制留痕。
            for loser in items[index + 1:]:
                loser["suppress_reason"] = "priority"
                suppressed.append({"alert": loser, "reason": "priority"})
                _log(loser, "suppress", "priority")
            pending.append(alert)
            break

    # 4) 同站合并（跨因子只影响通报组织，主告警带 concurrent_rules）。
    primaries = merge_by_station(pending)
    primary_ids = {alert.get("event_id") for alert in primaries}

    # 5) 推送落位：每个候选写自己的规则实例状态，计数逐条累加。
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
            event_id=str(alert.get("event_id") or ""),
            air_quality_level=alert.get("air_quality_level"),
            now=now,
            recovery_threshold=alert.get("recovery_threshold"),
            station_id=str(alert.get("station_id")),
        )
        rule_type = str(alert.get("rule_type") or "")
        if rule_type in SINGLE_STATION_RULES:
            group_state = store.notification_group(
                str(alert.get("measurement_granularity")),
                str(alert.get("station_id")),
                str(alert.get("target_pollutant")),
            )
            group_state.update({
                "last_push_ts": now.isoformat(),
                "last_rule_type": rule_type,
                "last_event_id": alert.get("event_id"),
                "last_air_level": alert.get("air_quality_level"),
                "pollutant": alert.get("target_pollutant"),
            })
        alert["push_decision"] = {"action": "push", "decided_at": now.isoformat()}
        _log(
            alert,
            "push",
            None,
            is_primary=alert.get("event_id") in primary_ids,
            is_upgrade=bool(alert.get("is_upgrade")),
            is_renotify=bool(alert.get("is_renotify")),
        )

    store.save()
    if log_store is not None:
        log_store.append(log_entries)
    summary = build_window_summary(primaries)
    # 返回全部已推送候选（含被合并为附注的因子），主告警带 concurrent_rules。
    return pending, suppressed, summary
