"""Structured retrieval over scheduled task history cases."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .storage.task_case_storage import TaskCaseStorage

_MAX_MATCHED_TERMS = 12


def search_history_cases(
    storage: TaskCaseStorage,
    *,
    query: str,
    limit: int = 5,
    status: str | None = None,
    trigger_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_failed: bool = True,
    max_scan: int | None = None,
) -> dict[str, Any]:
    """Search a task's structured case library and return compact matches."""
    terms = _extract_terms(query)
    limit = min(max(int(limit or 5), 1), 20)
    all_cases = storage.read_cases(limit=max_scan or storage.MAX_CASES)
    start_bound = _parse_datetime(from_date)
    end_bound = _parse_datetime(to_date, end_of_day=True)
    status_filter = _normalize_filter(status, {"succeeded", "failed", "timeout"})
    trigger_filter = _normalize_filter(trigger_type, {"schedule", "event"})

    scored: list[tuple[float, int, dict[str, Any], list[str]]] = []
    total = len(all_cases)
    for zero_index, case in enumerate(all_cases):
        if not _case_matches_filters(
            case,
            status_filter=status_filter,
            trigger_filter=trigger_filter,
            include_failed=include_failed,
            start_bound=start_bound,
            end_bound=end_bound,
        ):
            continue

        score, matched_terms = _score_case(case, terms)
        if terms and score <= 0:
            continue
        recency_bonus = (zero_index + 1) / max(total, 1) / 10
        scored.append((score + recency_bonus, zero_index + 1, case, matched_terms))

    scored.sort(
        key=lambda item: (
            item[0],
            _started_timestamp(item[2]),
            item[1],
        ),
        reverse=True,
    )
    matches = [
        _compact_case(case, score, case_number, matched_terms)
        for score, case_number, case, matched_terms in scored[:limit]
    ]
    return {
        "matches": matches,
        "count": len(matches),
        "total_cases": storage.case_count(),
        "query_terms": terms,
    }


def _case_matches_filters(
    case: dict[str, Any],
    *,
    status_filter: str | None,
    trigger_filter: str | None,
    include_failed: bool,
    start_bound: datetime | None,
    end_bound: datetime | None,
) -> bool:
    case_status = str(case.get("status") or "")
    if status_filter and case_status != status_filter:
        return False
    if not include_failed and case_status != "succeeded":
        return False

    trigger = case.get("trigger") if isinstance(case.get("trigger"), dict) else {}
    if trigger_filter and str(trigger.get("type") or "") != trigger_filter:
        return False

    started_at = _parse_datetime(case.get("started_at"))
    if start_bound and (started_at is None or started_at < start_bound):
        return False
    if end_bound and (started_at is None or started_at > end_bound):
        return False
    return True


def _score_case(case: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    if not terms:
        return 0.0, []

    distilled = case.get("distilled") if isinstance(case.get("distilled"), dict) else {}
    trigger = case.get("trigger") if isinstance(case.get("trigger"), dict) else {}
    weighted_texts = [
        (5.0, distilled.get("case_brief")),
        (4.0, " ".join(str(item) for item in distilled.get("findings") or [])),
        (3.0, trigger.get("context_digest")),
        (2.0, case.get("summary")),
        (2.0, _outputs_text(case.get("outputs") or [])),
        (1.5, " ".join(str(item) for item in case.get("errors") or [])),
        (1.0, f"{case.get('status') or ''} {trigger.get('type') or ''}"),
        (0.5, case.get("execution_id")),
    ]

    score = 0.0
    matched_terms: list[str] = []
    seen = set()
    for term in terms:
        term_lower = term.lower()
        term_score = 0.0
        for weight, value in weighted_texts:
            text = str(value or "").lower()
            if not text:
                continue
            occurrences = text.count(term_lower)
            if occurrences:
                term_score += weight * min(occurrences, 3)
        if term_score > 0:
            score += term_score
            if term not in seen and len(matched_terms) < _MAX_MATCHED_TERMS:
                matched_terms.append(term)
                seen.add(term)
    return score, matched_terms


def _outputs_text(outputs: list[Any]) -> str:
    parts: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        parts.extend(
            str(value)
            for value in (item.get("kind"), item.get("ref"), item.get("title"))
            if value
        )
    return " ".join(parts)


def _compact_case(
    case: dict[str, Any],
    score: float,
    case_number: int,
    matched_terms: list[str],
) -> dict[str, Any]:
    distilled = case.get("distilled") if isinstance(case.get("distilled"), dict) else {}
    brief = (
        distilled.get("case_brief")
        or case.get("summary")
        or ""
    )
    compact = {
        "case_ref": f"case_{case_number}",
        "execution_id": case.get("execution_id"),
        "status": case.get("status"),
        "started_at": case.get("started_at"),
        "duration_seconds": case.get("duration_seconds"),
        "trigger": case.get("trigger") or {},
        "case_brief": str(brief)[:200],
        "findings": [str(item)[:120] for item in (distilled.get("findings") or [])[:5]],
        "outputs": (case.get("outputs") or [])[:5],
        "errors": [str(item)[:200] for item in (case.get("errors") or [])[:3]],
        "score": round(score, 2),
        "matched_terms": matched_terms,
    }
    return {key: value for key, value in compact.items() if value not in (None, [], {})}


def _extract_terms(query: str) -> list[str]:
    text = str(query or "").strip()
    if not text:
        return []

    terms: list[str] = []
    seen = set()

    def add(value: str) -> None:
        normalized = value.strip()
        if len(normalized) < 2:
            return
        key = normalized.lower()
        if key in seen:
            return
        terms.append(normalized)
        seen.add(key)

    add(text)
    for token in re.findall(r"[A-Za-z]{1,5}\d+(?:\.\d+)?|[A-Za-z]{2,}|\d+(?:\.\d+)?", text):
        add(token.upper() if re.search(r"\d", token) else token.lower())

    for segment in re.findall(r"[\u4e00-\u9fa5]{2,}", text):
        add(segment)
        for width in (4, 3, 2):
            if len(segment) <= width:
                continue
            for index in range(0, len(segment) - width + 1):
                add(segment[index:index + width])

    stopwords = {"这个", "那个", "是否", "需要", "历史", "案例", "查询", "检索"}
    return [term for term in terms if term not in stopwords][:24]


def _normalize_filter(value: str | None, allowed: set[str]) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized or normalized == "any":
        return None
    return normalized if normalized in allowed else None


def _parse_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        suffix = "T23:59:59" if end_of_day else "T00:00:00"
        text = text + suffix
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _started_timestamp(case: dict[str, Any]) -> float:
    started = _parse_datetime(case.get("started_at"))
    if started is None:
        return 0.0
    return started.timestamp()
