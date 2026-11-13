"""Append-only feedback ledger for work order audit self-iteration.

The ledger is the single source of retrospective signal for the ops audit
self-iteration loop (design doc: ``backend/docs/design/ops-audit-self-iteration.md``).
Every human or automated judgement about audit output is appended here as one
JSON line, tagged by channel, so the monthly retrospective can aggregate
overthrow rates, missed issues and data drift without reparsing audit
artifacts themselves.

Channels:

- ``panel``: per-item include/exclude decisions from the human feedback panel.
- ``checklist``: reconciled user-submitted checklists (phase 1 step 2).
- ``db_recheck``: deterministic re-query triage run by the retrospective stats
  layer (phase 1 step 3).

A ``rule_id`` of ``null`` is meaningful: the signal is not covered by the
current rule catalog and is a candidate-new-rule hint for the retrospective.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.utils.path_config import get_memory_dir

logger = logging.getLogger(__name__)

LEDGER_SCHEMA_VERSION = "ops_audit_feedback_ledger.v1"
LEDGER_FILENAME = "feedback_ledger.jsonl"
METRICS_HISTORY_FILENAME = "metrics_history.jsonl"
METRICS_HISTORY_SCHEMA_VERSION = "ops_audit_metrics_history.v1"

PANEL_CHANNEL = "panel"
CHECKLIST_CHANNEL = "checklist"
DB_RECHECK_CHANNEL = "db_recheck"
CHANNELS = frozenset({PANEL_CHANNEL, CHECKLIST_CHANNEL, DB_RECHECK_CHANNEL})

OUTCOME_CONFIRMED = "confirmed"
OUTCOME_REJECTED = "rejected"
OUTCOME_MISSED = "missed"
OUTCOME_TACIT_CONFIRMED = "tacit_confirmed"
OUTCOME_VERIFIED = "verified"
OUTCOME_DATA_DRIFTED = "data_drifted"
OUTCOME_EVIDENCE_MISMATCH = "evidence_mismatch"
OUTCOMES = frozenset(
    {
        OUTCOME_CONFIRMED,
        OUTCOME_REJECTED,
        OUTCOME_MISSED,
        OUTCOME_TACIT_CONFIRMED,
        OUTCOME_VERIFIED,
        OUTCOME_DATA_DRIFTED,
        OUTCOME_EVIDENCE_MISMATCH,
    }
)

MAX_REASON_LENGTH = 2000


def default_ledger_path() -> Path:
    """The ledger lives beside the audit artifacts under the ops memory dir."""

    return get_memory_dir() / "ops" / "audit" / "ledger" / LEDGER_FILENAME


def default_metrics_history_path() -> Path:
    """Time-series of computed audit metrics, one JSON line per computation."""

    return default_ledger_path().parent / METRICS_HISTORY_FILENAME


def append_metrics_history(
    entry: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one metrics snapshot (reconciliation or monthly retrospective)."""

    record = {
        "schema_version": METRICS_HISTORY_SCHEMA_VERSION,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        **entry,
    }
    target = path or default_metrics_history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_metrics_history(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Read the metrics time-series, skipping malformed lines."""

    target = path or default_metrics_history_path()
    if not target.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def derive_execution_ref(path: str | Path) -> str | None:
    """Extract ``<task_id>/<execution_id>`` from a scheduled-task output path.

    Scheduled executions isolate artifacts under
    ``<registry>/scheduled_tasks/executions/{task_id}/{execution_id}/ops_audit``;
    interactive runs stay in the shared audit directory and carry no execution
    reference.
    """

    parts = [part for part in Path(path).parts if part]
    for index, part in enumerate(parts):
        if part == "scheduled_tasks" and parts[index + 1 : index + 2] == ["executions"]:
            if len(parts) > index + 3:
                return f"{parts[index + 2]}/{parts[index + 3]}"
    return None


def normalize_record(
    raw: dict[str, Any],
    *,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize one ledger record before it is appended."""

    channel = str(raw.get("channel") or "").strip()
    if channel not in CHANNELS:
        raise ValueError(f"invalid feedback ledger channel: {channel!r}")
    outcome = str(raw.get("outcome") or "").strip()
    if outcome not in OUTCOMES:
        raise ValueError(f"invalid feedback ledger outcome: {outcome!r}")
    order_code = _optional_str(raw.get("order_code"))
    if not order_code:
        raise ValueError("feedback ledger record requires order_code")
    reason = str(raw.get("reason") or "").strip()
    reviewer = raw.get("reviewer")
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "recorded_at": recorded_at or datetime.now().isoformat(timespec="seconds"),
        "channel": channel,
        "outcome": outcome,
        "explicit": bool(raw.get("explicit", True)),
        "order_code": order_code,
        "rule_id": _optional_str(raw.get("rule_id")),
        "issue_id": _optional_str(raw.get("issue_id")),
        "item_id": _optional_str(raw.get("item_id")),
        "execution_ref": _optional_str(raw.get("execution_ref")),
        "station_id": _optional_str(raw.get("station_id")),
        "original_judgment": _optional_str(raw.get("original_judgment")),
        "reason": reason[:MAX_REASON_LENGTH] or None,
        "feedback_id": _optional_str(raw.get("feedback_id")),
        "reviewer": reviewer if isinstance(reviewer, dict) and reviewer else None,
        "source_ref": _optional_str(raw.get("source_ref")),
        "snapshot_ref": _optional_str(raw.get("snapshot_ref")),
    }


def append_records(
    records: Iterable[dict[str, Any]],
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Append validated records as JSON lines and return what was written."""

    prepared = [normalize_record(record) for record in records]
    if not prepared:
        return []
    target = path or default_ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for record in prepared:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return prepared


def read_records(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Read the ledger, skipping blank or malformed lines with a warning."""

    target = path or default_ledger_path()
    if not target.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        target.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            logger.warning(
                "skipping malformed feedback ledger line %s in %s", line_number, target
            )
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def query_records(
    *,
    path: Path | None = None,
    channel: str | None = None,
    outcome: str | None = None,
    rule_id: str | None = None,
    order_code: str | None = None,
    execution_ref: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Filter ledger records; ``since`` compares ISO ``recorded_at`` prefixes."""

    records = read_records(path=path)
    result = records
    if channel is not None:
        result = [record for record in result if record.get("channel") == channel]
    if outcome is not None:
        result = [record for record in result if record.get("outcome") == outcome]
    if rule_id is not None:
        result = [record for record in result if record.get("rule_id") == rule_id]
    if order_code is not None:
        result = [record for record in result if record.get("order_code") == order_code]
    if execution_ref is not None:
        result = [record for record in result if record.get("execution_ref") == execution_ref]
    if since is not None:
        result = [
            record
            for record in result
            if str(record.get("recorded_at") or "") >= since
        ]
    return result


def aggregate_by_rule(
    records: Iterable[dict[str, Any]],
    *,
    channel: str | None = None,
) -> dict[str | None, dict[str, int]]:
    """Count outcomes per ``rule_id`` (``None`` = catalog-uncovered signal)."""

    counts: dict[str | None, Counter[str]] = defaultdict(Counter)
    for record in records:
        if channel is not None and record.get("channel") != channel:
            continue
        counts[record.get("rule_id")][str(record.get("outcome"))] += 1
    return {rule_id: dict(counter) for rule_id, counter in counts.items()}


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
