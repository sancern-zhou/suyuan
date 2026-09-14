"""Fault work order review reject reruns.

人工在 task_review 退回故障工单审核结论后，把退回意见作为增量输入重新派发一次
AI 复审：Web 进程（审核接口所在）只负责落盘一张待处理队列条目，worker 进程的
``jiangsu_fault_work_order_review_rerun`` fetcher 每分钟领取并通过
``publish_event(force_retry=True)`` 重开同一事件的执行声明，把上一轮结论与人工
退回意见注入事件 ``payload.continuity_context``，由 Agent 修正后再次调用
``submit_task_review``（subject_id 仍为工单号，版本 +1，旧结论进入 history）。
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import structlog

from app.scheduled_tasks.models.event import TaskEvent
from app.services.task_review import list_reviews
from app.utils.path_config import get_data_registry, resolve_agent_path

logger = structlog.get_logger(__name__)

REVIEW_TASK_ID = "jiangsu_fault_work_order_review"
REVIEW_SCENARIO = "fault_work_order_review"
MAX_RERUN_ROUNDS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_MAX_RERUN_ROUNDS", "2"))
MAX_DISPATCH_ATTEMPTS = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_RERUN_MAX_ATTEMPTS", "5"))
POLL_SCHEDULE = os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_RERUN_CRON", "* * * * *")
MAX_ENTRIES_PER_RUN = int(os.getenv("JIANGSU_FAULT_WORK_ORDER_REVIEW_RERUN_MAX_PER_RUN", "5"))

QUEUE_DIR_NAME = "work_order_review_reject_reruns"

_RERUN_INSTRUCTION = (
    "本次为人工审核退回后的增量复审：审核员已退回上一轮结论并给出退回意见（见 human_decision.comment）。"
    "人工退回意见是权威修正基准，优先于上一轮 AI 推断：先逐项对照上一轮结论与退回意见，"
    "基于同一证据包（evidence_pack_path）修正审核结论、数据处置与核验项；"
    "除非存在与退回意见直接矛盾且确凿的证据并在 comment 中逐条列明分歧依据，"
    "否则必须按人工意见更新结论，不得原样重复被退回的结论，也不得以辅助证据缺口为由维持待定。"
    "确需补充事实时可按 Skill 约束用只读取证工具做最小化补查。"
    "修正后仍以完整工单号作为 subject_id 再次调用 submit_task_review 提交完整结论。"
)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "…<已截断>"


def queue_root(registry_root: Path | None = None) -> Path:
    root = Path(registry_root) if registry_root else get_data_registry()
    return root / QUEUE_DIR_NAME


def events_root(registry_root: Path | None = None) -> Path:
    root = Path(registry_root) if registry_root else get_data_registry()
    return root / "work_order_review_events"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


@contextmanager
def _queue_lock(root: Path) -> Iterator[None]:
    """跨进程互斥，避免 web 落盘与 worker 领取/移动交错。"""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows deployments
        fcntl = None
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".reruns.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _compact_submission(submission: dict[str, Any] | None) -> dict[str, Any]:
    submission = submission if isinstance(submission, dict) else {}
    sections: list[dict[str, Any]] = submission.get("sections") if isinstance(submission.get("sections"), list) else []
    key_fields: dict[str, Any] = {}
    for section in sections:
        for field in section.get("fields") or []:
            key = str(field.get("key") or "").strip()
            if key:
                key_fields[key] = _clip(field.get("value"), 200)
    data_impact = submission.get("data_impact") if isinstance(submission.get("data_impact"), list) else []
    evidence = submission.get("evidence") if isinstance(submission.get("evidence"), list) else []
    return {
        "decision": submission.get("decision"),
        "title": _clip(submission.get("title"), 120),
        "summary": _clip(submission.get("summary"), 500),
        "comment": _clip(submission.get("comment"), 900),
        "data_impact": [
            {
                "pollutant": item.get("pollutant"),
                "decision": item.get("decision"),
                "start": item.get("start"),
                "end": item.get("end"),
            }
            for item in data_impact[:10]
            if isinstance(item, dict)
        ],
        "sections_key_fields": key_fields,
        "evidence_paths": [
            str(item.get("path"))
            for item in evidence[:10]
            if isinstance(item, dict) and item.get("path")
        ],
    }


def queue_fault_work_order_review_rerun(
    record: dict[str, Any], decision: dict[str, Any], actor: dict[str, Any],
) -> dict[str, Any] | None:
    """task_review 退回钩子：故障工单审核退回后排队一次增量复审。

    只处理故障工单审核任务；排队失败仅记录告警，不影响退回动作本身。
    队列由 worker 的 ``jiangsu_fault_work_order_review_rerun`` fetcher 每分钟领取派发。
    """
    if record.get("task_id") != REVIEW_TASK_ID:
        return None
    comment = str(decision.get("comment") or "").strip()
    if not comment:
        logger.info(
            "fault_work_order_review_rerun_skipped_empty_comment",
            review_id=record.get("review_id"),
        )
        return None
    history = record.get("history") if isinstance(record.get("history"), list) else []
    completed_rounds = len(history) + 1
    if completed_rounds > MAX_RERUN_ROUNDS:
        logger.info(
            "fault_work_order_review_rerun_skipped_round_limit",
            review_id=record.get("review_id"),
            completed_rounds=completed_rounds,
            max_rerun_rounds=MAX_RERUN_ROUNDS,
        )
        return None
    subject_id = str(record.get("subject_id") or "").strip()
    if not subject_id:
        return None
    human_decision = (record.get("human_decision") or {})
    entry = {
        "queue_id": record.get("review_id"),
        "task_id": REVIEW_TASK_ID,
        "review_id": record.get("review_id"),
        "subject_id": subject_id,
        "event_id": record.get("event_id") or None,
        "queued_at": _now_iso(),
        "queued_by": {"user_id": actor.get("user_id"), "username": actor.get("username")},
        "attempts": 0,
        "max_attempts": MAX_DISPATCH_ATTEMPTS,
        "rerun_round": completed_rounds + 1,
        "continuity": {
            "mode": "incremental",
            "reason": "review_reject",
            "base_execution_id": record.get("execution_id"),
            "round": completed_rounds + 1,
            "previous_submission": _compact_submission(record.get("submission")),
            "human_decision": {
                "action": decision.get("action"),
                "decision": decision.get("decision"),
                "comment": _clip(comment, 900),
                "actor": {"user_id": actor.get("user_id"), "username": actor.get("username")},
                "occurred_at": human_decision.get("occurred_at"),
            },
            "instruction": _RERUN_INSTRUCTION,
        },
    }
    root = queue_root()
    with _queue_lock(root):
        _write_json(root / "pending" / f"{entry['queue_id']}.json", entry)
    _record_feedback_event(entry, event_type="review_rejected", to_status=None, comment=comment)
    logger.info(
        "fault_work_order_review_rerun_queued",
        review_id=entry["review_id"],
        work_order_code=subject_id,
        rerun_round=entry["rerun_round"],
    )
    return entry


def pending_entries(root: Path | None = None, limit: int = MAX_ENTRIES_PER_RUN) -> list[dict[str, Any]]:
    base = root or queue_root()
    pending_dir = base / "pending"
    if not pending_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(pending_dir.glob("*.json")):
        entry = _read_json(path)
        if entry is None:
            continue
        entry["_path"] = str(path)
        entries.append(entry)
        if len(entries) >= max(1, limit):
            break
    return entries


def locate_event_payload(
    entry: dict[str, Any], *, root: Path | None = None,
) -> dict[str, Any] | None:
    """找到该工单最近一次审核事件的事件负载（event.json 内容）。"""
    base = events_root(root)
    if not base.is_dir():
        return None
    evidence_paths = (
        ((entry.get("continuity") or {}).get("previous_submission") or {}).get("evidence_paths")
        or []
    )
    registry = get_data_registry()
    for raw_path in evidence_paths:
        try:
            path = resolve_agent_path(str(raw_path))
        except (ValueError, OSError):
            continue
        if registry not in path.parents:
            continue
        for parent in path.parents:
            if parent == registry:
                break
            candidate = parent / "event.json"
            if candidate.is_file():
                payload = _read_json(candidate)
                if payload is not None and payload.get("event_type"):
                    return payload
    wanted_event_id = str(entry.get("event_id") or "").strip()
    code_match: tuple[str, dict[str, Any]] | None = None
    for candidate in base.glob("*/*/*/*/event.json"):
        payload = _read_json(candidate)
        if payload is None or payload.get("event_type") != "jiangsu.fault_work_order.review_requested":
            continue
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        if wanted_event_id and str(payload.get("event_id")) == wanted_event_id:
            return payload
        if str(attributes.get("work_order_code") or "") == str(entry.get("subject_id") or ""):
            stamp = str(payload.get("occurred_at") or "")
            if code_match is None or stamp > code_match[0]:
                code_match = (stamp, payload)
    return code_match[1] if code_match else None


def build_rerun_event(entry: dict[str, Any], event_payload: dict[str, Any]) -> TaskEvent:
    event = TaskEvent.model_validate(event_payload)
    attributes = {**event.attributes, "continuity_mode": "review_reject"}
    payload = {**event.payload, "continuity_context": entry.get("continuity") or {}}
    return TaskEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at or datetime.now().astimezone(),
        attributes=attributes,
        payload=payload,
    )


def _record_feedback_event(
    entry: dict[str, Any], *, event_type: str, to_status: str | None, **extra: Any,
) -> None:
    try:
        from app.services.jiangsu_feedback_loop import get_feedback_loop_store

        get_feedback_loop_store().record(
            case_id=f"{REVIEW_SCENARIO}:{entry.get('subject_id')}",
            scenario=REVIEW_SCENARIO,
            event_type=event_type,
            to_status=to_status,
            source_record_id=entry.get("event_id") or entry.get("review_id"),
            payload={"review_id": entry.get("review_id"), "rerun_round": entry.get("rerun_round"), **extra},
        )
    except Exception as exc:  # noqa: BLE001 - 反馈记录失败不影响主流程
        logger.warning(
            "fault_work_order_review_rerun_feedback_record_failed",
            review_id=entry.get("review_id"),
            event_type=event_type,
            error=str(exc),
        )


def _has_pending_review(task_id: str, subject_id: str) -> bool:
    """该工单当前是否已有待人工处理（待确认/处置中）的审核结论。

    文件存储模式下的 ``has_active_review`` 对任意历史记录均返回 True，
    会把退回后的增量复审一并挡掉，因此这里显式检查活跃状态。
    """
    return any(
        record.get("subject_id") == subject_id
        and record.get("status") in {"pending_review", "in_disposal"}
        for record in list_reviews(task_id=task_id, pending_only=False)
    )


def _rewrite_entry(entry: dict[str, Any]) -> None:
    path = entry.get("_path")
    if path:
        _write_json(Path(path), {key: value for key, value in entry.items() if key != "_path"})


def _finish_entry(entry: dict[str, Any], status: str, **fields: Any) -> None:
    path = Path(entry.pop("_path", "")) if entry.get("_path") else None
    root = queue_root()
    payload = {key: value for key, value in entry.items() if key != "_path"}
    payload.update(fields)
    if path and path.is_file():
        path.unlink(missing_ok=True)
    _write_json(root / status / f"{entry.get('queue_id')}.json", payload)


async def publish_pending_reruns(*, limit: int = MAX_ENTRIES_PER_RUN) -> dict[str, int]:
    """worker 侧领取队列并派发增量复审事件；返回处理统计。"""
    root = queue_root()
    stats = {"pending": 0, "dispatched": 0, "skipped": 0, "failed": 0}
    with _queue_lock(root):
        entries = pending_entries(root, limit=limit)
        stats["pending"] = len(entries)
        if not entries:
            return stats
        try:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
        except (RuntimeError, ImportError) as exc:
            for entry in entries:
                stats["failed"] += 1
                _finish_entry(
                    entry, "failed",
                    error=f"scheduled_task_service_unavailable: {exc}",
                    finished_at=_now_iso(),
                )
            return stats
        for entry in entries:
            subject_id = str(entry.get("subject_id") or "")
            if _has_pending_review(str(entry.get("task_id") or REVIEW_TASK_ID), subject_id):
                stats["skipped"] += 1
                _finish_entry(
                    entry, "done", result="skipped_active_review", finished_at=_now_iso(),
                )
                continue
            event_payload = locate_event_payload(entry)
            if event_payload is None:
                stats["failed"] += 1
                _finish_entry(
                    entry, "failed", error="original_event_payload_not_found", finished_at=_now_iso(),
                )
                logger.warning(
                    "fault_work_order_review_rerun_event_missing",
                    review_id=entry.get("review_id"),
                    work_order_code=subject_id,
                )
                continue
            try:
                dispatch = await task_service.publish_event(
                    build_rerun_event(entry, event_payload), force_retry=True,
                )
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断其余队列
                entry["attempts"] = int(entry.get("attempts") or 0) + 1
                entry["last_error"] = str(exc)
                if entry["attempts"] >= int(entry.get("max_attempts") or MAX_DISPATCH_ATTEMPTS):
                    stats["failed"] += 1
                    _finish_entry(
                        entry, "failed", error=str(exc), finished_at=_now_iso(),
                    )
                else:
                    _rewrite_entry(entry)
                logger.warning(
                    "fault_work_order_review_rerun_dispatch_failed",
                    review_id=entry.get("review_id"),
                    attempts=entry["attempts"],
                    error=str(exc),
                )
                continue
            accepted = list(getattr(dispatch, "accepted_task_ids", []) or [])
            if not accepted:
                entry["attempts"] = int(entry.get("attempts") or 0) + 1
                entry["last_error"] = "duplicate_or_unmatched"
                if entry["attempts"] >= int(entry.get("max_attempts") or MAX_DISPATCH_ATTEMPTS):
                    stats["failed"] += 1
                    _finish_entry(
                        entry, "failed", error="duplicate_or_unmatched", finished_at=_now_iso(),
                    )
                else:
                    _rewrite_entry(entry)
                continue
            stats["dispatched"] += 1
            _finish_entry(
                entry, "done", result="dispatched",
                scheduled_task_ids=accepted,
                execution_ids=list(getattr(dispatch, "execution_ids", []) or []),
                finished_at=_now_iso(),
            )
            _record_feedback_event(
                entry, event_type="review_reject_rerun_dispatched", to_status="analyzing",
            )
            logger.info(
                "fault_work_order_review_rerun_dispatched",
                review_id=entry.get("review_id"),
                work_order_code=subject_id,
                rerun_round=entry.get("rerun_round"),
                scheduled_task_ids=accepted,
            )
    return stats


__all__ = [
    "MAX_RERUN_ROUNDS",
    "POLL_SCHEDULE",
    "REVIEW_SCENARIO",
    "REVIEW_TASK_ID",
    "build_rerun_event",
    "locate_event_payload",
    "pending_entries",
    "publish_pending_reruns",
    "queue_fault_work_order_review_rerun",
    "queue_root",
]
