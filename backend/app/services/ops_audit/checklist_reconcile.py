"""Channel-2 checklist reconciliation for the ops audit self-iteration loop.

Users cross-check the audit result offline and submit a problem checklist
(Excel/Word/text, uploaded in an ops session).  The signal is not the raw
checklist but the *reconciliation* against the audit output of the same
period — every checklist row is joined deterministically on
``(order_code, problem category)`` against the final issue list, and each
pair is classified into the ledger outcomes defined by the design doc
(``backend/docs/ops-audit-self-iteration.md`` §3 通道2):

    checklist says problem  + audit reported same type  -> confirmed
    checklist says problem  + audit reported nothing     -> missed (rule_id=null)
    checklist says ok       + audit reported a problem   -> rejected
    checklist silent        + audit reported a problem   -> tacit_confirmed
                             (only under a full-review declaration)
    checklist silent        + audit reported a problem   -> not recorded (partial)
    order code outside the audited dataset               -> unmatched (echo only)

Semantic matching is deliberately NOT used for the join: a wrong join count
corrupts every downstream metric.  Category normalization from free text is
the agent's job (guided by the ``ops_audit_retrospective`` skill); this module
only accepts already-normalized items and rejects unknown categories with the
valid vocabulary in the error message.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.services.ops_audit import feedback_ledger
from app.services.ops_audit.config import load_rule_catalog
from app.services.ops_audit.final_issue_list import ensure_issue_ids
from app.services.ops_audit.review_artifacts import issue_list_sha256

VERDICT_PROBLEM = "problem"
VERDICT_OK = "ok"
CHECKLIST_VERDICTS = frozenset({VERDICT_PROBLEM, VERDICT_OK})

MAX_NOTE_LENGTH = 2000
RECONCILIATION_SCHEMA_VERSION = "ops_audit_checklist_reconciliation.v1"


def catalog_categories() -> frozenset[str]:
    """The controlled problem-category vocabulary (rule catalog categories)."""

    return frozenset(
        str(rule.get("category")).strip()
        for rule in load_rule_catalog()
        if str(rule.get("category") or "").strip()
    )


def rule_category_index() -> dict[str, str]:
    """Map ``rule_id`` -> catalog category for issue items missing one."""

    return {
        str(rule.get("id")): str(rule.get("category"))
        for rule in load_rule_catalog()
        if rule.get("id") and rule.get("category")
    }


def normalize_checklist_items(raw_items: list[Any]) -> list[dict[str, Any]]:
    """Validate and normalize agent-structured checklist items.

    Each item: ``order_code`` (required), ``verdict`` (``problem``/``ok``),
    optional ``problem_category`` (must be a catalog category) and ``note``
    (the user's original wording, kept verbatim for the ledger).
    """

    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("checklist_items must be a non-empty list")
    valid_categories = catalog_categories()
    normalized: list[dict[str, Any]] = []
    seen_orders: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"checklist item {index} must be an object")
        order_code = str(raw.get("order_code") or raw.get("working_order_code") or "").strip()
        if not order_code:
            raise ValueError(f"checklist item {index} requires order_code")
        verdict = str(raw.get("verdict") or "").strip().lower()
        if verdict == "有问题":
            verdict = VERDICT_PROBLEM
        elif verdict == "没问题":
            verdict = VERDICT_OK
        if verdict not in CHECKLIST_VERDICTS:
            raise ValueError(
                f"checklist item {index} ({order_code}): verdict must be "
                f"'{VERDICT_PROBLEM}'(说有问题) or '{VERDICT_OK}'(说没问题), got {verdict!r}"
            )
        category = str(raw.get("problem_category") or raw.get("category") or "").strip() or None
        if category is not None and category not in valid_categories:
            raise ValueError(
                f"checklist item {index} ({order_code}): unknown problem_category "
                f"{category!r}; valid categories: {', '.join(sorted(valid_categories))}"
            )
        note = str(raw.get("note") or raw.get("problem_text") or "").strip()
        key = (order_code, verdict, category or "")
        if key in seen_orders:
            raise ValueError(
                f"duplicate checklist item: {order_code} {verdict} {category or '(任意类型)'}"
            )
        seen_orders.add(key)
        normalized.append(
            {
                "item_id": f"chk-{index:03d}",
                "order_code": order_code,
                "verdict": verdict,
                "problem_category": category,
                "note": note[:MAX_NOTE_LENGTH] or None,
            }
        )
    return normalized


def reconcile_checklist(
    final_issue_list: dict[str, Any],
    checklist_items: list[dict[str, Any]],
    *,
    full_review_declared: bool,
    reviewer: dict[str, Any] | None = None,
    dataset_orders: set[str] | None = None,
    final_issue_list_path: Path | None = None,
) -> dict[str, Any]:
    """Classify every (checklist row x audit issue) pair per the design matrix.

    Returns the classification rows, projected ledger records, metrics (with
    the full-declaration gating for the error rate) and session echo lines.
    Pure function: no ledger writes, no filesystem access.
    """

    items = normalize_checklist_items(checklist_items)
    ensure_issue_ids(final_issue_list)
    execution_ref = (
        feedback_ledger.derive_execution_ref(final_issue_list_path)
        if final_issue_list_path
        else None
    )
    source_ref = str(final_issue_list_path) if final_issue_list_path else None
    category_of = rule_category_index()
    issues_by_order: dict[str, list[dict[str, Any]]] = {}
    for issue in final_issue_list.get("items", []):
        code = str(issue.get("working_order_code") or "").strip()
        if not code:
            continue
        issue = dict(issue)
        issue["category"] = (
            str(issue.get("category") or "").strip()
            or category_of.get(str(issue.get("rule_id") or ""), "")
        )
        issues_by_order.setdefault(code, []).append(issue)

    classifications: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    matched_issue_ids: set[str] = set()
    snapshot_ref = issue_list_sha256(final_issue_list)
    reconciliation_id = _reconciliation_id(snapshot_ref, items, full_review_declared)

    for item in items:
        order_issues = issues_by_order.get(item["order_code"], [])
        if item["problem_category"]:
            matching = [
                issue for issue in order_issues if issue.get("category") == item["problem_category"]
            ]
        else:
            matching = list(order_issues)

        if item["verdict"] == VERDICT_PROBLEM:
            if matching:
                for issue in matching:
                    matched_issue_ids.add(str(issue["issue_id"]))
                    classifications.append(
                        _classification(
                            item,
                            issue,
                            feedback_ledger.OUTCOME_CONFIRMED,
                            "清单说有问题，审核已报同类问题。",
                        )
                    )
                    ledger_records.append(
                        _ledger_record(
                            item,
                            issue,
                            feedback_ledger.OUTCOME_CONFIRMED,
                            reconciliation_id=reconciliation_id,
                            snapshot_ref=snapshot_ref,
                            reviewer=reviewer,
                            execution_ref=execution_ref,
                            source_ref=source_ref,
                        )
                    )
            else:
                in_dataset = dataset_orders is None or item["order_code"] in dataset_orders
                if in_dataset:
                    note = "清单说有问题，审核未报（候选新规则/漏报）。"
                    if order_issues:
                        note += " 该单报了其他类型问题，但无同类问题。"
                    classifications.append(_classification(item, None, feedback_ledger.OUTCOME_MISSED, note))
                    ledger_records.append(
                        _ledger_record(
                            item,
                            None,
                            feedback_ledger.OUTCOME_MISSED,
                            reconciliation_id=reconciliation_id,
                            snapshot_ref=snapshot_ref,
                            reviewer=reviewer,
                            execution_ref=execution_ref,
                            source_ref=source_ref,
                        )
                    )
                else:
                    classifications.append(
                        _classification(
                            item, None, "unmatched", "工单号不在当期审核数据集内，无法对账（仅回显）。"
                        )
                    )
        else:  # verdict == VERDICT_OK
            if matching:
                for issue in matching:
                    matched_issue_ids.add(str(issue["issue_id"]))
                    classifications.append(
                        _classification(
                            item,
                            issue,
                            feedback_ledger.OUTCOME_REJECTED,
                            "清单说没问题，审核报了问题（误报信号）。",
                        )
                    )
                    ledger_records.append(
                        _ledger_record(
                            item,
                            issue,
                            feedback_ledger.OUTCOME_REJECTED,
                            reconciliation_id=reconciliation_id,
                            snapshot_ref=snapshot_ref,
                            reviewer=reviewer,
                            execution_ref=execution_ref,
                            source_ref=source_ref,
                        )
                    )
            else:
                classifications.append(
                    _classification(item, None, "agreement", "清单说没问题，审核也未报，无信号不入账。")
                )

    mentioned_orders = {item["order_code"] for item in items}
    for code, order_issues in issues_by_order.items():
        for issue in order_issues:
            issue_id = str(issue["issue_id"])
            if issue_id in matched_issue_ids:
                continue
            if full_review_declared:
                classifications.append(
                    {
                        "item_id": None,
                        "order_code": code,
                        "verdict": None,
                        "problem_category": issue.get("category") or None,
                        "matched_issue_ids": [issue_id],
                        "outcome": feedback_ledger.OUTCOME_TACIT_CONFIRMED,
                        "ledger": True,
                        "note": "全量核对声明下未提及，视为默许确认（低权重）。",
                    }
                )
                ledger_records.append(
                    {
                        "channel": feedback_ledger.CHECKLIST_CHANNEL,
                        "outcome": feedback_ledger.OUTCOME_TACIT_CONFIRMED,
                        "explicit": False,
                        "order_code": code,
                        "rule_id": issue.get("rule_id"),
                        "issue_id": issue_id,
                        "item_id": None,
                        "execution_ref": execution_ref,
                        "station_id": issue.get("station_id"),
                        "original_judgment": _original_judgment(issue),
                        "reason": "全量核对声明下未提及该问题项。",
                        "feedback_id": reconciliation_id,
                        "reviewer": reviewer or None,
                        "source_ref": source_ref,
                        "snapshot_ref": snapshot_ref,
                    }
                )
            else:
                classifications.append(
                    {
                        "item_id": None,
                        "order_code": code,
                        "verdict": None,
                        "problem_category": issue.get("category") or None,
                        "matched_issue_ids": [issue_id],
                        "outcome": "unmentioned_partial",
                        "ledger": False,
                        "note": "部分清单未提及，无信息量不入账。",
                    }
                )

    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "reconciliation_id": reconciliation_id,
        "full_review_declared": full_review_declared,
        "source_sha256": snapshot_ref,
        "classifications": classifications,
        "ledger_records": ledger_records,
        "metrics": compute_reconciliation_metrics(
            classifications, full_review_declared=full_review_declared
        ),
        "echo_lines": _echo_lines(classifications),
    }


def compute_reconciliation_metrics(
    classifications: list[dict[str, Any]],
    *,
    full_review_declared: bool,
) -> dict[str, Any]:
    """Recall is always computable; error rate only under a full declaration.

    Every ratio carries numerator and denominator so small samples cannot hide
    behind a bare percentage (design doc §4).
    """

    outcomes = [str(row.get("outcome")) for row in classifications]
    confirmed = outcomes.count(feedback_ledger.OUTCOME_CONFIRMED)
    missed = outcomes.count(feedback_ledger.OUTCOME_MISSED)
    rejected = outcomes.count(feedback_ledger.OUTCOME_REJECTED)
    tacit = outcomes.count(feedback_ledger.OUTCOME_TACIT_CONFIRMED)
    unmatched = outcomes.count("unmatched")
    recall_denominator = confirmed + missed
    error_denominator = confirmed + rejected + tacit
    return {
        "identification_rate": {
            "applicable": recall_denominator > 0,
            "numerator": confirmed,
            "denominator": recall_denominator,
            "ratio": _ratio(confirmed, recall_denominator),
            "text": _ratio_text("识别率", confirmed, recall_denominator),
        },
        "error_rate": {
            "applicable": bool(full_review_declared and error_denominator > 0),
            "numerator": rejected,
            "denominator": error_denominator,
            "ratio": _ratio(rejected, error_denominator) if full_review_declared else None,
            "text": (
                _ratio_text("错误率", rejected, error_denominator)
                if full_review_declared and error_denominator > 0
                else "错误率：不适用（仅部分清单核对，未声明全量）"
            ),
            "gating_reason": None if full_review_declared else "partial_checklist",
        },
        "counts": {
            "confirmed": confirmed,
            "missed": missed,
            "rejected": rejected,
            "tacit_confirmed": tacit,
            "unmatched": unmatched,
        },
    }


def append_reconciliation_to_ledger(
    reconciliation: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append the reconciliation records unless the same run is already there.

    Idempotency key is ``feedback_id`` (the reconciliation id): a corrected
    checklist produces a different hash and therefore fresh records, while an
    accidental re-run of the same input is a no-op.
    """

    feedback_id = str(reconciliation.get("reconciliation_id"))
    existing = [
        record
        for record in feedback_ledger.read_records(path=path)
        if record.get("feedback_id") == feedback_id
    ]
    if existing:
        return {"appended": 0, "deduplicated": True, "existing_count": len(existing)}
    written = feedback_ledger.append_records(
        reconciliation["ledger_records"], path=path
    )
    return {"appended": len(written), "deduplicated": False, "existing_count": 0}


def archive_reconciliation(
    reconciliation: dict[str, Any],
    *,
    final_issue_list_path: Path,
    checklist_source_path: Path | None = None,
    checklist_items: list[dict[str, Any]] | None = None,
) -> Path:
    """Persist the reconciliation result beside its issue list (execution dir)."""

    target_dir = (
        final_issue_list_path.parent
        / "checklist_reconcile"
        / _archive_dir_name(reconciliation)
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(reconciliation)
    payload["final_issue_list_path"] = str(final_issue_list_path)
    payload["checklist_source_path"] = (
        str(checklist_source_path) if checklist_source_path else None
    )
    _atomic_write_json(target_dir / "reconciliation.json", payload)
    if checklist_items:
        _atomic_write_json(target_dir / "checklist_items.json", checklist_items)
    if checklist_source_path and Path(checklist_source_path).is_file():
        destination = target_dir / ("checklist_source" + _suffix_of(checklist_source_path))
        destination.write_bytes(Path(checklist_source_path).read_bytes())
    return target_dir


def _archive_dir_name(reconciliation: dict[str, Any]) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    digest = str(reconciliation.get("reconciliation_id", "")).split(":")[-1][:8]
    return f"{stamp}-{digest}"


def _suffix_of(path: Path | str) -> str:
    suffix = Path(path).suffix
    return suffix if re.match(r"^\.\w{1,10}$", suffix) else ".bin"


def _classification(
    item: dict[str, Any],
    issue: dict[str, Any] | None,
    outcome: str,
    note: str,
) -> dict[str, Any]:
    return {
        "item_id": item["item_id"],
        "order_code": item["order_code"],
        "verdict": item["verdict"],
        "problem_category": item["problem_category"],
        "matched_issue_ids": [str(issue["issue_id"])] if issue else [],
        "matched_rule_ids": [issue.get("rule_id")] if issue else [],
        "outcome": outcome,
        "ledger": outcome
        in {
            feedback_ledger.OUTCOME_CONFIRMED,
            feedback_ledger.OUTCOME_REJECTED,
            feedback_ledger.OUTCOME_MISSED,
        },
        "note": note,
    }


def _ledger_record(
    item: dict[str, Any],
    issue: dict[str, Any] | None,
    outcome: str,
    *,
    reconciliation_id: str,
    snapshot_ref: str,
    reviewer: dict[str, Any] | None,
    execution_ref: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    reason = item.get("note")
    if outcome == feedback_ledger.OUTCOME_MISSED:
        reason = reason or item.get("problem_category") or "清单指出但规则未覆盖"
    return {
        "channel": feedback_ledger.CHECKLIST_CHANNEL,
        "outcome": outcome,
        "explicit": True,
        "order_code": item["order_code"],
        "rule_id": issue.get("rule_id") if issue else None,
        "issue_id": str(issue["issue_id"]) if issue else None,
        "item_id": item["item_id"],
        "execution_ref": execution_ref,
        "station_id": issue.get("station_id") if issue else None,
        "original_judgment": _original_judgment(issue) if issue else None,
        "reason": reason,
        "feedback_id": reconciliation_id,
        "reviewer": reviewer or None,
        "source_ref": source_ref,
        "snapshot_ref": snapshot_ref,
    }


def _original_judgment(issue: dict[str, Any] | None) -> str | None:
    if not issue:
        return None
    for key in ("review_status", "remark_review_status", "review_stage"):
        value = str(issue.get(key) or "").strip()
        if value:
            return value
    return None


def _reconciliation_id(
    snapshot_ref: str, items: list[dict[str, Any]], full_review_declared: bool
) -> str:
    payload = json.dumps(
        {"source": snapshot_ref, "items": items, "full": full_review_declared},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"checklist:{sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _ratio_text(label: str, numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return f"{label}：暂不可算（0 个样本）"
    percentage = round(numerator * 100 / denominator)
    return f"{label}：{percentage}%（{numerator}/{denominator}）"


def _echo_lines(classifications: list[dict[str, Any]]) -> list[str]:
    """Human-readable echo for the session so the user can correct by voice."""

    verdict_labels = {VERDICT_PROBLEM: "说有问题", VERDICT_OK: "说没问题"}
    lines: list[str] = []
    for row in classifications:
        verdict = verdict_labels.get(row.get("verdict"))
        category = row.get("problem_category") or "任意类型"
        if row.get("item_id"):
            head = f"{row['order_code']}【清单{verdict}·{category}】"
        else:
            head = f"{row['order_code']}【清单未提及·{category}】"
        rules = ",".join(str(r) for r in row.get("matched_rule_ids", []) if r)
        suffix = f"（规则 {rules}）" if rules else ""
        lines.append(f"{head} → {row['outcome']}{suffix}：{row['note']}")
    return lines


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
