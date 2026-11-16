"""Monthly retrospective statistics and DB recheck triage (phase 1 step 3).

The retrospective has two layers (design doc §6): a deterministic stats layer
(this module — the code counts, never the LLM) and a narrative layer (the
``ops_audit_retrospective`` skill turns the stats JSON into a markdown report).

The DB recheck (channel 3) re-fetches the current source data for ledger
``rejected`` items and re-runs the deterministic rules, triaging each record:

- ``verified``        source data unchanged and the rule reproduces the issue
                      -> the rejection is a pure calibration (口径) question;
- ``data_drifted``    source data changed post-hoc (order edited / backfilled)
                      -> a data-pipeline problem, NOT a rule problem;
- ``evidence_mismatch`` data unchanged yet the rule no longer reproduces the
                      issue -> rule implementation bug signal.

The triage compares a per-order fingerprint of the archived dataset (kept
beside the final issue list) against a fresh fetch, falling back to re-run-only
triage when no archived dataset survives.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from app.services.ops_audit import feedback_ledger
from app.utils.path_config import get_memory_dir

logger = logging.getLogger(__name__)

STATS_SCHEMA_VERSION = "ops_audit_retrospective_stats.v1"
RECHECK_SCHEMA_VERSION = "ops_audit_db_recheck.v1"
DEFAULT_ROLLING_WEEKS = 8
_CODE_KEYS = ("working_order_code", "order_code", "WORKINGORDERCODE")


# --------------------------------------------------------------------------
# period helpers
# --------------------------------------------------------------------------

def resolve_month(month: str | None, *, today: date | None = None) -> str:
    """Normalize ``YYYY-MM``; default to the previous natural month."""

    if month:
        text = month.strip()
        if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:].isdigit():
            return text
        raise ValueError(f"month must look like YYYY-MM, got {month!r}")
    today = today or date.today()
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    return f"{last_month_end.year:04d}-{last_month_end.month:02d}"


def month_bounds(month: str) -> tuple[str, str]:
    """Inclusive start / exclusive end ISO timestamps for ``recorded_at``."""

    year, mon = int(month[:4]), int(month[5:7])
    start = datetime(year, mon, 1)
    end = datetime(year + 1, 1, 1) if mon == 12 else datetime(year, mon + 1, 1)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# stats layer
# --------------------------------------------------------------------------

def build_retrospective_stats(
    *,
    month: str | None = None,
    records: list[dict[str, Any]] | None = None,
    metrics_history: list[dict[str, Any]] | None = None,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    today: date | None = None,
) -> dict[str, Any]:
    """Aggregate the ledger + metrics time-series into the stats JSON.

    Pure function (data injected); the caller decides what to persist.
    """

    resolved = resolve_month(month, today=today)
    start, end = month_bounds(resolved)
    all_records = records if records is not None else feedback_ledger.read_records()
    period_records = [
        record
        for record in all_records
        if start <= str(record.get("recorded_at") or "") < end
    ]

    counts = _channel_outcome_counts(period_records)
    checklist_metrics = _checklist_metrics(
        period_records,
        history=metrics_history
        if metrics_history is not None
        else feedback_ledger.read_metrics_history(),
        start=start,
        end=end,
    )
    panel_metrics = _panel_metrics(period_records)
    return {
        "schema_version": STATS_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "month": resolved,
        "period_start": start,
        "period_end": end,
        "record_count": len(period_records),
        "counts_by_channel_outcome": counts,
        "checklist_metrics": checklist_metrics,
        "panel_metrics": panel_metrics,
        "by_rule": _by_rule(period_records),
        "candidate_new_rules": _candidate_new_rules(period_records),
        "calibration": _calibration(period_records),
        "rolling": _rolling(all_records, weeks=rolling_weeks, today=today),
    }


def _channel_outcome_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        counts[str(record.get("channel"))][str(record.get("outcome"))] += 1
    return {channel: dict(counter) for channel, counter in sorted(counts.items())}


def _checklist_metrics(
    period_records: list[dict[str, Any]],
    *,
    history: list[dict[str, Any]],
    start: str,
    end: str,
) -> dict[str, Any]:
    """Identification rate over all checklists; error rate only over full ones.

    Per-reconciliation gating comes from the metrics time-series (written at
    reconciliation time); a ledger-only fallback keeps the stats honest when
    the history entry is missing.
    """

    entries = [
        entry
        for entry in history
        if entry.get("kind") == "checklist_reconciliation"
        and start <= str(entry.get("recorded_at") or "") < end
    ]
    identified_num = identified_den = 0
    error_num = error_den = 0
    full_declared_seen = False
    for entry in entries:
        metrics = entry.get("metrics") or {}
        identification = metrics.get("identification_rate") or {}
        identified_num += int(identification.get("numerator") or 0)
        identified_den += int(identification.get("denominator") or 0)
        if entry.get("full_review_declared"):
            full_declared_seen = True
            error = metrics.get("error_rate") or {}
            error_num += int(error.get("numerator") or 0)
            error_den += int(error.get("denominator") or 0)
    if not entries:
        outcomes = Counter(
            str(record.get("outcome"))
            for record in period_records
            if record.get("channel") == feedback_ledger.CHECKLIST_CHANNEL
        )
        identified_num = outcomes[feedback_ledger.OUTCOME_CONFIRMED]
        identified_den = (
            outcomes[feedback_ledger.OUTCOME_CONFIRMED] + outcomes[feedback_ledger.OUTCOME_MISSED]
        )
        full_declared_seen = outcomes[feedback_ledger.OUTCOME_TACIT_CONFIRMED] > 0
        if full_declared_seen:
            error_num = outcomes[feedback_ledger.OUTCOME_REJECTED]
            error_den = (
                outcomes[feedback_ledger.OUTCOME_CONFIRMED]
                + outcomes[feedback_ledger.OUTCOME_REJECTED]
                + outcomes[feedback_ledger.OUTCOME_TACIT_CONFIRMED]
            )
    return {
        "source": "metrics_history" if entries else "ledger_fallback",
        "reconciliation_count": len(entries),
        "identification_rate": _metric(
            "清单识别率", identified_num, identified_den, applicable=True
        ),
        "error_rate": _metric(
            "清单错误率",
            error_num,
            error_den,
            applicable=full_declared_seen and error_den > 0,
            inapplicable_text="清单错误率：不适用（本月无全量核对声明的对账）",
        ),
    }


def _panel_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(
        str(record.get("outcome"))
        for record in records
        if record.get("channel") == feedback_ledger.PANEL_CHANNEL
    )
    confirmed = outcomes[feedback_ledger.OUTCOME_CONFIRMED]
    rejected = outcomes[feedback_ledger.OUTCOME_REJECTED]
    return {
        "panel_confirm_rate": _metric("面板确认率", confirmed, confirmed + rejected, applicable=True),
        "panel_exclude_rate": _metric("面板排除率", rejected, confirmed + rejected, applicable=True),
    }


def _by_rule(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-rule outcome counts and human overturn rate; null rule last."""

    explicit = [
        record
        for record in records
        if record.get("channel") in {feedback_ledger.PANEL_CHANNEL, feedback_ledger.CHECKLIST_CHANNEL}
        and record.get("outcome")
        in {feedback_ledger.OUTCOME_CONFIRMED, feedback_ledger.OUTCOME_REJECTED}
        and record.get("explicit", True)
    ]
    counts: dict[object, Counter[str]] = defaultdict(Counter)
    for record in explicit:
        counts[record.get("rule_id")][str(record.get("outcome"))] += 1
    rows: list[dict[str, Any]] = []
    for rule_id, counter in sorted(counts.items(), key=lambda item: (item[0] is None, -sum(item[1].values()))):
        confirmed = counter[feedback_ledger.OUTCOME_CONFIRMED]
        rejected = counter[feedback_ledger.OUTCOME_REJECTED]
        rows.append(
            {
                "rule_id": rule_id,
                "confirmed": confirmed,
                "rejected": rejected,
                "overturn_rate": _ratio(rejected, rejected + confirmed),
                "overturn_text": _ratio_text("人工推翻率", rejected, rejected + confirmed),
            }
        )
    return rows


