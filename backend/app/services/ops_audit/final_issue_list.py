"""Final issue list assembly for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import review_stage_for_rule, rules_for_review_stage
from app.services.ops_audit.rf_form_names import rf_form_display_name


EXCLUDED_RULE_IDS = rules_for_review_stage("excluded")


def build_final_issue_list(
    audit: dict[str, Any],
    semantic_review_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured issue list that reports should consume."""

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    record_context_by_code = {
        str(record.get("working_order_code")): record
        for record in audit.get("records", [])
        if record.get("working_order_code")
    }
    for record in audit.get("records", []):
        for issue in record.get("scoring_issues", []):
            if _should_exclude_issue(issue):
                continue
            stage = review_stage_for_rule(issue.get("rule_id"))
            if stage in {"future_ocr", "semantic_remark"}:
                continue
            item = _issue_item(record, issue, stage)
            key = _item_key(item)
            if key not in seen:
                seen.add(key)
                items.append(item)

    for result in (semantic_review_results or {}).get("results", []):
        if not result.get("can_promote_to_final_issue"):
            continue
        for rule_id in result.get("supported_rule_ids", []):
            if rule_id in EXCLUDED_RULE_IDS:
                continue
            context = record_context_by_code.get(str(result.get("working_order_code") or ""))
            item = _semantic_item(result, rule_id, context)
            if item is None:
                continue
            key = _item_key(item)
            if key not in seen:
                seen.add(key)
                items.append(item)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "final_issue_list_for_reporting",
        "issue_count": len(items),
        "affected_order_count": len({item["working_order_code"] for item in items if item.get("working_order_code")}),
        "stage_counts": _count_by(items, "review_stage"),
        "rule_counts": _count_by(items, "rule_id"),
        "items": items,
    }


def _should_exclude_issue(issue: dict[str, Any]) -> bool:
    rule_id = str(issue.get("rule_id") or "")
    if rule_id in EXCLUDED_RULE_IDS:
        return True
    if _is_flow_visual_rule(rule_id) and not _flow_visual_issue_can_promote(issue):
        return True
    evidence = _parse_evidence(issue.get("evidence"))
    if evidence.get("needs_semantic_review") is True:
        return True
    reason_rule_id = str(evidence.get("reason_rule_id") or "")
    if reason_rule_id in EXCLUDED_RULE_IDS:
        return True
    if rule_id == "RF_REQUIRED_FIELD_LOW_VALUE":
        return _required_field_issue_is_remark_only(issue)
    return False


def _required_field_issue_is_remark_only(issue: dict[str, Any]) -> bool:
    try:
        evidence = json.loads(issue.get("evidence") or "{}")
    except Exception:
        return False
    fields = list(evidence.get("empty_fields") or []) + list(evidence.get("low_value_fields") or [])
    if not fields:
        return False
    return all(str(field).split(".", 1)[0] == "备注" for field in fields)


def _issue_item(record: dict[str, Any], issue: dict[str, Any], stage: str) -> dict[str, Any]:
    evidence_data = _parse_evidence(issue.get("evidence"))
    rf_table = _rf_table_from_evidence(evidence_data) or _rf_table_from_field(issue.get("field"))
    item = {
        "working_order_code": record.get("working_order_code"),
        "station_id": record.get("station_id"),
        "station_name": record.get("station_name"),
        "operation_unit": record.get("operation_unit"),
        "order_type": record.get("order_type"),
        "maintenance_type": record.get("maintenance_type"),
        "rf_table": rf_table,
        "rf_form_name": rf_form_display_name(rf_table),
        "rf_field": evidence_data.get("field") or _rf_field_from_field(issue.get("field")),
        "rf_record_key": _rf_record_key(evidence_data),
        "pollutant_type": evidence_data.get("pollutant_type"),
        "field_label": evidence_data.get("field_label"),
        "rule_id": issue.get("rule_id"),
        "category": issue.get("category"),
        "review_stage": stage,
        "source": "rule_engine",
        "field": issue.get("field"),
        "message": issue.get("message"),
        "evidence": issue.get("evidence"),
    }
    for key in (
        "report_classification",
        "needs_manual_review",
        "attachment_filename",
        "attachment_local_path",
        "attachment_original_path",
        "attachment_url",
        "model_result_path",
        "reason_code",
        "reason",
        "observed_summary",
        "form_concentrations",
        "concentration_unit",
        "evidence_images",
    ):
        if key in evidence_data:
            item[key] = evidence_data[key]
    return item


