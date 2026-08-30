"""Final issue list assembly for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from app.services.ops_audit.config import review_stage_for_rule, rules_for_review_stage
from app.services.ops_audit.field_labels import remark_field_display_name
from app.services.ops_audit.issue_linking import (
    ABNORMAL_WITHOUT_EXPLANATION_RULE_ID,
    is_abnormal_fact_rule,
    issue_link_metadata,
)
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
            if stage in {"future_ocr", "semantic_remark", "technical_diagnostic"}:
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

    _assign_issue_ids(items)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "final_issue_list_for_reporting",
        "issue_count": len(items),
        "affected_order_count": len({item["working_order_code"] for item in items if item.get("working_order_code")}),
        "stage_counts": _count_by(items, "review_stage"),
        "component_counts": _count_present_by(items, "issue_component"),
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
    if evidence.get("needs_semantic_review") is True and not is_abnormal_fact_rule(rule_id):
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
    _attach_range_decision_evidence(item, evidence_data)
    _attach_evidence_remarks(item, evidence_data)
    link_metadata = issue_link_metadata(issue, working_order_code=record.get("working_order_code"))
    if link_metadata:
        item.update(link_metadata)
        item["review_status"] = (
            "pending_semantic_review"
            if link_metadata.get("issue_component") == "abnormal_explanation_issue"
            else "rule_detected"
        )
    return item


def _attach_range_decision_evidence(
    item: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    """Expose the range comparison without requiring consumers to parse evidence JSON."""

    values = evidence.get("out_of_spec_values")
    range_value = values[0] if isinstance(values, list) and values and isinstance(values[0], dict) else {}
    observed = evidence.get("observed_value")
    expected = evidence.get("expected_range")
    if not isinstance(observed, dict) or not isinstance(expected, dict):
        if not range_value:
            return
        observed = {
            "raw_value": range_value.get("raw_value"),
            "normalized_value": range_value.get("value"),
            "raw_unit": range_value.get("raw_unit"),
            "normalized_unit": range_value.get("unit"),
            "unit_conversion_applied": _units_differ(range_value.get("raw_unit"), range_value.get("unit")),
        }
        expected = {
            "min": range_value.get("min"),
            "max": range_value.get("max"),
            "operator": range_value.get("operator"),
            "unit": range_value.get("unit"),
            "text": _range_text(range_value),
        }

    item["decision_evidence"] = {
        "brand": evidence.get("brand"),
        "field": evidence.get("field") or range_value.get("field") or item.get("rf_field"),
        "field_label": evidence.get("field_label") or range_value.get("label") or item.get("field_label"),
        "raw_value": observed.get("raw_value"),
        "normalized_value": observed.get("normalized_value"),
        "raw_unit": observed.get("raw_unit"),
        "normalized_unit": observed.get("normalized_unit"),
        "unit_conversion_applied": bool(observed.get("unit_conversion_applied")),
        "expected_range": expected.get("text") or _range_text(expected),
        "expected_min": expected.get("min"),
        "expected_max": expected.get("max"),
        "expected_operator": expected.get("operator"),
        "expected_unit": expected.get("unit"),
        "comparison_result": "out_of_spec",
    }


def _attach_evidence_remarks(
    item: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    candidates = None
    for key in ("handling_record_candidates", "remark_candidates"):
        if key in evidence:
            candidates = evidence.get(key)
            break
    if candidates is None:
        return

    entries = _remark_entries(candidates)
    nonempty_entries = [entry for entry in entries if entry["value"].strip()]
    item["remark_status"] = "provided" if nonempty_entries else "missing"
    item["remark_status_label"] = "已填写" if nonempty_entries else "未填写"
    item["original_remarks"] = [
        {**entry, "field_label": remark_field_display_name(entry["field"])}
        for entry in nonempty_entries
    ]
    item["original_remark_text"] = "\n".join(entry["value"] for entry in nonempty_entries)
    if nonempty_entries:
        item["remark_review_status"] = (
            "pending_semantic_review"
            if evidence.get("needs_semantic_review") is True
            else "not_requested"
        )
        item["remark_review_status_label"] = (
            "内容有效性待语义复核"
            if evidence.get("needs_semantic_review") is True
            else "已记录，未要求语义复核"
        )
    else:
        item["remark_review_status"] = "missing"
        item["remark_review_status_label"] = "未填写备注"


def _units_differ(source: Any, target: Any) -> bool:
    source_text = str(source or "").strip().lower()
    target_text = str(target or "").strip().lower()
    return bool(source_text and target_text and source_text != target_text)


def _range_text(spec: dict[str, Any]) -> str:
    operator = str(spec.get("operator") or "").strip()
    minimum = spec.get("min")
    maximum = spec.get("max")
    unit = str(spec.get("unit") or "").strip()
    if operator in {">", ">="} and minimum is not None and maximum is None:
        value = f"{operator}{minimum}"
    elif operator in {"<", "<="} and maximum is not None and minimum is None:
        value = f"{operator}{maximum}"
    elif minimum is not None and maximum is not None:
        value = f"{minimum}-{maximum}"
    elif minimum is not None:
        value = f">={minimum}"
    elif maximum is not None:
        value = f"<={maximum}"
    else:
        value = "未配置"
    return f"{value} {unit}".strip()


def _semantic_item(
    result: dict[str, Any],
    rule_id: str,
    record_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source_item = _semantic_item_from_source_issue(result, rule_id, record_context)
    if source_item is not None:
        return source_item
    if rule_id == "RF_ABNORMAL_VALUE_NO_REMARK":
        # An abnormal-remark conclusion must remain attached to the concrete
        # range/missing/result issue that caused review. Never synthesize a
        # standalone business issue after that source was excluded or absent.
        return None

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
    if rule_id == ABNORMAL_WITHOUT_EXPLANATION_RULE_ID:
        base["value_abnormal_message"] = base.get("message")
        base["message"] = _semantic_problem_description(result) or "异常说明缺失或无效。"
        base["review_status"] = "semantic_confirmed"
        _attach_original_remarks(base, result, source_issue)
    return base


def _attach_original_remarks(
    item: dict[str, Any],
    result: dict[str, Any],
    source_issue: dict[str, Any],
) -> None:
    """Keep the exact remark text beside the semantic conclusion for reporting."""

    evidence = _parse_evidence(source_issue.get("evidence"))
    has_source_candidates = "remark_candidates" in evidence
    entries = _remark_entries(evidence.get("remark_candidates"))
    if not has_source_candidates:
        remark_review = result.get("remark_review")
        reviewed_remark = remark_review.get("remark") if isinstance(remark_review, dict) else None
        fallback_entries = _remark_entries(reviewed_remark, default_field="semantic_review_input")
        if any(entry["value"].strip() for entry in fallback_entries):
            entries = fallback_entries

    nonempty_entries = [entry for entry in entries if entry["value"].strip()]
    item["remark_status"] = "provided" if nonempty_entries else "missing"
    item["original_remarks"] = [
        {**entry, "field_label": remark_field_display_name(entry["field"])}
        for entry in nonempty_entries
    ]
    item["original_remark_text"] = "\n".join(entry["value"] for entry in nonempty_entries)
    remark_review = result.get("remark_review")
    judgment_type = (
        str(result.get("remark_judgment") or remark_review.get("judgment_type") or "").strip()
        if isinstance(remark_review, dict)
        else str(result.get("remark_judgment") or "").strip()
    )
    item["remark_judgment"] = _effective_remark_judgment(judgment_type, nonempty_entries)
    item["remark_judgment_label"] = _remark_judgment_label(item["remark_judgment"])
    item["remark_status_label"] = "已填写" if nonempty_entries else "未填写"
    item["remark_review_status"] = "semantic_confirmed"
    item["remark_review_status_label"] = item["remark_judgment_label"]


def _remark_entries(value: Any, *, default_field: str = "remark") -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_entry(field: Any, raw_value: Any) -> None:
        field_text = str(field or default_field)
        if _remark_field_tail(field_text).upper() == "PROCESSTYPE":
            return
        text = str(raw_value or "")
        key = (field_text, text)
        if key in seen:
            return
        seen.add(key)
        entries.append({"field": key[0], "value": text})

    def visit(node: Any, field: str) -> None:
        if isinstance(node, dict):
            for child_field, child_value in node.items():
                visit(child_value, _join_remark_field(field, child_field))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                if isinstance(child, dict):
                    visit(child, field)
                    continue
                child_field, child_value = _split_embedded_remark_field(child)
                if child_field:
                    add_entry(_join_remark_field(field, child_field), child_value)
                else:
                    add_entry(field, child_value)
            return
        add_entry(field, node)

    if value is not None:
        visit(value, default_field)
    return entries


def _join_remark_field(parent: str, child: Any) -> str:
    child_text = str(child or "").strip()
    if not child_text:
        return parent
    if not parent or parent == "remark":
        return child_text
    return f"{parent}.{child_text}"


def _remark_field_tail(field: str) -> str:
    for separator in (".", "/"):
        if separator in field:
            field = field.rsplit(separator, 1)[1]
    return field


def _split_embedded_remark_field(value: Any) -> tuple[str | None, Any]:
    text = str(value or "")
    if "=" not in text:
        return None, value
    field, content = text.split("=", 1)
    field = field.strip()
    if not field:
        return None, value
    if not all(char.isalnum() or char == "_" for char in field):
        return None, value
    return field, content


def _effective_remark_judgment(
    semantic_judgment: str,
    entries: list[dict[str, str]],
) -> str:
    if not entries:
        return "missing"
    if all(entry["value"].strip() in {"/", "-", "--", "无", "未填", "不适用", "无备注", "暂无"} for entry in entries):
        return "placeholder"
    if semantic_judgment in {"missing", "placeholder", "unrelated", "contradictory", "valid"}:
        return semantic_judgment
    return "unrelated"


def _remark_judgment_label(value: str) -> str:
    return {
        "missing": "未填写",
        "placeholder": "占位内容",
        "unrelated": "与当前异常无关",
        "contradictory": "与异常证据矛盾",
        "valid": "有效说明",
    }.get(value, "说明有效性待确认")


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
    if review_stage_for_rule(rule_id) == "technical_diagnostic":
        return True
    if _is_flow_visual_rule(rule_id) and not _flow_visual_issue_can_promote(issue):
        return True
    evidence = _parse_evidence(issue.get("evidence"))
    reason_rule_id = str(evidence.get("reason_rule_id") or "")
    if rule_id == "RF_ABNORMAL_VALUE_NO_REMARK" and not reason_rule_id:
        has_concrete_abnormal_source = bool(
            evidence.get("rf_table")
            and (evidence.get("field") or evidence.get("abnormal_field"))
            and evidence.get("needs_semantic_review") is True
        )
        if not has_concrete_abnormal_source:
            return True
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


def issue_id_for_item(item: dict[str, Any]) -> str:
    """Return a stable identity that distinguishes repeated rules in one order."""

    identity = {
        "working_order_code": str(item.get("working_order_code") or ""),
        "rf_table": str(item.get("rf_table") or ""),
        "rf_record_key": str(item.get("rf_record_key") or ""),
        "pollutant_type": str(item.get("pollutant_type") or ""),
        "rule_id": str(item.get("rule_id") or ""),
        "issue_group_id": str(item.get("issue_group_id") or ""),
        "issue_component": str(item.get("issue_component") or ""),
        "field": str(item.get("field") or ""),
        "message": str(item.get("message") or ""),
    }
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"ops_issue_v1_{sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def ensure_issue_ids(issue_list: dict[str, Any]) -> dict[str, Any]:
    """Add issue IDs in place for current and legacy final issue lists."""

    _assign_issue_ids(issue_list.get("items", []))
    return issue_list


def _assign_issue_ids(items: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for item in items:
        issue_id = str(item.get("issue_id") or issue_id_for_item(item))
        if issue_id in seen:
            raise ValueError(f"duplicate final issue identity: {issue_id}")
        seen.add(issue_id)
        item["issue_id"] = issue_id


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


def _count_present_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return _count_by([item for item in items if item.get(key)], key)
