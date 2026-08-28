"""Workflow-native feedback and evaluation for the Jiangsu pilot scenarios.

This module deliberately stores *business outcomes* rather than asking users to
rate an Agent response.  The web process, worker process and external business
callbacks all write the same append-only event stream under ``DATA_REGISTRY``.
The first pilot scenarios are station fault diagnosis and operations work-order
audit; other Jiangsu modes can use the same contract later.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterator

import fcntl
from pydantic import BaseModel, ConfigDict, Field

from app.utils.path_config import get_data_registry


PILOT_SCENARIOS = {"station_fault_diagnosis", "ops_work_order_audit"}
CASE_STATUSES = {
    "new",
    "analyzing",
    "awaiting_review",
    "processing",
    "awaiting_verification",
    "closed",
    "dismissed",
    "needs_followup",
    "reopened",
}

_TRANSITIONS: dict[str, set[str]] = {
    "new": {"analyzing", "awaiting_review", "dismissed"},
    "analyzing": {"awaiting_review", "needs_followup", "dismissed"},
    "awaiting_review": {"processing", "needs_followup", "dismissed"},
    "processing": {"awaiting_verification", "needs_followup", "dismissed"},
    "awaiting_verification": {"closed", "reopened", "needs_followup"},
    "needs_followup": {"analyzing", "awaiting_review", "processing", "dismissed"},
    "reopened": {"analyzing", "awaiting_review", "processing", "dismissed"},
    "closed": {"reopened"},
    "dismissed": {"reopened"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value))[:160]


class FeedbackEvent(BaseModel):
    """One immutable business/workflow event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"fb_{uuid.uuid4().hex}")
    case_id: str
    scenario: str
    event_type: str
    occurred_at: datetime = Field(default_factory=_now)
    from_status: str | None = None
    to_status: str | None = None
    source_system: str = "jiangsu"
    source_record_id: str | None = None
    actor_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, Any] = Field(default_factory=dict)


