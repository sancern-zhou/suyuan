"""江苏审核平台数据审核事件抓取器。

每日（含补看昨日）调用平台第三方接口：

1. ``GetExternalStationAuditStatus`` 拉取昨天+今天的站点审核状态，筛选已完成
   初审（状态非 ``WaitAudit``）的站点-审核日；
2. 对每个新站点-审核日调用 ``GetExternalEvidence`` 按三个页签（初审结果/恒值/
   离群值）抓取审核记录证据包，落盘后发布 ``jiangsu.data_audit.review_requested``
   事件，由 ``jiangsu_data_audit_review`` 任务 Agent 出审核结论；
3. 次日起对已派发条目回捞 ``GetExternalAuditLogs``：把平台人工初审/复核日志
   转化为 task_review 人工决定与 human_feedback（案例库+长期记忆学习走既有
   ``task_review_feedback`` 链路），结论与人工处理冲突时以
   ``continuity_context`` 派发增量重审事件。

subject_id 约定 ``{station_code}:{audit_day}``，与任务 ``review_subject_attribute``
绑定，事件 attributes 提供 ``audit_subject_id``。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scheduled_tasks.models.event import TaskEvent
from app.services.task_review import decide_review, has_active_review, load_review
from app.tools.jiangsu.demo_freeze import demo_freeze_active, demo_freeze_skip_result
from app.tools.jiangsu.external_audit import (
    TAB_TYPE_LABELS,
    TAB_TYPES,
    JiangsuExternalAuditClient,
    _format_day,
    _parse_day,
)
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

REVIEW_TASK_ID = "jiangsu_data_audit_review"
EVENT_TYPE = "jiangsu.data_audit.review_requested"
EVIDENCE_SCHEMA = "jiangsu_data_audit_review/v1"

POLL_SCHEDULE = os.getenv("JIANGSU_DATA_AUDIT_REVIEW_POLL_CRON", "30 7 * * *")
# 每次同步覆盖 [今天-LOOKBACK_DAYS, 今天] 的审核日；默认 1 = 昨天+今天。
LOOKBACK_DAYS = max(0, int(os.getenv("JIANGSU_DATA_AUDIT_REVIEW_LOOKBACK_DAYS", "1")))
MAX_EVENTS_PER_RUN = int(os.getenv("JIANGSU_DATA_AUDIT_REVIEW_MAX_EVENTS_PER_RUN", "50"))
TAB_MAX_RECORDS = int(os.getenv("JIANGSU_DATA_AUDIT_REVIEW_TAB_MAX_RECORDS", "50"))
EVIDENCE_PACKAGE_TIMEOUT_SECONDS = float(
    os.getenv("JIANGSU_DATA_AUDIT_REVIEW_PACKAGE_TIMEOUT_SECONDS", "900")
)
# 平台人工日志回看的最大审核日年龄；超过后条目过期，不再等待反馈。
FEEDBACK_MAX_AGE_DAYS = int(os.getenv("JIANGSU_DATA_AUDIT_FEEDBACK_MAX_AGE_DAYS", "10"))
# AI 结论迟迟未生成（无 review 记录）时，超过该天数停止等待反馈。
FEEDBACK_REVIEW_GRACE_DAYS = int(os.getenv("JIANGSU_DATA_AUDIT_FEEDBACK_REVIEW_GRACE_DAYS", "3"))
MAX_RERUN_ROUNDS = int(os.getenv("JIANGSU_DATA_AUDIT_FEEDBACK_MAX_RERUN_ROUNDS", "2"))

WAIT_AUDIT_STATE = "WaitAudit"
# 审核状态枚举（平台 AuditEnum.StationState）：
# WaitAudit 待审核 / WaitUpload 待上报 / WaitReview 待复核 / Reviewed 已复核 /
# DirectAudit 已直审 / BackUp 回补；除 WaitAudit 外均视为已完成初审操作。
STATE_CODE_BY_INDEX = {
    0: "WaitAudit", 1: "WaitUpload", 2: "WaitReview",
    3: "Reviewed", 4: "DirectAudit", 5: "BackUp",
}
# 审核操作枚举（平台 AuditEnum.AuditOperateType）中会改动数据判定/数值的操作。
_MODIFYING_OPERATE_TYPES = {"AddMark", "RemoveMark", "Round", "Recover", "Recuperation"}
_OPERATE_TYPE_BY_INDEX = {
    0: "AddMark", 1: "RemoveMark", 2: "Round", 3: "Recover", 4: "Redo",
    5: "Comments", 6: "Pass", 7: "UnPass", 8: "Recuperation", 9: "UndoPreHandle",
}
PLATFORM_ACTOR = {
    "user_id": "system",
    "username": "jiangsu-audit-platform",
    "display_name": "江苏省审核联网平台",
}

MAX_INLINE_EVIDENCE_ITEMS = 120
MAX_STATE_ENTRIES = 20000


def _now() -> datetime:
    return datetime.now().astimezone()


def _state_code_text(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return STATE_CODE_BY_INDEX.get(value, str(value))
    return str(value or "").strip()


def _operate_type_text(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return _OPERATE_TYPE_BY_INDEX.get(value, str(value))
    return str(value or "").strip()


def _station_day_key(row: dict[str, Any]) -> tuple[str, date] | None:
    code = str(row.get("stationCode") or "").strip()
    day = _parse_day(row.get("dayTime"))
    if not code or day is None:
        return None
    return code, day


def _subject_id(station_code: str, audit_day: str) -> str:
    return f"{station_code}:{audit_day}"


def _event_id(station_code: str, audit_day: str) -> str:
    digest = hashlib.sha256(f"{station_code}|{audit_day}".encode()).hexdigest()[:20]
    return f"da-audit-{digest}"


def _review_id(subject_id: str) -> str:
    # 与 app.services.task_review.submit_review 的确定性 review_id 保持一致。
    digest = hashlib.sha256(
        json.dumps([REVIEW_TASK_ID, subject_id], ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return f"review_{digest}"


def _compact_value(value: Any, *, depth: int = 0, max_items: int = MAX_INLINE_EVIDENCE_ITEMS) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 2000 else value[:2000] + "…[truncated]"
    if depth >= 6:
        return "[nested data omitted]" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        kept = [_compact_value(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            kept.append(f"…[{len(value) - max_items} more omitted]")
        return kept
    if isinstance(value, dict):
        return {str(key): _compact_value(item, depth=depth + 1, max_items=max_items)
                for key, item in value.items()}
    return value


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    """压缩单条审核记录：保留页面字段与 matchedRules，证据链限深限长。"""
    compact: dict[str, Any] = {}
    for key, value in record.items():
        if key == "evidence":
            compact[key] = _compact_value(value)
        elif isinstance(value, list):
            compact[key] = _compact_value(value, max_items=200)
        else:
            compact[key] = value
    return compact


def _log_time_text(row: dict[str, Any]) -> str:
    return str(row.get("operateTime") or row.get("timePoint") or "").strip()


def _human_data_modifications(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in logs
            if _operate_type_text(row.get("operateType")) in _MODIFYING_OPERATE_TYPES]


def _summarize_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
    audit_types: dict[str, int] = {}
    operate_types: dict[str, int] = {}
    operators: set[str] = set()
    for row in logs:
        audit_type = str(row.get("auditType") or "").strip() or "未知"
        audit_types[audit_type] = audit_types.get(audit_type, 0) + 1
        operate_type = _operate_type_text(row.get("operateType")) or "未知"
        operate_types[operate_type] = operate_types.get(operate_type, 0) + 1
        operator = str(row.get("operator") or "").strip()
        if operator:
            operators.add(operator)
    modifications = _human_data_modifications(logs)
    samples: list[dict[str, Any]] = []
    for row in modifications[:30]:
        samples.append({
            "time_point": str(row.get("timePoint") or ""),
            "pollutant_name": str(row.get("pollutantName") or ""),
            "operate_type": _operate_type_text(row.get("operateType")),
            "before_value": row.get("beforeValue"),
            "after_value": row.get("afterValue"),
            "before_mark": row.get("beforeMark"),
            "after_mark": row.get("afterMark"),
            "audit_desc": str(row.get("auditDesc") or ""),
            "operator": str(row.get("operator") or ""),
            "operate_time": str(row.get("operateTime") or ""),
        })
    return {
        "log_count": len(logs),
        "audit_type_counts": audit_types,
        "operate_type_counts": operate_types,
        "operators": sorted(operators),
        "modification_count": len(modifications),
        "modification_samples": samples,
        "has_data_modification": bool(modifications),
    }


def _ai_decision(record: dict[str, Any]) -> str:
    return str(record.get("decision") or "").strip()


def _ai_recommends_exclusion(record: dict[str, Any]) -> bool:
    return any(
        str(item.get("decision") or "") in {"exclude", "partial_exclude"}
        for item in record.get("data_impact") or []
        if isinstance(item, dict)
    )


def _conflicts_with_platform(record: dict[str, Any], log_summary: dict[str, Any]) -> bool:
    """AI 结论与平台人工初审是否冲突（冲突才触发增量重审）。"""
    ai_decision = _ai_decision(record)
    modified = bool(log_summary.get("has_data_modification"))
    if ai_decision == "needs_evidence":
        # 证据当时不足；平台已完成人工初审，按人工口径重审。
        return True
    if ai_decision == "approve" and modified:
        # AI 认为数据无需处理，人工却修改了数据判定/数值。
        return True
    if ai_decision == "reject" and not modified and _ai_recommends_exclusion(record):
        # AI 建议剔除，人工未做任何数据修改。
        return True
    return False


def _feedback_comment(log_summary: dict[str, Any], *, conflict: bool) -> str:
    counts = "、".join(f"{name}{count}条" for name, count in log_summary["audit_type_counts"].items())
    operators = "、".join(log_summary["operators"]) or "未知"
    if conflict:
        return (
            f"平台人工审核日志与 AI 结论存在分歧（{counts}；操作人：{operators}；"
            f"数据修改{log_summary['modification_count']}处），已按平台人工意见触发增量重审。"
        )
    return (
        f"平台人工审核日志与 AI 结论一致（{counts}；操作人：{operators}；"
        f"数据修改{log_summary['modification_count']}处），AI 结论予以确认。"
    )


class JiangsuDataAuditReviewEventFetcher(DataFetcher):
    """每日同步平台初审状态并发布数据审核事件，次日以审核日志闭环。"""

    def __init__(
        self,
        *,
        registry_root: Path | None = None,
        event_publisher: Callable[[TaskEvent], Awaitable[Any]] | None = None,
        clock: Callable[[], datetime] = _now,
        client: JiangsuExternalAuditClient | None = None,
    ) -> None:
        super().__init__(
            name="jiangsu_data_audit_review_event",
            description=(
                "每日同步江苏审核平台站点初审状态，组装数据审核证据包并发布审核事件；"
                "次日回捞平台审核日志作为人工反馈，更新结论、案例库与长期记忆"
            ),
            schedule=POLL_SCHEDULE,
            version="1.0.0",
        )
        self.registry_root = registry_root or get_data_registry()
        self.output_root = self.registry_root / "data_audit_review_events"
        self.state_path = self.output_root / "poll_state.json"
        self.event_publisher = event_publisher or self._publish_event
        self.clock = clock
        self.client = client or JiangsuExternalAuditClient()

    # ------------------------------------------------------------------ state

    def _read_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _save_state(self, state: dict[str, Any]) -> None:
        dispatched = state.get("dispatched")
        if isinstance(dispatched, dict) and len(dispatched) > MAX_STATE_ENTRIES:
            ordered = sorted(
                dispatched.items(),
                key=lambda item: item[1].get("dispatched_at", ""),
                reverse=True,
            )
            state["dispatched"] = dict(ordered[:MAX_STATE_ENTRIES])
        self._write_json(self.state_path, state)

    # ------------------------------------------------------------------ main

    async def fetch_and_store(self) -> dict[str, Any]:
        if demo_freeze_active():
            return demo_freeze_skip_result(self.name)
        now = self.clock()
        state = self._read_state()
        state.setdefault("dispatched", {})
        sync_stats = await self._sync_station_days(now, state)
        feedback_stats = await self._apply_platform_feedback(now, state)
        state["last_poll_at"] = now.isoformat()
        self._save_state(state)
        result = {"last_run_at": now.isoformat(), **sync_stats, **feedback_stats}
        logger.info("jiangsu_data_audit_review_poll_completed", **result)
        return result

    # ------------------------------------------------------------------ sync

    async def _sync_station_days(self, now: datetime, state: dict[str, Any]) -> dict[str, Any]:
        today = now.date()
        start_day = today - timedelta(days=LOOKBACK_DAYS)
        rows = await self.client.get_station_audit_status(start_day, today)
        candidates: dict[tuple[str, date], dict[str, Any]] = {}
        for row in rows:
            key = _station_day_key(row)
            if key is None:
                continue
            code, day = key
            if not (start_day <= day <= today):
                continue
            if _state_code_text(row.get("stateCode")) in ("", WAIT_AUDIT_STATE):
                continue
            candidates[(code, day)] = row

        dispatched: dict[str, dict[str, Any]] = state["dispatched"]
        published = skipped_processed = skipped_existing = failed_evidence = 0
        waiting_candidates = len(candidates)
        for (code, day), row in sorted(candidates.items(), key=lambda item: (item[0][1], item[0][0])):
            audit_day = _format_day(day)
            subject = _subject_id(code, audit_day)
            if subject in dispatched:
                skipped_processed += 1
                continue
            if has_active_review(REVIEW_TASK_ID, subject):
                skipped_existing += 1
                continue
            try:
                event = await asyncio.wait_for(
                    self._write_event_package(row, code, day, now),
                    timeout=EVIDENCE_PACKAGE_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - 单站失败不阻塞其余站点
                failed_evidence += 1
                logger.warning(
                    "jiangsu_data_audit_review_evidence_failed",
                    station_code=code, audit_day=audit_day, error=str(exc),
                )
                continue
            try:
                await self.event_publisher(event)
            except Exception as exc:  # noqa: BLE001
                failed_evidence += 1
                logger.warning(
                    "jiangsu_data_audit_review_publish_failed",
                    station_code=code, audit_day=audit_day, error=str(exc),
                )
                continue
            station = event.payload.get("station") or {}
            dispatched[subject] = {
                "station_code": code,
                "station_name": str(station.get("station_name") or ""),
                "city_name": str(station.get("city_name") or ""),
                "district_name": str(station.get("district_name") or ""),
                "audit_day": audit_day,
                "station_state": {
                    "state_code": _state_code_text(row.get("stateCode")),
                    "state_name": str(row.get("stateName") or ""),
                },
                "event_id": event.event_id,
                "event_dir": str(self.output_root / day.strftime("%Y/%m/%d") / event.event_id),
                "dispatched_at": now.isoformat(),
                "feedback": {
                    "status": "waiting_logs",
                    "rounds": 0,
                    "decided_version": None,
                    "last_operate_time": None,
                },
            }
            published += 1
            self._save_state(state)
            if published >= MAX_EVENTS_PER_RUN:
                break
        return {
            "sync_window": [str(start_day), str(today)],
            "status_rows": len(rows),
            "initial_review_candidates": waiting_candidates,
            "published_events": published,
            "skipped_processed": skipped_processed,
            "skipped_existing_review": skipped_existing,
            "failed_evidence": failed_evidence,
        }

    async def _write_event_package(
        self, row: dict[str, Any], station_code: str, day: date, now: datetime,
    ) -> TaskEvent:
        audit_day = _format_day(day)
        subject = _subject_id(station_code, audit_day)
        event_id = _event_id(station_code, audit_day)
        event_dir = self.output_root / day.strftime("%Y/%m/%d") / event_id
        tabs: dict[str, Any] = {}
        gaps: list[dict[str, str]] = []
        for tab in TAB_TYPES:
            label = TAB_TYPE_LABELS[tab]
            try:
                result = await self.client.fetch_evidence_records(
                    audit_day, audit_day, tab,
                    station_codes=[station_code], max_records=TAB_MAX_RECORDS,
                )
                tabs[tab] = {
                    "label": label,
                    "total_count": result["total_count"],
                    "fetched_count": len(result["records"]),
                    "truncated": result["truncated"],
                    "records": [_compact_record(record) for record in result["records"]],
                }
                if result["truncated"]:
                    gaps.append({
                        "tab": tab,
                        "reason": (
                            f"{label}页签审核记录超过单站单日落包上限 {TAB_MAX_RECORDS} 条，"
                            "已截断；如需全量请人工复核平台页面。"
                        ),
                    })
            except Exception as exc:  # noqa: BLE001 - 单页签失败保留其余证据
                tabs[tab] = {
                    "label": label, "total_count": None, "fetched_count": 0,
                    "records": [], "failed": True,
                }
                gaps.append({"tab": tab, "reason": f"{label}页签证据包查询失败：{exc}"})
        station = {
            "station_code": station_code,
            "station_name": str(row.get("stationName") or ""),
            "city_name": str(row.get("cityName") or ""),
            "city_code": str(row.get("cityCode") or ""),
            "district_name": str(row.get("districtName") or ""),
            "district_code": str(row.get("districtCode") or ""),
            "unique_code": str(row.get("uniqueCode") or ""),
        }
        def _tab_count(tab: str) -> int:
            value = tabs[tab].get("total_count")
            if value is None:
                value = tabs[tab].get("fetched_count")
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        tab_counts = {tab: _tab_count(tab) for tab in TAB_TYPES}
        evidence = {
            "schema_version": EVIDENCE_SCHEMA,
            "task_id": REVIEW_TASK_ID,
            "subject_id": subject,
            "generated_at": now.isoformat(),
            "station": station,
            "audit_day": audit_day,
            "station_state": {
                "state_code": _state_code_text(row.get("stateCode")),
                "state_name": str(row.get("stateName") or ""),
            },
            "query_window": {"start": f"{audit_day}T00:00:00", "end": f"{audit_day}T23:59:59"},
            "tabs": tabs,
            "gaps": gaps,
            "collection_notes": [
                "证据来自江苏审核平台第三方接口 GetExternalEvidence，按站点+自然日聚合三个页签。",
                "每条审核记录按 stationCode+timePoint+pollutantCode 关联证据链，证据窗口为事件小时及前一小时。",
                "matchedRules 返回该数据点命中的全部异常模型规则；matchedRules.reason/proof 含平台 AI 研判标签与判断依据，仅供交叉参考。",
                "数值 null 表示缺失或源无效占位，不是 0；审核前后值见 auditBeforeValue/auditAfterValue。",
                "视频/附件地址可能仅内网可用；报警集合只表示同站点同范围关联证据，不表示逐条因果匹配。",
            ],
        }
        evidence_path = event_dir / "review_evidence_pack.json"
        self._write_json(evidence_path, evidence)
        summary_text = (
            f"{station['station_name'] or station_code} {audit_day} 数据审核"
            f"（初审{tab_counts['initialReview']}条/恒值{tab_counts['constant']}条"
            f"/离群{tab_counts['outlier']}条）"
        )
        event = TaskEvent(
            event_id=event_id,
            event_type=EVENT_TYPE,
            occurred_at=now,
            attributes={
                "station_code": station_code,
                "station_name": station["station_name"],
                "city_name": station["city_name"],
                "district_name": station["district_name"],
                "audit_day": audit_day,
                "audit_subject_id": subject,
                "station_state": str(row.get("stateName") or _state_code_text(row.get("stateCode"))),
                "record_count": sum(count or 0 for count in tab_counts.values()),
                "summary": summary_text,
            },
            payload={
                "station": station,
                "audit_day": audit_day,
                "subject_id": subject,
                "summary": summary_text,
                "evidence_pack_path": format_agent_path(evidence_path),
                "evidence_dir": format_agent_path(event_dir),
                "tab_record_counts": tab_counts,
                "review_submit_tool": "submit_task_review",
                "submission_note": (
                    "category 填数据审核；subject_id 与 event_id 均填 payload.subject_id；"
                    "审核对象为平台已完成初审的站点-审核日。"
                ),
            },
        )
        self._write_json(event_dir / "event.json", event.model_dump(mode="json"))
        return event

    # -------------------------------------------------------------- feedback

    async def _apply_platform_feedback(self, now: datetime, state: dict[str, Any]) -> dict[str, Any]:
        today = now.date()
        dispatched: dict[str, dict[str, Any]] = state["dispatched"]
        confirmed = rerun_dispatched = waiting_logs = waiting_review = expired = 0
        failures = 0
        for subject, entry in list(dispatched.items()):
            feedback = entry.setdefault("feedback", {})
            if feedback.get("status") in {"done", "expired", "no_review"}:
                continue
            audit_day = _parse_day(entry.get("audit_day"))
            if audit_day is None:
                feedback["status"] = "expired"
                expired += 1
                continue
            age_days = (today - audit_day).days
            if age_days > FEEDBACK_MAX_AGE_DAYS:
                feedback["status"] = "expired"
                expired += 1
                continue
            if audit_day >= today:
                # 按需求第二天才回捞审核日志；当日条目继续等待。
                waiting_logs += 1
                continue
            station_code = str(entry.get("station_code") or "")
            if not station_code:
                feedback["status"] = "expired"
                expired += 1
                continue
            try:
                logs = await self.client.get_audit_logs(
                    entry.get("audit_day"), entry.get("audit_day"), [station_code],
                )
            except Exception as exc:  # noqa: BLE001 - 上游失败保留等待，下次重试
                failures += 1
                logger.warning(
                    "jiangsu_data_audit_review_logs_failed",
                    station_code=station_code, audit_day=entry.get("audit_day"), error=str(exc),
                )
                waiting_logs += 1
                continue
            if not logs:
                waiting_logs += 1
                continue
            review = load_review(_review_id(subject))
            if review is None:
                if age_days > FEEDBACK_REVIEW_GRACE_DAYS:
                    feedback["status"] = "no_review"
                waiting_review += 1
                continue
            try:
                outcome = self._advance_feedback(entry, feedback, review, logs, now)
            except Exception as exc:  # noqa: BLE001 - 状态竞争或写入失败，下次重试
                failures += 1
                logger.warning(
                    "jiangsu_data_audit_review_feedback_failed",
                    subject_id=subject, error=str(exc),
                )
                continue
            if outcome == "confirmed":
                confirmed += 1
            elif outcome == "rerun":
                rerun_dispatched += 1
                try:
                    await self._publish_rerun_event(entry, review, logs, now)
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    logger.warning(
                        "jiangsu_data_audit_review_rerun_publish_failed",
                        subject_id=subject, error=str(exc),
                    )
                    # 回滚为等待状态，明天重试派发。
                    feedback["status"] = "waiting_logs"
                    feedback["rounds"] = max(0, feedback.get("rounds", 0) - 1)
                    continue
            self._save_state(state)
        return {
            "feedback_confirmed": confirmed,
            "feedback_rerun_dispatched": rerun_dispatched,
            "feedback_waiting_logs": waiting_logs,
            "feedback_waiting_review": waiting_review,
            "feedback_expired": expired,
            "feedback_failures": failures,
        }

    def _advance_feedback(
        self,
        entry: dict[str, Any],
        feedback: dict[str, Any],
        review: dict[str, Any],
        logs: list[dict[str, Any]],
        now: datetime,
    ) -> str:
        """根据平台审核日志推进单条反馈状态；返回 confirmed / rerun。

        状态流转：
        - waiting_logs + review 待处理 → 首次合成平台人工决定：一致则 confirm，
          冲突则 reject 并派发增量重审；
        - rerun_dispatched + 新版本待处理 → 增量结论已按人工日志修正，自动归档；
        - review 长期 rejected（重审执行失败或派发失败）且轮次未耗尽 → 重试派发；
        - review 已归档（人工处理）或轮次耗尽 → 结束反馈。
        """
        status = review.get("status")
        version = review.get("version", 0)
        log_summary = _summarize_logs(logs)
        feedback["last_operate_time"] = max(
            (feedback.get("last_operate_time") or ""),
            max((_log_time_text(row) for row in logs), default=""),
        )
        feedback_status = feedback.get("status") or "waiting_logs"
        rounds = feedback.get("rounds", 0)
        decided_version = feedback.get("decided_version") or 0

        if status == "archived":
            feedback["status"] = "done"
            return "confirmed"

        if (
            feedback_status == "rerun_dispatched"
            and status == "pending_review"
            and version > decided_version
        ):
            # 增量重审结论已按人工日志修正，自动归档闭环。
            decision = {
                "version": review["version"],
                "action": "confirm",
                "decision": "approve",
                "comment": (
                    "增量重审结论已按平台人工审核日志修正，系统自动归档；"
                    f"平台日志摘要：{log_summary['log_count']}条，数据修改"
                    f"{log_summary['modification_count']}处。"
                ),
                "data_impact": [],
                "intervals_confirmed": True,
            }
            decide_review(review["review_id"], decision, PLATFORM_ACTOR)
            feedback["status"] = "done"
            return "confirmed"

        if feedback_status == "waiting_logs" and status in {"pending_review", "in_disposal"}:
            conflict = _conflicts_with_platform(review, log_summary)
            if conflict and rounds < MAX_RERUN_ROUNDS:
                decision = {
                    "version": review["version"],
                    "action": "reject",
                    "decision": "reject",
                    "comment": _feedback_comment(log_summary, conflict=True),
                    "data_impact": [],
                }
                updated = decide_review(review["review_id"], decision, PLATFORM_ACTOR)
                feedback["rounds"] = rounds + 1
                feedback["decided_version"] = updated.get("version")
                feedback["status"] = "rerun_dispatched"
                entry["latest_log_summary"] = log_summary
                return "rerun"
            decision = {
                "version": review["version"],
                "action": "confirm",
                "decision": "reject" if log_summary["has_data_modification"] else "approve",
                "comment": _feedback_comment(log_summary, conflict=False),
                "data_impact": [],
                # 平台人工已实际操作数据（RM 标识/修约等），区间由平台操作事实确认。
                "intervals_confirmed": True,
            }
            decide_review(review["review_id"], decision, PLATFORM_ACTOR)
            feedback["status"] = "done"
            entry["latest_log_summary"] = log_summary
            return "confirmed"

        if (
            status == "rejected"
            and rounds < MAX_RERUN_ROUNDS
            and feedback_status in {"waiting_logs", "rerun_dispatched"}
        ):
            # 上一轮退回后重审未完成（执行失败或派发失败）：按轮次重试派发增量重审。
            feedback["rounds"] = rounds + 1
            feedback["status"] = "rerun_dispatched"
            entry["latest_log_summary"] = log_summary
            return "rerun"

        # 人工已退回但轮次耗尽，或状态异常：结束自动反馈，保留人工处理入口。
        feedback["status"] = "done"
        return "confirmed"

    async def _publish_rerun_event(
        self,
        entry: dict[str, Any],
        review: dict[str, Any],
        logs: list[dict[str, Any]],
        now: datetime,
    ) -> Any:
        event_dir = Path(str(entry.get("event_dir") or ""))
        event_file = event_dir / "event.json"
        original = TaskEvent.model_validate(json.loads(event_file.read_text(encoding="utf-8")))
        round_no = int(entry.get("feedback", {}).get("rounds") or 1)
        logs_path = event_dir / f"platform_audit_logs_r{round_no}.json"
        self._write_json(logs_path, logs)
        log_summary = entry.get("latest_log_summary") or _summarize_logs(logs)
        payload = dict(original.payload)
        payload["continuity_context"] = {
            "reason": "platform_audit_feedback",
            "note": (
                "江苏省审核平台人工初审/复核日志与上一轮 AI 结论存在分歧；"
                "平台人工处理是权威修正基准，请基于同一证据包修正审核结论。"
            ),
            "previous_submission": {
                "version": review.get("version"),
                "decision": review.get("decision"),
                "summary": review.get("summary"),
                "comment": review.get("comment"),
                "data_impact": review.get("data_impact"),
            },
            "human_decision": review.get("human_decision") or {},
            "platform_audit_logs": log_summary,
            "audit_logs_path": format_agent_path(logs_path),
        }
        event = TaskEvent(
            event_id=f"{original.event_id}-r{round_no}",
            event_type=EVENT_TYPE,
            occurred_at=now,
            attributes=dict(original.attributes),
            payload=payload,
        )
        self._write_json(event_dir / f"event_r{round_no}.json", event.model_dump(mode="json"))
        entry["rerun_event_ids"] = [*entry.get("rerun_event_ids", []), event.event_id]
        return await self.event_publisher(event)

    # -------------------------------------------------------------- publish

    @staticmethod
    async def _publish_event(event: TaskEvent) -> Any:
        from app.scheduled_tasks import get_scheduled_task_service

        return await get_scheduled_task_service().publish_event(event)
