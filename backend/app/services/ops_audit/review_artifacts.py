"""Deterministic report artifacts for operations audit handoff."""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.services.ops_audit.field_labels import remark_field_display_name
from app.services.ops_audit.final_issue_list import ensure_issue_ids
from app.services.ops_audit.issue_linking import is_abnormal_fact_rule, parse_issue_evidence

REPORT_INPUT_FILENAME = "latest_finished_work_orders_report_input.json"
REVIEW_DECISIONS_FILENAME = "latest_finished_work_orders_review_decisions.json"
REVIEWED_ISSUES_FILENAME = "latest_finished_work_orders_reviewed_issue_list.json"
REVIEW_INPUT_FILENAME = "latest_finished_work_orders_review_input.json"
ALLOWED_DECISIONS = {"retain", "exclude", "manual_review"}
HUMAN_FEEDBACK_DECISIONS = {"include", "exclude", "pending"}


def issue_list_sha256(issue_list: dict[str, Any]) -> str:
    payload = json.dumps(issue_list, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def build_report_input(
    final_issue_list: dict[str, Any],
    *,
    source_path: Path | None = None,
) -> dict[str, Any]:
    """Build the report projection without a second LLM decision pass."""

    ensure_issue_ids(final_issue_list)
    source_items = final_issue_list.get("items", [])
    reportable, pending = _partition_report_items(source_items)
    pending_semantic_reviews = final_issue_list.get("pending_semantic_reviews", [])
    semantic_excluded = final_issue_list.get("semantic_excluded_items", [])
    report_items = _group_report_items(reportable)
    affected_orders = {
        item.get("working_order_code") for item in reportable if item.get("working_order_code")
    }
    source = {
        "sha256": issue_list_sha256(final_issue_list),
        "issue_count": len(source_items),
    }
    if source_path is not None:
        source["path"] = str(source_path.resolve())
    return {
        "schema_version": "ops_audit_report_input.v3",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "report_ready": not pending and not pending_semantic_reviews,
        "pending_review_items": [_review_item(item) for item in pending],
        "pending_semantic_reviews": pending_semantic_reviews,
        "semantic_excluded_items": semantic_excluded,
        "report_contract": {
            "one_item_per_report_row": True,
            "components_are_evidence_not_additional_rows": True,
            "report_issue_count_unit": "grouped_abnormality",
            "pending_items_are_not_reportable": True,
        },
        "summary": {
            "source_issue_count": len(source_items),
            "reportable_issue_count": len(reportable),
            "pending_review_count": len(pending),
            "pending_semantic_review_count": len(pending_semantic_reviews),
            "semantic_excluded_count": len(semantic_excluded),
            "affected_order_count": len(affected_orders),
            "report_issue_count": len(report_items),
        },
        "items": report_items,
    }


def persist_report_input(
    final_issue_list: dict[str, Any],
    path: Path,
    *,
    source_path: Path | None = None,
) -> dict[str, Any]:
    report_input = build_report_input(final_issue_list, source_path=source_path)
    _atomic_write_json(path, report_input)
    return report_input


def build_human_feedback_request(
    report_input: dict[str, Any],
    *,
    report_input_path: Path | None = None,
) -> dict[str, Any]:
    """Project pending report items into the reusable UI feedback contract."""

    items: list[dict[str, Any]] = []
    for item in report_input.get("pending_review_items", []):
        if not isinstance(item, dict) or not item.get("issue_id"):
            continue
        items.append({
            "item_id": str(item["issue_id"]),
            "kind": "issue",
            "title": item.get("message") or item.get("field_label") or "待确认问题",
            "details": item,
        })
    for item in report_input.get("pending_semantic_reviews", []):
        if not isinstance(item, dict) or not item.get("review_item_id"):
            continue
        items.append({
            "item_id": str(item["review_item_id"]),
            "kind": "semantic_review",
            "title": item.get("conclusion") or "语义复核待确认",
            "details": item,
        })
    return {
        "feedback_id": f"ops-audit:{report_input.get('source', {}).get('sha256', '')}",
        "scenario": "ops_work_order_audit",
        "learning_mode": "ops",
        "title": "待确认问题",
        "source_sha256": report_input.get("source", {}).get("sha256"),
        "report_input_path": str(report_input_path.resolve()) if report_input_path else None,
        "items": items,
        "required": bool(items),
    }


def apply_human_feedback(
    report_input_path: Path,
    decisions: Iterable[dict[str, Any]],
    *,
    expected_source_sha256: str,
    feedback_id: str,
    reviewer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply user decisions to an audit source and rebuild its report input.

    The operation is deterministic and source-hash guarded so a stale panel
    cannot silently change a newer audit run.
    """

    report_path = report_input_path.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source_meta = report.get("source") if isinstance(report.get("source"), dict) else {}
    source_path = Path(str(source_meta.get("path") or "")).expanduser().resolve()
    try:
        source_path.relative_to(report_path.parent)
    except ValueError as exc:
        raise ValueError("human feedback source issue list is outside the report directory") from exc
    if not source_path.is_file():
        raise ValueError("human feedback source issue list is unavailable")
    source = ensure_issue_ids(json.loads(source_path.read_text(encoding="utf-8")))
    actual_sha256 = issue_list_sha256(source)
    if expected_source_sha256 and expected_source_sha256 != actual_sha256:
        raise ValueError("report input changed after the feedback panel was opened")

    pending_issue_ids = {
        str(item.get("issue_id"))
        for item in report.get("pending_review_items", [])
        if isinstance(item, dict) and item.get("issue_id")
    }
    pending_semantic_ids = {
        str(item.get("review_item_id"))
        for item in report.get("pending_semantic_reviews", [])
        if isinstance(item, dict) and item.get("review_item_id")
    }
    allowed_ids = pending_issue_ids | pending_semantic_ids
    normalized: dict[str, dict[str, Any]] = {}
    for raw in decisions:
        item_id = str(raw.get("item_id") or raw.get("issue_id") or "").strip()
        decision = str(raw.get("decision") or "").strip().lower()
        if not item_id or item_id not in allowed_ids:
            raise ValueError(f"unknown human feedback item: {item_id or '<empty>'}")
        if decision not in HUMAN_FEEDBACK_DECISIONS:
            raise ValueError(f"invalid human feedback decision for {item_id}: {decision}")
        if item_id in normalized:
            raise ValueError(f"duplicate human feedback item: {item_id}")
        normalized[item_id] = {
            "item_id": item_id,
            "decision": decision,
            "comment": str(raw.get("comment") or "").strip()[:4000],
        }
    missing = allowed_ids - normalized.keys()
    if missing:
        raise ValueError(f"human feedback does not cover all pending items: {len(missing)}")

    excluded_ids: set[str] = set()
    for item in source.get("items", []):
        item_id = str(item.get("issue_id") or "")
        feedback = normalized.get(item_id)
        if not feedback:
            continue
        item["human_feedback"] = {"feedback_id": feedback_id, **feedback}
        if feedback["decision"] == "include":
            item["needs_manual_review"] = False
            item["review_status"] = "human_confirmed"
            item["review_stage"] = "human_feedback"
        elif feedback["decision"] == "exclude":
            excluded_ids.add(item_id)

    remaining_semantic: list[dict[str, Any]] = []
    for review in source.get("pending_semantic_reviews", []):
        review_id = str(review.get("review_item_id") or "")
        feedback = normalized.get(review_id)
        if not feedback or feedback["decision"] == "pending":
            remaining_semantic.append(review)
            continue
        matching_items = _semantic_feedback_matches(source.get("items", []), review)
        for item in matching_items:
            item_id = str(item.get("issue_id") or "")
            item["human_feedback"] = {"feedback_id": feedback_id, **feedback}
            if feedback["decision"] == "include":
                item["needs_manual_review"] = False
                item["review_status"] = "human_confirmed"
                item["review_stage"] = "human_feedback"
            else:
                excluded_ids.add(item_id)
    source["items"] = [item for item in source.get("items", []) if str(item.get("issue_id") or "") not in excluded_ids]
    source["pending_semantic_reviews"] = remaining_semantic
    source["last_human_feedback"] = {
        "feedback_id": feedback_id,
        "reviewer": reviewer or {},
        "decisions": list(normalized.values()),
        "recorded_at": datetime.now().isoformat(),
    }
    _atomic_write_json(source_path, source)
    updated = persist_report_input(source, report_path, source_path=source_path)
    updated["feedback_id"] = feedback_id
    updated["feedback"] = list(normalized.values())
    return updated


def _semantic_feedback_matches(items: list[dict[str, Any]], review: dict[str, Any]) -> list[dict[str, Any]]:
    """Find the source issues represented by a semantic review item."""

    source_issue = review.get("source_issue") if isinstance(review.get("source_issue"), dict) else {}
    keys = ("working_order_code", "rule_id", "rf_table", "field", "rf_record_key")
    if any(source_issue.get(key) not in (None, "") for key in keys):
        return [
            item for item in items
            if all(
                source_issue.get(key) in (None, "")
                or str(item.get(key) or "") == str(source_issue.get(key) or "")
                for key in keys
            )
        ]
    code = str(review.get("working_order_code") or "")
    return [
        item for item in items
        if str(item.get("working_order_code") or "") == code
        and item.get("review_stage") == "semantic_remark"
    ]


def build_review_input(final_issue_list: dict[str, Any]) -> dict[str, Any]:
    """Deprecated compatibility projection; the production path uses report_input directly."""
    ensure_issue_ids(final_issue_list)
    items = [_review_item(item) for item in final_issue_list.get("items", [])]
    return {
        "schema_version": "ops_audit_review_input.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {"sha256": issue_list_sha256(final_issue_list), "issue_count": len(items)},
        "items": items,
        "pending_semantic_reviews": final_issue_list.get("pending_semantic_reviews", []),
    }


def persist_review_input(final_issue_list: dict[str, Any], path: Path) -> dict[str, Any]:
    """Deprecated compatibility writer; no production caller uses this artifact."""
    result = build_review_input(final_issue_list)
    _atomic_write_json(path, result)
    return result


def apply_review_decisions(
    final_issue_list_path: Path,
    decisions: Iterable[dict[str, Any]],
    *,
    expected_source_sha256: str,
    reviewer: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Deprecated compatibility API for old callers; removed from the Agent tool registry."""
    source_path = final_issue_list_path.resolve()
    final = ensure_issue_ids(json.loads(source_path.read_text(encoding="utf-8")))
    if expected_source_sha256 != issue_list_sha256(final):
        raise ValueError("final issue list changed after review input was created")
    source = final.get("items", [])
    by_id = {str(item["issue_id"]): item for item in source}
    normalized = []
    seen = set()
    for raw in decisions:
        issue_id = str(raw.get("issue_id") or "").strip()
        decision = str(raw.get("decision") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if issue_id not in by_id:
            raise ValueError(f"unknown review issue_id: {issue_id or '<empty>'}")
        if issue_id in seen:
            raise ValueError(f"duplicate review issue_id: {issue_id}")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"invalid decision for {issue_id}: {decision}")
        if not reason:
            raise ValueError(f"reason is required for {decision}: {issue_id}")
        seen.add(issue_id)
        normalized.append(
            {
                "issue_id": issue_id,
                "decision": decision,
                "reason": reason,
                "evidence_refs": [str(v) for v in raw.get("evidence_refs", []) if str(v).strip()],
            }
        )
    missing = set(by_id) - seen
    if missing:
        raise ValueError(
            f"review decisions do not cover all issues; missing {len(missing)}: {', '.join(sorted(missing)[:5])}"
        )
    decisions_by_id = {item["issue_id"]: item for item in normalized}
    facts_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in source:
        if is_abnormal_fact_rule(item.get("rule_id")) and item.get("issue_group_id"):
            facts_by_group.setdefault(str(item["issue_group_id"]), []).append(item)
    for item in source:
        decision = decisions_by_id[item["issue_id"]]
        if (
            item.get("needs_manual_review")
            and decision["decision"] == "retain"
            and not decision["evidence_refs"]
        ):
            decision.update(
                decision="manual_review",
                reason=f"待核验项尚无补充证据：{item.get('reason') or item.get('message')}",
            )
        if item.get("rule_id") == "RF_ABNORMAL_VALUE_NO_REMARK":
            facts = facts_by_group.get(str(item.get("issue_group_id") or ""), [])
            fact_decisions = [decisions_by_id[f["issue_id"]]["decision"] for f in facts]
            if (
                fact_decisions
                and not any(value == "retain" for value in fact_decisions)
                and decision["decision"] != "exclude"
            ):
                status = (
                    "exclude"
                    if all(value == "exclude" for value in fact_decisions)
                    else "manual_review"
                )
                decision.update(
                    decision=status,
                    reason="关联异常事实已排除，异常说明问题同步排除。"
                    if status == "exclude"
                    else "关联异常事实尚待核验，不能单独确认异常说明问题。",
                )
    retained, excluded, manual = [], [], []
    for item in source:
        annotated = {**item, "final_review": decisions_by_id[item["issue_id"]]}
        bucket = {"retain": retained, "exclude": excluded, "manual_review": manual}[
            annotated["final_review"]["decision"]
        ]
        bucket.append(annotated)
    target = (output_dir or source_path.parent).resolve()
    target.mkdir(parents=True, exist_ok=True)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_meta = {
        "path": str(source_path),
        "sha256": issue_list_sha256(final),
        "issue_count": len(source),
    }
    pending = final.get("pending_semantic_reviews", [])
    report_items = _group_report_items(retained)
    ready = not manual and not pending
    review_meta = {
        "schema_version": "ops_audit_review_decisions.v1",
        "generated_at": generated,
        "source": source_meta,
        "reviewer": reviewer or {},
        "counts": {
            key: Counter(i["decision"] for i in normalized).get(key, 0)
            for key in sorted(ALLOWED_DECISIONS)
        },
        "decisions": normalized,
    }
    reviewed = {
        "schema_version": "ops_audit_reviewed_issue_list.v1",
        "generated_at": generated,
        "source": source_meta,
        "reviewer": reviewer or {},
        "review_complete": True,
        "report_ready": ready,
        "pending_semantic_reviews": pending,
        "issue_count": len(retained),
        "excluded_count": len(excluded),
        "manual_review_count": len(manual),
        "items": retained,
        "excluded_items": excluded,
        "manual_review_items": manual,
    }
    report = {
        "schema_version": "ops_audit_report_input.v2",
        "generated_at": generated,
        "source": source_meta,
        "report_ready": ready,
        "pending_semantic_reviews": pending,
        "summary": {
            "reviewed_count": len(source),
            "retained_count": len(retained),
            "excluded_count": len(excluded),
            "manual_review_count": len(manual),
            "affected_order_count": len(
                {i.get("working_order_code") for i in retained if i.get("working_order_code")}
            ),
            "report_issue_count": len(report_items),
        },
        "items": report_items,
    }
    decisions_path, reviewed_path, report_path = (
        target / name
        for name in (REVIEW_DECISIONS_FILENAME, REVIEWED_ISSUES_FILENAME, REPORT_INPUT_FILENAME)
    )
    _atomic_write_json(decisions_path, review_meta)
    _atomic_write_json(reviewed_path, reviewed)
    _atomic_write_json(report_path, report)
    return {
        "success": True,
        "review_complete": True,
        "report_ready": ready,
        "pending_semantic_review_count": len(pending),
        "source_issue_count": len(source),
        "retained_count": len(retained),
        "report_issue_count": len(report_items),
        "excluded_count": len(excluded),
        "manual_review_count": len(manual),
        "review_decisions_path": str(decisions_path),
        "reviewed_issue_list_path": str(reviewed_path),
        "report_input_path": str(report_path),
    }


def _partition_report_items(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending_groups = {
        str(item.get("issue_group_id"))
        for item in items
        if item.get("needs_manual_review") and item.get("issue_group_id")
    }
    reportable: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for item in items:
        group_is_pending = str(item.get("issue_group_id")) in pending_groups
        (pending if item.get("needs_manual_review") or group_is_pending else reportable).append(
            item
        )
    return reportable, pending


def _review_item(item: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: item.get(key)
        for key in (
            "issue_id",
            "working_order_code",
            "station_id",
            "station_name",
            "operation_unit",
            "order_type",
            "maintenance_type",
            "rf_table",
            "rf_form_name",
            "rf_record_key",
            "pollutant_type",
            "rule_id",
            "category",
            "issue_group_id",
            "issue_component",
            "field",
            "field_label",
            "message",
            "original_remarks",
            "original_remark_text",
            "remark_status",
            "remark_status_label",
            "remark_judgment",
            "remark_judgment_label",
            "semantic_message",
            "semantic_conclusion",
            "semantic_remark_review",
            "remark_review_status",
            "remark_review_status_label",
            "needs_manual_review",
            "decision_evidence",
            "report_classification",
            "reason_code",
            "reason",
            "observed_summary",
            "form_concentrations",
            "concentration_unit",
            "attachment_filename",
            "attachment_original_path",
            "model_result_path",
            "evidence_images",
        )
        if item.get(key) not in (None, "", [], {})
    } | {
        "evidence_facts": _compact_evidence(item.get("evidence")),
        "remark_context": _remark_context(item),
    }
    # The report agent receives this projection for every issue.  Raw evidence is
    # retained for traceability, but is deliberately not needed to write prose.
    result["display_evidence"] = _display_evidence(item)
    return result


def _remark_context(item: dict[str, Any]) -> dict[str, Any]:
    """Keep empty associated fields distinct from unavailable remark evidence."""
    evidence = parse_issue_evidence(item.get("evidence"))
    entries = [
        dict(entry) for entry in (item.get("original_remarks") or []) if isinstance(entry, dict)
    ]
    for key in ("handling_record_candidates", "remark_candidates"):
        candidates = evidence.get(key)
        if not isinstance(candidates, dict):
            continue
        known = {entry.get("field") for entry in entries}
        for field, value in candidates.items():
            if field.upper() == "PROCESSTYPE" or field in known:
                continue
            entries.append(
                {
                    "field": field,
                    "field_label": remark_field_display_name(field),
                    "value": "" if value is None else str(value),
                }
            )
    text = str(item.get("original_remark_text") or "").strip()
    if any(str(entry.get("value") or "").strip() for entry in entries) or text:
        status = "provided"
    elif (
        entries
        or item.get("remark_status") == "missing"
        or item.get("remark_review_status") == "missing"
    ):
        status = "missing"
    elif item.get("remark_status") == "not_applicable":
        status = "not_applicable"
    else:
        status = "unavailable"
    labels = {
        "provided": "已填写",
        "missing": "未填写",
        "unavailable": "备注信息未取得，待核验",
        "not_applicable": "不适用",
    }
    return {"status": status, "status_label": labels[status], "entries": entries, "text": text}


def _group_report_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    records_by_group: dict[tuple[str, ...], set[str]] = {}
    for item in items:
        scope = tuple(
            str(item.get(key) or "") for key in ("working_order_code", "rf_table", "issue_group_id")
        )
        record = str(item.get("rf_record_key") or "")
        if is_abnormal_fact_rule(item.get("rule_id")) and record and record != scope[0]:
            records_by_group.setdefault(scope, set()).add(record)
    for item in items:
        linked = (
            is_abnormal_fact_rule(item.get("rule_id"))
            or item.get("rule_id") == "RF_ABNORMAL_VALUE_NO_REMARK"
        )
        if (
            linked
            and item.get("issue_group_id")
            and item.get("working_order_code")
            and item.get("rf_table")
        ):
            scope = tuple(
                str(item[key]) for key in ("working_order_code", "rf_table", "issue_group_id")
            )
            record = str(item.get("rf_record_key") or "")
            records = records_by_group.get(scope, set())
            # Older semantic results used only the order code as their record key.
            if record in {"", scope[0]} and len(records) == 1:
                record = next(iter(records))
            key = (
                "linked",
                str(item["working_order_code"]),
                str(item["rf_table"]),
                record,
                str(item["issue_group_id"]),
            )
        else:
            key = ("single", str(item["issue_id"]))
        groups.setdefault(key, []).append(item)
    result = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: not is_abnormal_fact_rule(item.get("rule_id")))
        components = [_report_item(item) for item in ordered]
        row = dict(components[0])
        row["source_issue_ids"] = [item["issue_id"] for item in ordered]
        row["rule_ids"] = list(dict.fromkeys(item["rule_id"] for item in ordered))
        row["message"] = "；".join(
            dict.fromkeys(str(item.get("message") or "") for item in ordered)
        )
        row["components"] = components
        # Keep every source's remarks, including empty fields, without hiding a provided explanation.
        contexts = [component["remark_context"] for component in components]
        rank = {"provided": 0, "missing": 1, "unavailable": 2, "not_applicable": 3}
        context = dict(min(contexts, key=lambda value: rank[value["status"]]))
        context["entries"] = []
        for value in contexts:
            for entry in value["entries"]:
                if entry not in context["entries"]:
                    context["entries"].append(entry)
        row["remark_context"] = context
        result.append(row)
    return result


def _report_item(item: dict[str, Any]) -> dict[str, Any]:
    return _review_item(item)


def _compact_evidence(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value[:2000]
        value = parsed
    if isinstance(value, dict):
        return {
            str(key): child
            if key in {"handling_record_candidates", "remark_candidates"}
            else _compact_evidence(child)
            for key, child in value.items()
            if child not in (None, "", [], {})
            and key
            not in {
                "raw_record",
                "dataset",
                "tool_trace",
                "debug",
                "image_base64",
                "base64",
                "raw_bytes",
                "source_issue",
                "sample_issues",
            }
        }
    if isinstance(value, list):
        return [_compact_evidence(child) for child in value[:50]]
    return value


def _display_evidence(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Build concise user-facing evidence for every rule family.

    This is the report-facing contract.  Do not expose the raw evidence keys here:
    the report agent should be able to render this list without parsing JSON or
    calling ``execute_python``.
    """
    evidence = parse_issue_evidence(item.get("evidence"))
    comparisons = evidence.get("comparisons")
    if not isinstance(comparisons, list):
        comparison = evidence.get("comparison")
        comparisons = [comparison] if isinstance(comparison, dict) else []
    attachment = evidence.get("attachment") if isinstance(evidence.get("attachment"), dict) else {}
    attachment_name = (
        item.get("attachment_filename")
        or attachment.get("filename")
        or attachment.get("name")
    )
    display: list[dict[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        status = str(comparison.get("status") or "").strip()
        if status == "xls_read_error":
            display.append({"text": f"附件读取失败：{comparison.get('error') or '无法读取'}"})
            continue
        if status not in {"mismatch", "missing_form_value", "missing_xls_value"}:
            continue
        item_display: dict[str, Any] = {
            "label": comparison.get("label") or comparison.get("field") or "比对项",
            "form_value": comparison.get("form_value"),
            "attachment_value": comparison.get("xls_value"),
        }
        location = comparison.get("cell") or comparison.get("configured_cell")
        if location:
            item_display["location"] = location
        if attachment_name:
            item_display["attachment"] = attachment_name
        item_display["text"] = _comparison_text(item_display)
        display.append(item_display)

    # Range/abnormal rules already expose normalized decision evidence.  Prefer it
    # over the lower-level out_of_spec_values payload.
    decision = item.get("decision_evidence")
    if isinstance(decision, dict) and decision:
        text = _decision_evidence_text(decision)
        if text:
            display.append({"text": text})

    rows: list[Any] = []
    for key in ("violations", "out_of_spec_values", "missing_fields", "checks"):
        value = evidence.get(key)
        if isinstance(value, list):
            rows.extend(value)
    # Avoid duplicating the normalized range item when no decision projection exists.
    if not decision:
        for row in rows[:20]:
            text = _rule_evidence_text(row)
            if text:
                display.append({"text": text})

    if not display:
        fallback = _rule_evidence_text(evidence)
        if fallback:
            display.append({"text": fallback})
    if not display and item.get("message"):
        display.append({"text": str(item["message"])})
    return display


def _value_text(value: Any, default: str = "未填写") -> str:
    if value in (None, ""):
        return default
    return str(value)


def _comparison_text(item: dict[str, Any]) -> str:
    label = _value_text(item.get("label"), "比对项")
    form_value = _value_text(item.get("form_value"))
    attachment_value = _value_text(item.get("attachment_value"))
    location = item.get("location")
    suffix = f"，附件{item['attachment']}" if item.get("attachment") else ""
    location_text = f"（位置：{location}）" if location else ""
    return f"{label}：表单值“{form_value}”，附件值“{attachment_value}”{suffix}{location_text}。"


def _decision_evidence_text(value: dict[str, Any]) -> str:
    label = value.get("field_label") or value.get("field")
    if not label:
        return ""
    observed = value.get("raw_value", value.get("normalized_value"))
    expected = value.get("expected_range")
    if expected:
        brand = f"（{value['brand']}）" if value.get("brand") else ""
        return f"{label}：实测值“{_value_text(observed)}”，正常范围为“{expected}”{brand}。"
    return f"{label}：实际值“{_value_text(observed)}”。"


def _rule_evidence_text(row: Any) -> str:
    """Turn common rule evidence shapes into one short Chinese sentence."""
    if not isinstance(row, dict):
        return _value_text(row, "")
    label = row.get("label") or row.get("field_label") or row.get("item_label")
    field = row.get("field") or row.get("actual_field")
    name = label or field or row.get("name")
    if row.get("model_value") is not None or row.get("situation_value") is not None:
        project = label or "检查项目"
        return (
            f"{project}：设备型号“{_value_text(row.get('model_value'))}”，"
            f"运行情况“{_value_text(row.get('situation_value'))}”。"
        )
    if row.get("actual") is not None or row.get("expected") is not None:
        return (
            f"{name or '检查项'}：实际值“{_value_text(row.get('actual'))}”，"
            f"期望值“{_value_text(row.get('expected'))}”。"
        )
    if row.get("value") is not None or row.get("raw_value") is not None:
        value = row.get("raw_value", row.get("value"))
        expected = row.get("expected_range")
        if expected is None and (row.get("min") is not None or row.get("max") is not None):
            expected = f"{_value_text(row.get('min'))}至{_value_text(row.get('max'))}{row.get('unit') or ''}"
        suffix = f"，要求“{expected}”" if expected else ""
        return f"{name or '检查项'}：实际值“{_value_text(value)}”{suffix}。"
    if row.get("missing") is True:
        return f"{name or '检查项'}：未填写。"
    return ""


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