class FeedbackCase(BaseModel):
    """Materialized view of a case reconstructed from the event stream."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    scenario: str
    status: str
    created_at: datetime
    updated_at: datetime
    source_system: str = "jiangsu"
    source_record_id: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)
    event_count: int = 0
    latest_event_id: str | None = None


class FeedbackLoopStore:
    """Small append-only store suitable for the current web/worker pilot.

    The registry is shared by web and worker processes.  ``flock`` protects
    appends and the read path tolerates a partially written last line.
    """

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else get_data_registry() / "jiangsu_feedback_loop"
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.lock_path = self.root / ".events.lock"

    @contextmanager
    def _lock(self, exclusive: bool = False) -> Iterator[None]:
        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_events(self) -> list[FeedbackEvent]:
        if not self.events_path.exists():
            return []
        events: list[FeedbackEvent] = []
        with self._lock():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(FeedbackEvent.model_validate_json(line))
                except ValueError:
                    # A process crash can leave an incomplete final line.  It
                    # must not make the entire feedback API unavailable.
                    continue
        return events

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        with self._lock(exclusive=True):
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return event

    def events_for(self, case_id: str) -> list[FeedbackEvent]:
        return [event for event in self._read_events() if event.case_id == case_id]

    def materialize_case(self, case_id: str) -> FeedbackCase | None:
        events = self.events_for(case_id)
        if not events:
            return None
        events.sort(key=lambda event: event.occurred_at)
        first = events[0]
        status = first.to_status or "new"
        subject = dict(first.payload.get("subject") or {})
        for event in events[1:]:
            if event.to_status:
                status = event.to_status
            if event.payload.get("subject"):
                subject.update(event.payload["subject"])
        return FeedbackCase(
            case_id=case_id,
            scenario=first.scenario,
            status=status,
            created_at=first.occurred_at,
            updated_at=events[-1].occurred_at,
            source_system=first.source_system,
            source_record_id=first.source_record_id,
            subject=subject,
            event_count=len(events),
            latest_event_id=events[-1].event_id,
        )

    def list_cases(self, *, scenario: str | None = None, limit: int = 100) -> list[FeedbackCase]:
        case_ids: set[str] = set()
        for event in self._read_events():
            if scenario is None or event.scenario == scenario:
                case_ids.add(event.case_id)
        cases = [self.materialize_case(case_id) for case_id in case_ids]
        cases = [case for case in cases if case is not None]
        cases.sort(key=lambda case: case.updated_at, reverse=True)
        return cases[: max(1, min(limit, 500))]

    def _current_status(self, case_id: str) -> str | None:
        case = self.materialize_case(case_id)
        return case.status if case else None

    def record(
        self,
        *,
        case_id: str,
        scenario: str,
        event_type: str,
        to_status: str | None = None,
        source_record_id: str | None = None,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        labels: dict[str, Any] | None = None,
        source_system: str = "jiangsu",
    ) -> FeedbackEvent:
        if not case_id.strip():
            raise ValueError("case_id不能为空")
        if not scenario.strip():
            raise ValueError("scenario不能为空")
        if to_status is not None and to_status not in CASE_STATUSES:
            raise ValueError(f"不支持的事项状态：{to_status}")
        current = self._current_status(case_id)
        if current is not None and to_status and to_status != current:
            allowed = _TRANSITIONS.get(current, set())
            if to_status not in allowed:
                raise ValueError(f"事项 {case_id} 不允许从 {current} 转为 {to_status}")
        event = FeedbackEvent(
            case_id=case_id,
            scenario=scenario,
            event_type=event_type,
            from_status=current,
            to_status=to_status,
            source_system=source_system,
            source_record_id=source_record_id,
            actor_id=actor_id,
            payload=payload or {},
            labels=labels or {},
        )
        return self.append(event)

    def ensure_case(
        self,
        *,
        case_id: str,
        scenario: str,
        source_record_id: str | None = None,
        subject: dict[str, Any] | None = None,
    ) -> FeedbackCase:
        existing = self.materialize_case(case_id)
        if existing:
            return existing
        self.record(
            case_id=case_id,
            scenario=scenario,
            event_type="case_created",
            to_status="new",
            source_record_id=source_record_id,
            payload={"subject": subject or {}},
        )
        return self.materialize_case(case_id)  # type: ignore[return-value]

    def agent_recommendation(
        self,
        *,
        case_id: str,
        scenario: str,
        source_record_id: str | None,
        recommendation_id: str,
        payload: dict[str, Any],
        subject: dict[str, Any] | None = None,
    ) -> FeedbackEvent:
        self.ensure_case(
            case_id=case_id,
            scenario=scenario,
            source_record_id=source_record_id,
            subject=subject,
        )
        current = self._current_status(case_id)
        target = "awaiting_review" if current in {"new", "analyzing", "needs_followup", "reopened"} else current
        return self.record(
            case_id=case_id,
            scenario=scenario,
            event_type="agent_recommendation",
            to_status=target,
            source_record_id=source_record_id,
            payload={"recommendation_id": recommendation_id, **payload},
            labels={"feedback_source": "business_workflow"},
        )

    def human_review(
        self,
        *,
        case_id: str,
        scenario: str,
        decision: str,
        payload: dict[str, Any] | None = None,
        actor_id: str | None = None,
        source_record_id: str | None = None,
    ) -> FeedbackEvent:
        target = {
            "accepted": "processing",
            "modified": "processing",
            "rejected": "dismissed",
            "needs_evidence": "needs_followup",
        }.get(decision)
        if target is None:
            raise ValueError("decision 必须是 accepted、modified、rejected 或 needs_evidence")
        return self.record(
            case_id=case_id,
            scenario=scenario,
            event_type="human_review",
            to_status=target,
            actor_id=actor_id,
            source_record_id=source_record_id,
            payload={"decision": decision, **(payload or {})},
            labels={"feedback_source": "business_workflow"},
        )

    def business_action(
        self,
        *,
        case_id: str,
        scenario: str,
        action: str,
        outcome: str,
        payload: dict[str, Any] | None = None,
        source_record_id: str | None = None,
    ) -> FeedbackEvent:
        target = "awaiting_verification" if outcome in {"accepted", "success", "created"} else "needs_followup"
        return self.record(
            case_id=case_id,
            scenario=scenario,
            event_type="business_action",
            to_status=target,
            source_record_id=source_record_id,
            payload={"action": action, "outcome": outcome, **(payload or {})},
            labels={"feedback_source": "business_workflow"},
        )

    def verification(
        self,
        *,
        case_id: str,
        scenario: str,
        outcome: str,
        payload: dict[str, Any] | None = None,
        source_record_id: str | None = None,
    ) -> FeedbackEvent:
        target = "closed" if outcome in {"resolved", "completed", "passed"} else "reopened"
        return self.record(
            case_id=case_id,
            scenario=scenario,
            event_type="verification",
            to_status=target,
            source_record_id=source_record_id,
            payload={"outcome": outcome, **(payload or {})},
            labels={"feedback_source": "business_workflow"},
        )

    def metrics(self, *, scenario: str | None = None, days: int = 30) -> dict[str, Any]:
        cutoff = _now() - timedelta(days=max(1, min(days, 365)))
        all_events = self._read_events()
        events = [event for event in all_events if event.occurred_at >= cutoff]
        if scenario:
            events = [event for event in events if event.scenario == scenario]
        by_case: dict[str, list[FeedbackEvent]] = defaultdict(list)
        for event in events:
            by_case[event.case_id].append(event)
        # Reconstruct each touched case from its complete history so closure
        # latency remains correct when a case was opened before the window.
        all_by_case: dict[str, list[FeedbackEvent]] = defaultdict(list)
        for event in all_events:
            if event.case_id in by_case:
                all_by_case[event.case_id].append(event)
        cases = [self._case_from_events(rows) for rows in all_by_case.values()]
        cases = [case for case in cases if case is not None]
        reviews = [event for event in events if event.event_type == "human_review"]
        actions = [event for event in events if event.event_type == "business_action"]
        verifications = [event for event in events if event.event_type == "verification"]
        accepted = [event for event in reviews if event.payload.get("decision") in {"accepted", "modified"}]
        resolved = [event for event in verifications if event.payload.get("outcome") in {"resolved", "completed", "passed"}]
        reopened = [event for event in verifications if event.payload.get("outcome") not in {"resolved", "completed", "passed"}]
        closure_hours = [
            (case.updated_at - case.created_at).total_seconds() / 3600
            for case in cases
            if case.status == "closed"
        ]
        result: dict[str, Any] = {
            "scenario": scenario,
            "period_days": days,
            "case_count": len(cases),
            "review_count": len(reviews),
            "accepted_or_modified_count": len(accepted),
            "acceptance_rate": len(accepted) / len(reviews) if reviews else None,
            "business_action_count": len(actions),
            "verification_count": len(verifications),
            "resolved_count": len(resolved),
            "reopened_count": len(reopened),
            "verification_success_rate": len(resolved) / len(verifications) if verifications else None,
            "closed_case_count": sum(case.status == "closed" for case in cases),
            "open_case_count": sum(case.status not in {"closed", "dismissed"} for case in cases),
            "median_closure_hours": median(closure_hours) if closure_hours else None,
        }
        if scenario == "ops_work_order_audit":
            result.update(_audit_metrics(reviews))
        result["optimization_actions"] = _optimization_actions(result)
        return result

    @staticmethod
    def _case_from_events(events: list[FeedbackEvent]) -> FeedbackCase | None:
        if not events:
            return None
        events.sort(key=lambda event: event.occurred_at)
        status = events[0].to_status or "new"
        for event in events[1:]:
            if event.to_status:
                status = event.to_status
        return FeedbackCase(
            case_id=events[0].case_id,
            scenario=events[0].scenario,
            status=status,
            created_at=events[0].occurred_at,
            updated_at=events[-1].occurred_at,
            source_system=events[0].source_system,
            source_record_id=events[0].source_record_id,
            event_count=len(events),
            latest_event_id=events[-1].event_id,
        )


def _audit_metrics(reviews: list[FeedbackEvent]) -> dict[str, Any]:
    pairs = []
    for review in reviews:
        ai_ids = set(str(value) for value in review.payload.get("ai_item_ids") or [])
        final_ids = set(str(value) for value in review.payload.get("final_item_ids") or [])
        if not ai_ids and not final_ids:
            continue
        pairs.append((ai_ids, final_ids))
    if not pairs:
        return {"audit_labeled_review_count": 0, "issue_precision": None, "issue_recall": None, "issue_f1": None}
    tp = sum(len(ai & final) for ai, final in pairs)
    predicted = sum(len(ai) for ai, _ in pairs)
    actual = sum(len(final) for _, final in pairs)
    precision = tp / predicted if predicted else None
    recall = tp / actual if actual else None
    f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else None
    return {
        "audit_labeled_review_count": len(pairs),
        "issue_precision": precision,
        "issue_recall": recall,
        "issue_f1": f1,
    }


def _optimization_actions(metrics: dict[str, Any]) -> list[dict[str, str]]:
    """Turn sufficiently-sized outcome samples into reviewable next steps.

    These are deliberately recommendations for a weekly calibration review;
    the service never changes prompts, rules or model versions automatically.
    """

    actions: list[dict[str, str]] = []
    review_count = int(metrics.get("review_count") or 0)
    verification_count = int(metrics.get("verification_count") or 0)
    if review_count >= 5 and (metrics.get("acceptance_rate") or 0) < 0.7:
        actions.append({
            "type": "review_recommendation_quality",
            "reason": "人工接受或修改比例偏低",
            "next_step": "抽样查看人工修改字段，区分证据不足、口径错误和处置方案不可执行。",
        })
    if verification_count >= 5 and (metrics.get("verification_success_rate") or 0) < 0.8:
        actions.append({
            "type": "review_verification_failure",
            "reason": "业务复查通过率偏低",
            "next_step": "回放证据包和现场结果，优先调整数据补证范围、根因排序或验证标准。",
        })
    if int(metrics.get("audit_labeled_review_count") or 0) >= 5:
        precision = metrics.get("issue_precision")
        recall = metrics.get("issue_recall")
        if precision is not None and precision < 0.8:
            actions.append({
                "type": "tighten_audit_rules",
                "reason": "审核问题项 precision 偏低",
                "next_step": "按规则 ID 查看误报样本，校准规则阈值或提升人工复核门槛。",
            })
        if recall is not None and recall < 0.8:
            actions.append({
                "type": "expand_audit_evidence",
                "reason": "审核问题项 recall 偏低",
                "next_step": "按规则 ID 查看遗漏样本，补充字段、附件或语义复核证据。",
            })
    return actions


def fault_case_id(event_id: str, draft_id: str | None = None) -> str:
    """Stable case key shared by detection, diagnosis, draft and verification."""
    key = str(event_id or "").strip() or f"draft:{draft_id or uuid.uuid4().hex}"
    return f"jiangsu:fault:{_safe_slug(key)}"


def audit_case_id(dataset_path: str, run_key: str | None = None) -> str:
    key = f"{dataset_path}:{run_key}" if run_key else dataset_path
    # Dataset paths can contain deployment-specific directories; keep them out
    # of the public case identifier while retaining the source path in the
    # event payload for authorized operators.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"jiangsu:audit:{digest}"


_default_store: FeedbackLoopStore | None = None


def get_feedback_loop_store() -> FeedbackLoopStore:
    global _default_store
    if _default_store is None:
        _default_store = FeedbackLoopStore()
    return _default_store
