"""Layered evidence builders for operations work order audits."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.ops_audit.issue_linking import issue_link_metadata, parse_issue_evidence


def build_summary_evidence(dataset: dict[str, Any]) -> dict[str, Any]:
    """Build the default lightweight evidence layer.

    The summary layer keeps only order-level identifiers, workflow summary,
    RF table names, attachment counts, and device identity fields.
    """

    orders = dataset.get("orders", [])
    details_by_code = _group_details_by_order_code(dataset.get("details", []))
    forms_by_code = _group_rf_forms_by_order_code(dataset.get("rf_forms", {}))
    attachments_by_code = _group_by_order_code(dataset.get("attachments", []), ["refid", "REFID", "remark", "REMARK"])
    wo_commonfile_by_code = _group_by_order_code(dataset.get("wo_commonfile", []), ["REFID", "refid"])
    device_history = dataset.get("device_history") or {}

    records = []
    for order in orders:
        code = order.get("WORKINGORDERCODE")
        forms = forms_by_code.get(str(code), [])
        records.append(
            {
                "working_order_code": code,
                "station_id": order.get("STATIONID"),
                "device_id": order.get("DEVICEID"),
                "order_type": order.get("DDWORKINGORDERTYPE"),
                "maintenance_type": order.get("MAINTENANCETYPE"),
                "create_time": order.get("CREATETIME"),
                "finish_time": order.get("FINISHTIME"),
                "plan_finish_time": order.get("PLANFINISHTIME"),
                "status": order.get("DDWORKINGORDERSTATUS") or order.get("STATUS"),
                "title": order.get("ORDERTITLE"),
                "content": order.get("ORDERCONTENT"),
                "workflow_steps": [detail.get("PROCESSSTEP") for detail in details_by_code.get(str(code), [])],
                "rf_tables": sorted({table for table, _ in forms}),
                "attachment_count": len(attachments_by_code.get(str(code), [])) + len(wo_commonfile_by_code.get(str(code), [])),
                "device_identity": {
                    "brand": _first_non_empty(order, ["DEVICEBRAND", "BRAND"]),
                    "model": _first_non_empty(order, ["DEVICEMODEL", "MODEL"]),
                    "device_code": _first_non_empty(order, ["DEVICECODE", "DEVICECODEN"]),
                },
            }
        )

    return {
        "layer": "summary",
        "order_count": len(records),
        "records": records,
        "device_history": {
            "order_count": len(device_history.get("orders", [])),
            "history_days": device_history.get("query_info", {}).get("history_days"),
        },
    }


def build_structured_detail_evidence(
    dataset: dict[str, Any],
    *,
    working_order_code: str | None = None,
    rule_ids: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build structured detail evidence for a single order or a filtered subset."""

    summary = build_summary_evidence(dataset)
    order_map = {record["working_order_code"]: record for record in summary["records"]}
    order_codes = [working_order_code] if working_order_code else [record["working_order_code"] for record in summary["records"]]
    selected_codes = [code for code in order_codes if code in order_map]
    if limit > 0:
        selected_codes = selected_codes[:limit]

    details_by_code = _group_details_by_order_code(dataset.get("details", []))
    forms_by_code = _group_rf_forms_by_order_code(dataset.get("rf_forms", {}))
    attachments_by_code = _group_by_order_code(dataset.get("attachments", []), ["refid", "REFID", "remark", "REMARK"])
    wo_commonfile_by_code = _group_by_order_code(dataset.get("wo_commonfile", []), ["REFID", "refid"])
    device_history = dataset.get("device_history") or {}

    records = []
    for code in selected_codes:
        order = order_map[code]
        forms = forms_by_code.get(code, [])
        records.append(
            {
                "working_order_code": code,
                "rule_ids": rule_ids or [],
                "workflow_details": details_by_code.get(code, [])[:12],
                "rf_details": [
                    {
                        "table": table,
                        "fields": _rf_field_snapshot(form),
                    }
                    for table, form in forms[:12]
                ],
                "attachment_inventory": _attachment_inventory(attachments_by_code.get(code, []), wo_commonfile_by_code.get(code, [])),
                "device_history": _history_summary(device_history, code),
                "summary": order,
            }
        )

    return {
        "layer": "structured_detail",
        "count": len(records),
        "records": records,
    }