def _semantic_item(
    result: dict[str, Any],
    rule_id: str,
    record_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source_item = _semantic_item_from_source_issue(result, rule_id, record_context)
    if source_item is not None:
        return source_item

    rf_table = result.get("rf_table") or _rf_table_from_field(result.get("field"))
    return {
        "working_order_code": result.get("working_order_code"),
        "station_id": _context_value(result, record_context, "station_id"),
        "station_name": _context_value(result, record_context, "station_name"),
        "operation_unit": _context_value(result, record_context, "operation_unit"),
        "order_type": _context_value(result, record_context, "order_type"),
        "maintenance_type": _context_value(result, record_context, "maintenance_type"),
        "rf_table": rf_table,
        "rf_form_name": rf_form_display_name(rf_table),
        "rf_field": result.get("rf_field") or _rf_field_from_field(result.get("field")),
        "rf_record_key": result.get("rf_record_key"),
        "pollutant_type": result.get("pollutant_type"),
        "field_label": result.get("field_label"),
        "rule_id": rule_id,
        "category": "异常说明问题",
        "review_stage": "semantic_remark",
        "source": "semantic_review",
        "field": result.get("field") or "remark_closure",
        "message": _semantic_problem_description(result),
        "evidence": result.get("evidence_text") or result.get("remark_review", {}).get("remark"),
        "confidence": result.get("confidence"),
    }


def _semantic_item_from_source_issue(
    result: dict[str, Any],
    rule_id: str,
    record_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source_issue = _source_issue_for_rule(result, rule_id)
    if not source_issue:
        return None
    if _should_exclude_semantic_source_issue(source_issue):
        return None
    base = _issue_item(
        {
            "working_order_code": result.get("working_order_code"),
            "station_id": _context_value(result, record_context, "station_id"),
            "station_name": _context_value(result, record_context, "station_name"),
            "operation_unit": _context_value(result, record_context, "operation_unit"),
            "order_type": _context_value(result, record_context, "order_type"),
            "maintenance_type": _context_value(result, record_context, "maintenance_type"),
        },
        source_issue,
        "semantic_remark",
    )
    base["source"] = "semantic_review"
    base["confidence"] = result.get("confidence")
    _attach_semantic_supplement(base, result, source_issue)
    return base


def _attach_semantic_supplement(
    item: dict[str, Any],
    result: dict[str, Any],
    source_issue: dict[str, Any] | None = None,
) -> None:
    semantic_message = (
        _specialized_semantic_source_message(source_issue)
        if source_issue is not None
        else None
    ) or _semantic_problem_description(result)
    if semantic_message:
        item["semantic_message"] = semantic_message
    item["semantic_conclusion"] = result.get("conclusion")
    remark_review = result.get("remark_review")
    if isinstance(remark_review, dict):
        item["semantic_remark_review"] = remark_review
    order_description_review = result.get("order_description_review")
    if isinstance(order_description_review, dict):
        item["semantic_order_description_review"] = order_description_review


def _should_exclude_semantic_source_issue(issue: dict[str, Any]) -> bool:
    rule_id = str(issue.get("rule_id") or "")
    if rule_id in EXCLUDED_RULE_IDS:
        return True
    if _is_flow_visual_rule(rule_id) and not _flow_visual_issue_can_promote(issue):
        return True
    evidence = _parse_evidence(issue.get("evidence"))
    reason_rule_id = str(evidence.get("reason_rule_id") or "")
    if reason_rule_id in EXCLUDED_RULE_IDS:
        return True
    if rule_id == "RF_REQUIRED_FIELD_LOW_VALUE":
        return _required_field_issue_is_remark_only(issue)
    return False


def _is_flow_visual_rule(rule_id: str) -> bool:
    return rule_id in rules_for_review_stage("flow_visual")


def _flow_visual_issue_can_promote(issue: dict[str, Any]) -> bool:
    evidence = _parse_evidence(issue.get("evidence"))
    confidence = _float_or_none(evidence.get("vision_confidence"))
    threshold = 0.85
    if confidence is None or confidence < threshold:
        return False
    comparisons = evidence.get("comparisons")
    if not isinstance(comparisons, list):
        return False
    mismatches = [item for item in comparisons if isinstance(item, dict) and item.get("status") == "mismatch"]
    if not mismatches:
        return False
    return all(_flow_visual_mismatch_has_strong_evidence(item) for item in mismatches)


def _flow_visual_mismatch_has_strong_evidence(comparison: dict[str, Any]) -> bool:
    if not str(comparison.get("field") or "").strip():
        return False
    if comparison.get("visual_value") is None or comparison.get("form_value") is None:
        return False
    return bool(str(comparison.get("visual_unit") or "").strip())


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _context_value(
    result: dict[str, Any],
    record_context: dict[str, Any] | None,
    key: str,
) -> Any:
    value = result.get(key)
    if value not in (None, ""):
        return value
    if not record_context:
        return value
    return record_context.get(key)


def _semantic_problem_description(result: dict[str, Any]) -> Any:
    remark_review = result.get("remark_review") or {}
    order_description_review = result.get("order_description_review") or {}
    return (
        result.get("problem_description")
        or remark_review.get("problem_description")
        or order_description_review.get("problem_description")
        or result.get("conclusion")
    )


def _specialized_semantic_source_message(source_issue: dict[str, Any]) -> str | None:
    evidence = _parse_evidence(source_issue.get("evidence"))
    if (
        source_issue.get("rule_id") == "RF_TW_REMARK_LOW_VALUE"
        and evidence.get("rf_table") == "RF_TW_CleanCuttingHead"
        and evidence.get("field") == "CleaningRemark"
    ):
        return "双周切割头清洗未识别到清洗照片，备注仅说明已清洗，未提供照片缺失或清洗证据不足的合理说明。"
    return None


def _source_issue_for_rule(result: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    source_issue = result.get("source_issue")
    if isinstance(source_issue, dict) and source_issue.get("rule_id") == rule_id:
        return source_issue
    evidence_summary = result.get("evidence_summary") or {}
    sample_issues = evidence_summary.get("sample_issues") or []
    if not isinstance(sample_issues, list):
        return None
    for issue in sample_issues:
        if isinstance(issue, dict) and issue.get("rule_id") == rule_id:
            return issue
    return None


def _item_key(item: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(item.get("working_order_code") or ""),
        str(item.get("rf_table") or ""),
        str(item.get("rf_record_key") or ""),
        str(item.get("pollutant_type") or ""),
        str(item.get("rule_id") or ""),
        str(item.get("field") or ""),
        str(item.get("message") or ""),
    )


def _parse_evidence(evidence: Any) -> dict[str, Any]:
    if isinstance(evidence, dict):
        return evidence
    if not evidence:
        return {}
    try:
        parsed = json.loads(str(evidence))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rf_table_from_field(field: Any) -> str | None:
    text = str(field or "")
    parts = text.split(".")
    if len(parts) >= 2 and parts[0] in {"rf", "attachment"}:
        return parts[1]
    return None


def _rf_table_from_evidence(evidence: dict[str, Any]) -> str | None:
    for key in ("rf_table", "current_table"):
        value = str(evidence.get(key) or "").strip()
        if value:
            return value
    current_tables = evidence.get("current_tables")
    if isinstance(current_tables, list):
        tables = sorted({str(value).strip() for value in current_tables if str(value).strip()})
        if len(tables) == 1:
            return tables[0]
    comparisons = evidence.get("comparisons")
    if isinstance(comparisons, list):
        tables = sorted(
            {
                str(comparison.get("current_table") or comparison.get("compare_table") or "").strip()
                for comparison in comparisons
                if isinstance(comparison, dict)
                and str(comparison.get("current_table") or comparison.get("compare_table") or "").strip()
            }
        )
        if len(tables) == 1:
            return tables[0]
    return None


def _rf_field_from_field(field: Any) -> str | None:
    text = str(field or "")
    parts = text.split(".")
    if len(parts) >= 3 and parts[0] == "rf":
        return parts[-1]
    return None


def _rf_record_key(evidence: dict[str, Any]) -> str | None:
    rf_table = _rf_table_from_evidence(evidence)
    composite_parts = [
        str(evidence.get("working_order_code") or evidence.get("current_order_code") or "").strip(),
        str(rf_table or "").strip(),
        str(evidence.get("pollutant_type") or "").strip(),
        str(evidence.get("field") or "").strip(),
    ]
    compact_composite = [part for part in composite_parts if part]
    if len(compact_composite) >= 3:
        return "::".join(compact_composite)

    for key in (
        "rf_record_id",
        "record_id",
        "id",
        "Id",
        "RFWPMCHECKID",
        "working_order_code",
    ):
        value = evidence.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    parts = [
        str(evidence.get("working_order_code") or evidence.get("current_order_code") or "").strip(),
        str(rf_table or "").strip(),
        str(evidence.get("pollutant_type") or "").strip(),
        str(evidence.get("field") or "").strip(),
    ]
    compact = [part for part in parts if part]
    return "::".join(compact) if compact else None


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "<unknown>")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda entry: entry[0]))