def _candidate_new_rules(records: list[dict[str, Any]]) -> dict[str, Any]:
    missed = [
        record
        for record in records
        if record.get("outcome") == feedback_ledger.OUTCOME_MISSED
        and record.get("rule_id") in (None, "")
    ]
    samples = [
        {
            "order_code": record.get("order_code"),
            "reason": record.get("reason"),
            "channel": record.get("channel"),
            "recorded_at": record.get("recorded_at"),
        }
        for record in missed[:20]
    ]
    return {
        "missed_without_rule_count": len(missed),
        "note": "rule_id=null 的 missed 信号是候选新规则证据（设计文档 §3 通道2）。"
        if missed
        else None,
        "samples": samples,
    }


def _calibration(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """original_judgment x outcome cross-tab as the calibration proxy."""

    cross: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        judgment = str(record.get("original_judgment") or "unknown")
        cross[judgment][str(record.get("outcome"))] += 1
    return [
        {"original_judgment": judgment, "outcomes": dict(counter), "total": sum(counter.values())}
        for judgment, counter in sorted(cross.items(), key=lambda item: -sum(item[1].values()))
    ]


def _rolling(
    records: list[dict[str, Any]], *, weeks: int, today: date | None
) -> dict[str, Any]:
    """Cumulative ratios over the last N ISO weeks containing signal."""

    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    week_starts = [(monday - timedelta(weeks=offset)) for offset in range(weeks)]
    window_start = week_starts[-1].isoformat()
    checklist = Counter()
    panel = Counter()
    for record in records:
        recorded = str(record.get("recorded_at") or "")[:10]
        if not recorded or recorded < window_start:
            continue
        outcome = str(record.get("outcome"))
        if record.get("channel") == feedback_ledger.CHECKLIST_CHANNEL:
            checklist[outcome] += 1
        elif record.get("channel") == feedback_ledger.PANEL_CHANNEL:
            panel[outcome] += 1
    confirmed = checklist[feedback_ledger.OUTCOME_CONFIRMED]
    missed = checklist[feedback_ledger.OUTCOME_MISSED]
    panel_confirmed = panel[feedback_ledger.OUTCOME_CONFIRMED]
    panel_rejected = panel[feedback_ledger.OUTCOME_REJECTED]
    return {
        "window_weeks": weeks,
        "window_start": window_start,
        "window_end": monday.isoformat(),
        "checklist_identification_rate": _metric(
            "滚动识别率", confirmed, confirmed + missed, applicable=True
        ),
        "panel_exclude_rate": _metric(
            "滚动面板排除率", panel_rejected, panel_confirmed + panel_rejected, applicable=True
        ),
    }


def _metric(
    label: str, numerator: int, denominator: int, *, applicable: bool, inapplicable_text: str | None = None
) -> dict[str, Any]:
    if applicable and denominator > 0:
        text = _ratio_text(label, numerator, denominator)
    else:
        text = inapplicable_text or f"{label}：暂不可算（0 个样本）"
    return {
        "applicable": bool(applicable and denominator > 0),
        "numerator": numerator,
        "denominator": denominator,
        "ratio": _ratio(numerator, denominator) if applicable else None,
        "text": text,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator > 0 else None


def _ratio_text(label: str, numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return f"{label}：暂不可算（0 个样本）"
    return f"{label}：{round(numerator * 100 / denominator)}%（{numerator}/{denominator}）"


# --------------------------------------------------------------------------
# channel 3: DB recheck triage
# --------------------------------------------------------------------------

def eligible_recheck_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ledger rejected items that a deterministic re-run can triage."""

    return [
        record
        for record in records
        if record.get("outcome") == feedback_ledger.OUTCOME_REJECTED
        and str(record.get("order_code") or "").strip()
        and str(record.get("rule_id") or "").strip()
    ]


def run_db_recheck(
    records: list[dict[str, Any]],
    *,
    month: str,
    fetch_and_run: Callable[[list[str]], dict[str, Any]] | None = None,
    baseline_dataset_for: Callable[[dict[str, Any]], Path | None] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Triage rejected ledger records against a fresh fetch + rule re-run.

    ``fetch_and_run`` (injectable for tests) receives the distinct order codes
    and returns ``{"issues": [...], "dataset": {...}, "dataset_orders": set}``;
    the production default re-fetches via the audit dataset pipeline and runs
    the non-visual rules.  Triage rows and projected db_recheck ledger records
    are returned — persistence is the caller's decision.
    """

    targets = eligible_recheck_records(records)
    if not targets:
        return {
            "schema_version": RECHECK_SCHEMA_VERSION,
            "month": month,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "eligible_count": 0,
            "order_codes": [],
            "counts": {},
            "triage": [],
            "ledger_records": [],
            "skipped": [
                {"order_code": record.get("order_code"), "reason": "missing rule_id"}
                for record in records
                if record.get("outcome") == feedback_ledger.OUTCOME_REJECTED
                and str(record.get("order_code") or "").strip()
                and not str(record.get("rule_id") or "").strip()
            ],
        }

    fetch_and_run = fetch_and_run or _default_fetch_and_run
    baseline_dataset_for = baseline_dataset_for or _baseline_dataset_beside_source
    codes = sorted({str(record["order_code"]).strip() for record in targets})
    fresh = fetch_and_run(codes)
    fresh_issues = _index_fresh_issues(fresh.get("issues") or [])
    reported_orders = fresh.get("dataset_orders")
    # An explicit empty set means the orders are gone from the source; only an
    # omitted key falls back to assuming every requested code came back.
    fresh_orders = (
        {str(code) for code in codes}
        if reported_orders is None
        else {str(code) for code in reported_orders}
    )
    fresh_dataset = fresh.get("dataset") if isinstance(fresh.get("dataset"), dict) else {}

    triage: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    feedback_id = f"db_recheck:{month}"
    for record in targets:
        code = str(record["order_code"]).strip()
        rule_id = str(record["rule_id"]).strip()
        row, outcome, reason = _triage_one(
            record,
            code=code,
            rule_id=rule_id,
            fresh_issues=fresh_issues.get((code, rule_id), []),
            order_returned=code in fresh_orders,
            fresh_fingerprint=_order_fingerprint(fresh_dataset, code),
            baseline_fingerprint=_baseline_fingerprint(record, baseline_dataset_for, code),
        )
        triage.append(row)
        ledger_records.append(
            {
                "channel": feedback_ledger.DB_RECHECK_CHANNEL,
                "outcome": outcome,
                "explicit": False,
                "order_code": code,
                "rule_id": rule_id,
                "issue_id": record.get("issue_id"),
                "item_id": record.get("item_id"),
                "execution_ref": record.get("execution_ref"),
                "station_id": record.get("station_id"),
                "original_judgment": record.get("original_judgment"),
                "reason": reason,
                "feedback_id": feedback_id,
                "reviewer": None,
                "source_ref": record.get("source_ref"),
                "snapshot_ref": record.get("snapshot_ref"),
            }
        )

    result = {
        "schema_version": RECHECK_SCHEMA_VERSION,
        "month": month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "eligible_count": len(targets),
        "order_codes": codes,
        "triage": triage,
        "ledger_records": ledger_records,
        "skipped": [
            {"order_code": record.get("order_code"), "reason": "missing rule_id"}
            for record in records
            if record.get("outcome") == feedback_ledger.OUTCOME_REJECTED
            and str(record.get("order_code") or "").strip()
            and not str(record.get("rule_id") or "").strip()
        ],
        "counts": dict(Counter(str(row["outcome"]) for row in triage)),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"db_recheck_{month}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["archive_path"] = str(target)
    return result


def _triage_one(
    record: dict[str, Any],
    *,
    code: str,
    rule_id: str,
    fresh_issues: list[dict[str, Any]],
    order_returned: bool,
    fresh_fingerprint: str | None,
    baseline_fingerprint: str | None,
) -> tuple[dict[str, Any], str, str]:
    fresh_messages = sorted(
        str(issue.get("message") or "") for issue in fresh_issues
    )
    row: dict[str, Any] = {
        "order_code": code,
        "rule_id": rule_id,
        "recorded_at": record.get("recorded_at"),
        "fresh_messages": fresh_messages,
        "baseline_fingerprint": baseline_fingerprint,
        "fresh_fingerprint": fresh_fingerprint,
    }
    if not order_returned:
        outcome = feedback_ledger.OUTCOME_DATA_DRIFTED
        reason = "回库重取未返回该工单（工单被删/状态变更），属数据管道口径变化。"
    elif baseline_fingerprint and fresh_fingerprint:
        if baseline_fingerprint != fresh_fingerprint:
            outcome = feedback_ledger.OUTCOME_DATA_DRIFTED
            reason = "基线与回库数据指纹不一致：工单事后被修改或补录，属数据管道问题而非规则问题。"
        elif fresh_issues:
            outcome = feedback_ledger.OUTCOME_VERIFIED
            reason = "源数据未变且规则复现原判定：排除属口径/校准问题。"
        else:
            outcome = feedback_ledger.OUTCOME_EVIDENCE_MISMATCH
            reason = "源数据未变但规则不再命中原判定：规则实现 bug 信号。"
    else:
        # No archived baseline survived: triage by re-run only, honestly labelled.
        if fresh_issues:
            outcome = feedback_ledger.OUTCOME_VERIFIED
            reason = "无基线数据集，按复跑结果分诊：规则复现原判定，排除属口径/校准问题。"
        else:
            outcome = feedback_ledger.OUTCOME_EVIDENCE_MISMATCH
            reason = "无基线数据集，按复跑结果分诊：规则未复现原判定，需人工核对规则实现。"
    row["outcome"] = outcome
    row["reason"] = reason
    return row, outcome, reason


def _default_fetch_and_run(codes: list[str]) -> dict[str, Any]:
    """Production fetch: fresh dataset + deterministic non-visual re-run.

    Deliberately calls ``audit_dataset`` instead of the full rule-engine
    pipeline: the recheck is a deterministic evidence comparison and must not
    spend semantic-review LLM calls.  Output goes to an isolated recheck dir so
    the live ``latest_*`` audit artifacts are never clobbered.
    """

    from app.services.ops_work_order_audit import (
        OpsWorkOrderAuditConfig,
        fetch_ops_audit_dataset,
    )
    from app.services.ops_work_order_audit_engine import audit_dataset

    output_dir = get_memory_dir() / "ops" / "audit" / "recheck"
    fetch = fetch_ops_audit_dataset(
        OpsWorkOrderAuditConfig(
            limit=max(50, min(len(codes) * 2, 3000)),
            audit_window_preset=None,
            working_order_codes=list(codes),
            order_statuses=None,
            evidence_level="summary",
            output_dir=output_dir,
        )
    )
    dataset = json.loads(Path(str(fetch["dataset_path"])).read_text(encoding="utf-8"))
    audit = audit_dataset(dataset, enable_visual=False, enable_non_visual=True)
    # scoring_issue dicts carry no order code of their own; stamp it from the record.
    issues = [
        {**issue, "working_order_code": audit_record.get("working_order_code")}
        for audit_record in audit.get("records", [])
        for issue in audit_record.get("scoring_issues", [])
    ]
    return {
        "issues": issues,
        "dataset": dataset,
        "dataset_orders": {
            str(order.get("working_order_code") or order.get("WORKINGORDERCODE") or "")
            for order in dataset.get("orders", [])
        }
        - {""},
    }


def _baseline_dataset_beside_source(record: dict[str, Any]) -> Path | None:
    source_ref = str(record.get("source_ref") or "").strip()
    if not source_ref:
        return None
    candidate = Path(source_ref).parent / "latest_finished_work_orders_dataset.json"
    return candidate if candidate.is_file() else None


def _baseline_fingerprint(
    record: dict[str, Any],
    baseline_dataset_for: Callable[[dict[str, Any]], Path | None],
    code: str,
) -> str | None:
    baseline_path = baseline_dataset_for(record)
    if baseline_path is None:
        return None
    try:
        dataset = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _order_fingerprint(dataset, code)


def _index_fresh_issues(issues: list[Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("working_order_code") or "").strip()
        rule_id = str(issue.get("rule_id") or "").strip()
        if code and rule_id:
            index[(code, rule_id)].append(issue)
    return index


def _item_code(item: dict[str, Any]) -> str | None:
    for key in _CODE_KEYS:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def _order_fingerprint(dataset: dict[str, Any], order_code: str) -> str | None:
    """Stable fingerprint of one order across dataset slices.

    Pipeline-generated whole-dataset keys (query_info / audit window) are
    excluded; per-record business fields are kept verbatim so a post-hoc edit
    shows up as a fingerprint change.
    """

    payload: dict[str, Any] = {}
    for key, value in dataset.items():
        if key in {"query_info", "audit_window"}:
            continue
        if isinstance(value, list):
            matched = [
                item for item in value if isinstance(item, dict) and _item_code(item) == order_code
            ]
            if matched:
                payload[key] = matched
        elif isinstance(value, dict):
            sub = value.get(order_code)
            if sub is not None:
                payload[key] = sub
    if not payload:
        return None
    normalized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )
    return sha256(normalized.encode("utf-8")).hexdigest()