def build_raw_evidence(
    dataset: dict[str, Any],
    *,
    working_order_code: str | None = None,
    include_attachments: bool = False,
) -> dict[str, Any]:
    """Build raw evidence references without embedding large payloads."""

    structured = build_structured_detail_evidence(dataset, working_order_code=working_order_code)
    records = []
    for item in structured["records"]:
        raw = {
            "working_order_code": item["working_order_code"],
            "workflow_detail_count": len(item["workflow_details"]),
            "rf_detail_count": len(item["rf_details"]),
            "attachment_inventory": item["attachment_inventory"],
            "device_history": item["device_history"],
        }
        if include_attachments:
            raw["attachment_refs"] = item["attachment_inventory"].get("items", [])
        records.append(raw)
    return {
        "layer": "raw_evidence",
        "count": len(records),
        "records": records,
    }


def build_dataset_evidence(
    dataset: dict[str, Any],
    *,
    audit: dict[str, Any] | None = None,
    evidence_level: str = "summary",
    working_order_code: str | None = None,
    rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build the requested evidence layer bundle."""

    evidence_level = (evidence_level or "summary").strip().lower()
    bundle = {"summary": build_summary_evidence(dataset)}
    if audit is not None:
        bundle["issue_evidence"] = _build_split_issue_evidence(audit)
    if evidence_level in {"detail", "raw"}:
        bundle["structured_detail"] = build_structured_detail_evidence(
            dataset,
            working_order_code=working_order_code,
            rule_ids=rule_ids,
        )
    if evidence_level == "raw":
        bundle["raw_evidence"] = build_raw_evidence(dataset, working_order_code=working_order_code)
    return bundle


def _build_split_issue_evidence(audit: dict[str, Any]) -> dict[str, Any]:
    items = []
    component_counts: dict[str, int] = defaultdict(int)
    for record in audit.get("records", []):
        code = record.get("working_order_code")
        for issue in record.get("scoring_issues", []):
            metadata = issue_link_metadata(issue, working_order_code=code)
            if not metadata:
                continue
            evidence = parse_issue_evidence(issue.get("evidence"))
            component = metadata["issue_component"]
            item = {
                "working_order_code": code,
                "rule_id": issue.get("rule_id"),
                "rf_table": evidence.get("rf_table"),
                "field": issue.get("field"),
                "message": issue.get("message"),
                **metadata,
            }
            if component == "abnormal_explanation_issue":
                item["remark_evidence"] = {
                    "reason_rule_id": evidence.get("reason_rule_id"),
                    "abnormal_field": evidence.get("abnormal_field"),
                    "remark_candidates": evidence.get("remark_candidates") or {},
                    "needs_semantic_review": evidence.get("needs_semantic_review"),
                }
            else:
                item["fact_evidence"] = evidence
                if component in {"value_abnormal", "value_missing"}:
                    item["value_evidence"] = evidence
            component_counts[component] += 1
            items.append(item)
    return {
        "layer": "split_issue_evidence",
        "item_count": len(items),
        "component_counts": dict(component_counts),
        "items": items,
    }


def build_inspection_item(
    record: dict[str, Any],
    dataset: dict[str, Any] | None,
    *,
    focus_rule_id: str | None = None,
) -> dict[str, Any]:
    """Build an inspection item that mirrors the old inspect view."""

    item = {
        "working_order_code": record.get("working_order_code"),
        "station_id": record.get("station_id"),
        "order_type": record.get("order_type"),
        "maintenance_type": record.get("maintenance_type"),
        "audit_level": record.get("audit_level"),
        "matched_rules": [issue.get("rule_id") for issue in record.get("issues", [])],
        "deterministic_rules": record.get("deterministic_rules", []),
        "candidate_rules": record.get("candidate_rules", []),
        "deterministic_issue_count": record.get("deterministic_issue_count", 0),
        "candidate_issue_count": record.get("candidate_issue_count", 0),
        "issues": record.get("issues", [])[:12],
        "workflow_steps": record.get("workflow_steps", []),
        "rf_tables": record.get("rf_tables", []),
        "attachment_count": record.get("attachment_count", 0),
        "attachment_review_rules": record.get("attachment_review_rules", []),
    }
    if not dataset:
        return item

    code = record.get("working_order_code")
    details = [detail for detail in dataset.get("details", []) if detail.get("WORKINGORDERCODE") == code]
    rf_rows = []
    for table, rows in dataset.get("rf_forms", {}).items():
        for row in rows:
            if row.get("WORKINGORDERCODE") == code:
                rf_rows.append({"table": table, "fields": _rf_field_snapshot(row)})

    item["order_summary"] = _order_summary(dataset, code)
    item["workflow_summary"] = details[:12]
    item["rf_summary"] = rf_rows[:20]
    if focus_rule_id:
        item["focus_rule_id"] = focus_rule_id
    return item


def _group_by_order_code(records: list[dict[str, Any]], fields: list[str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        codes = set()
        for field in fields:
            value = record.get(field)
            if value is not None and str(value).strip():
                codes.add(str(value).strip())
        for code in codes:
            grouped[code].append(record)
    return grouped


def _group_details_by_order_code(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        code = record.get("WORKINGORDERCODE")
        if code:
            grouped[str(code)].append(record)
    return grouped


def _group_rf_forms_by_order_code(rf_forms: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for table, rows in rf_forms.items():
        for row in rows:
            code = row.get("WORKINGORDERCODE")
            if code:
                grouped[str(code)].append((table, row))
    return grouped


def _rf_field_snapshot(form: dict[str, Any]) -> dict[str, Any]:
    preferred_fields = [
        "WORKINGORDERCODE",
        "STATIONID",
        "DEVICEBRAND",
        "DEVICEMODEL",
        "DEVICECODE",
        "DEVICECODEN",
        "POLLUTANTTYPE",
        "CHECKTIME",
        "STARTTIME",
        "ENDTIME",
        "CREATEDATE",
        "PREPARERUSERID",
        "REVIEWUSERID",
        "AUDITORUSERID",
        "REMARK",
        "REMARKS",
        "CleaningRemark",
        "SUBMITREMARK",
        "DISPLAYVALUE",
        "MEASUREVALUE",
        "SENSORVALUE",
    ]
    snapshot = {}
    for field in preferred_fields:
        if field in form and form.get(field) is not None and str(form.get(field)).strip() != "":
            snapshot[field] = form.get(field)
    return snapshot


def _attachment_inventory(
    attachments: list[dict[str, Any]],
    wo_commonfile: list[dict[str, Any]],
) -> dict[str, Any]:
    items = []
    for source, records in (("wo_commonfile_links", attachments), ("WO_COMMONFILE", wo_commonfile)):
        for record in records:
            items.append(
                {
                    "source": source,
                    "name": _first_non_empty(record, ["filename", "FILENAME", "FileName", "NAME", "TITLE"]),
                    "upload_time": _first_non_empty(record, ["createdate", "CREATEDATE", "uploadtime", "UPLOADTIME"]),
                    "path": _first_non_empty(record, ["filepath", "FILEPATH", "url", "URL"]),
                    "hash": _first_non_empty(record, ["filehash", "FILEHASH", "md5", "MD5"]),
                }
            )
    return {
        "attachment_count": len(items),
        "items": items[:20],
        "summary": items[:8],
    }


def _history_summary(device_history: dict[str, Any], working_order_code: str) -> dict[str, Any]:
    history_orders = device_history.get("orders", []) or []
    history_rf_forms = device_history.get("rf_forms", {}) or {}
    return {
        "history_days": device_history.get("query_info", {}).get("history_days"),
        "order_count": len(history_orders),
        "sample_orders": history_orders[:5],
        "rf_tables": sorted(history_rf_forms.keys())[:12],
        "current_working_order_code": working_order_code,
    }


def _order_summary(dataset: dict[str, Any], working_order_code: str | None) -> dict[str, Any] | None:
    if not working_order_code:
        return None
    for order in dataset.get("orders", []):
        if order.get("WORKINGORDERCODE") == working_order_code:
            return order
    return None


def _first_non_empty(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return value
    return None
