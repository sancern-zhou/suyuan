"""Persistent review artifacts for operations audit report handoff."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from app.services.ops_audit.final_issue_list import ensure_issue_ids


REVIEW_DECISIONS_FILENAME = "latest_finished_work_orders_review_decisions.json"
REVIEWED_ISSUES_FILENAME = "latest_finished_work_orders_reviewed_issue_list.json"
REPORT_INPUT_FILENAME = "latest_finished_work_orders_report_input.json"
REVIEW_INPUT_FILENAME = "latest_finished_work_orders_review_input.json"
ALLOWED_DECISIONS = {"retain", "exclude", "manual_review"}


def issue_list_sha256(issue_list: dict[str, Any]) -> str:
    payload = json.dumps(issue_list, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def build_review_input(final_issue_list: dict[str, Any]) -> dict[str, Any]:
    """Project the final list into a compact, decision-focused evidence package."""

    ensure_issue_ids(final_issue_list)
    source_hash = issue_list_sha256(final_issue_list)
    items = [_review_item(item) for item in final_issue_list.get("items", [])]
    return {
        "schema_version": "ops_audit_review_input.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {
            "sha256": source_hash,
            "issue_count": len(items),
        },
        "review_contract": {
            "allowed_decisions": sorted(ALLOWED_DECISIONS),
            "full_coverage_required": True,
            "identity_field": "issue_id",
            "absence_does_not_mean_retain": True,
        },
        "items": items,
    }


def persist_review_input(final_issue_list: dict[str, Any], path: Path) -> dict[str, Any]:
    review_input = build_review_input(final_issue_list)
    _atomic_write_json(path, review_input)
    return review_input


def apply_review_decisions(
    final_issue_list_path: Path,
    decisions: Iterable[dict[str, Any]],
    *,
    expected_source_sha256: str,
    reviewer: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate a complete review and materialize reviewed/report artifacts."""

    source_path = final_issue_list_path.resolve()
    final_issue_list = ensure_issue_ids(json.loads(source_path.read_text(encoding="utf-8")))
    actual_hash = issue_list_sha256(final_issue_list)
    if not expected_source_sha256 or expected_source_sha256 != actual_hash:
        raise ValueError("final issue list changed after review input was created")

    source_items = final_issue_list.get("items", [])
    source_by_id = {str(item["issue_id"]): item for item in source_items}
    normalized = _validate_decisions(decisions, source_by_id)
    decision_by_id = {item["issue_id"]: item for item in normalized}

    retained: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    for source_item in source_items:
        decision = decision_by_id[str(source_item["issue_id"])]
        annotated = {**source_item, "final_review": decision}
        if decision["decision"] == "retain":
            retained.append(annotated)
        elif decision["decision"] == "exclude":
            excluded.append(annotated)
        else:
            manual.append(annotated)

    target_dir = (output_dir or source_path.parent).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = Counter(item["decision"] for item in normalized)
    review_meta = {
        "schema_version": "ops_audit_review_decisions.v1",
        "generated_at": generated_at,
        "source": {
            "path": str(source_path),
            "sha256": actual_hash,
            "issue_count": len(source_items),
        },
        "reviewer": reviewer or {},
        "counts": {key: counts.get(key, 0) for key in sorted(ALLOWED_DECISIONS)},
        "decisions": normalized,
    }
    reviewed = {
        "schema_version": "ops_audit_reviewed_issue_list.v1",
        "generated_at": generated_at,
        "source": review_meta["source"],
        "reviewer": review_meta["reviewer"],
        "review_complete": True,
        "report_ready": not manual,
        "issue_count": len(retained),
        "excluded_count": len(excluded),
        "manual_review_count": len(manual),
        "affected_order_count": len({item.get("working_order_code") for item in retained if item.get("working_order_code")}),
        "items": retained,
        "excluded_items": excluded,
        "manual_review_items": manual,
    }
    report_input = {
        "schema_version": "ops_audit_report_input.v1",
        "generated_at": generated_at,
        "source": review_meta["source"],
        "report_ready": not manual,
        "summary": {
            "reviewed_count": len(source_items),
            "retained_count": len(retained),
            "excluded_count": len(excluded),
            "manual_review_count": len(manual),
            "affected_order_count": reviewed["affected_order_count"],
        },
        "items": [_report_item(item) for item in retained],
    }

    decisions_path = target_dir / REVIEW_DECISIONS_FILENAME
    reviewed_path = target_dir / REVIEWED_ISSUES_FILENAME
    report_input_path = target_dir / REPORT_INPUT_FILENAME
    _atomic_write_json(decisions_path, review_meta)
    _atomic_write_json(reviewed_path, reviewed)
    _atomic_write_json(report_input_path, report_input)
    return {
        "success": True,
        "review_complete": True,
        "report_ready": not manual,
        "source_issue_count": len(source_items),
        "retained_count": len(retained),
        "excluded_count": len(excluded),
        "manual_review_count": len(manual),
        "review_decisions_path": str(decisions_path),
        "reviewed_issue_list_path": str(reviewed_path),
        "report_input_path": str(report_input_path),
    }


def _validate_decisions(
    decisions: Iterable[dict[str, Any]],
    source_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in decisions:
        if not isinstance(raw, dict):
            raise ValueError("every review decision must be an object")
        issue_id = str(raw.get("issue_id") or "").strip()
        decision = str(raw.get("decision") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if not issue_id or issue_id not in source_by_id:
            raise ValueError(f"unknown review issue_id: {issue_id or '<empty>'}")
        if issue_id in seen:
            raise ValueError(f"duplicate review issue_id: {issue_id}")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"invalid decision for {issue_id}: {decision}")
        if decision != "retain" and not reason:
            raise ValueError(f"reason is required for {decision}: {issue_id}")
        seen.add(issue_id)
        normalized.append(
            {
                "issue_id": issue_id,
                "decision": decision,
                "reason": reason,
                "evidence_refs": _string_list(raw.get("evidence_refs")),
            }
        )

    missing = sorted(set(source_by_id) - seen)
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"review decisions do not cover all issues; missing {len(missing)}: {preview}")
    return normalized


def _review_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
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
            "remark_judgment_label",
            "semantic_message",
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
    } | {"evidence_facts": _compact_evidence(item.get("evidence"))}


def _report_item(item: dict[str, Any]) -> dict[str, Any]:
    projected = _review_item(item)
    projected["review_reason"] = item.get("final_review", {}).get("reason", "")
    return projected


def _compact_evidence(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value[:2000]
        value = parsed
    if isinstance(value, dict):
        return {
            str(key): _compact_evidence(child)
            for key, child in value.items()
            if child not in (None, "", [], {})
            and key not in {
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
