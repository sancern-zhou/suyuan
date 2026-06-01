"""Attachment inventory rules for operations work order audits."""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.config import load_attachment_requirements
from app.services.ops_audit.models import Issue
from app.services.ops_audit.semantic.attachment_classifier import classify_attachment_metadata
from app.services.ops_audit.rules.base import add_issue


ATTACHMENT_PROFILE = load_attachment_requirements()


def check_attachment_requirements(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Check required attachment presence using metadata only."""

    rf_tables = {table for table, form in forms if not form.get("_query_error")}
    inventory = build_attachment_inventory(attachments, wo_commonfiles)
    matched_requirements = [
        requirement
        for requirement in ATTACHMENT_PROFILE.get("requirements", [])
        if _requirement_applies(requirement, order, rf_tables)
    ]
    if not matched_requirements:
        return

    for requirement in matched_requirements:
        if _requirement_is_not_applicable(requirement, forms):
            continue
        required_types = [str(item) for item in requirement.get("required_types", []) if item]
        if requirement.get("id") == "MONTH_STATION_MAINTAIN_PHOTOS":
            _add_station_maintain_photo_semantic_candidate(order, requirement, inventory, issues)
            continue
        missing_types, filename_semantic_review = _resolve_missing_attachment_types(
            order,
            requirement,
            required_types,
            inventory,
        )
        if "report" in missing_types and inventory["type_counts"].get("photo"):
            _add_report_only_photo_issue(order, requirement, inventory, issues)
            remaining_missing_types = [item for item in missing_types if item != "report"]
            if remaining_missing_types:
                _add_missing_issue(order, requirement, remaining_missing_types, inventory, issues, filename_semantic_review)
            continue
        if missing_types:
            _add_missing_issue(order, requirement, missing_types, inventory, issues, filename_semantic_review)
            continue


def build_attachment_inventory(
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return normalized attachment metadata and coarse type counts."""

    items = []
    for source, records in (("wo_commonfile_links", attachments), ("WO_COMMONFILE", wo_commonfiles)):
        for record in records:
            descriptor = _attachment_descriptor(record)
            types = _classify_attachment(descriptor)
            items.append(
                {
                    "source": source,
                    "name": _first_present(record, _name_fields()),
                    "typecode": _first_present(record, ["TYPECODE", "typecode", "TypeCode", "FUNCTIONCODE", "functioncode"]),
                    "created_at": _first_present(record, ["CREATEDATE", "createdate", "CreateDate", "UPLOADTIME", "uploadtime"]),
                    "descriptor": descriptor[:500],
                    "types": sorted(types),
                }
            )

    type_counts: dict[str, int] = {}
    for item in items:
        for attachment_type in item["types"]:
            type_counts[attachment_type] = type_counts.get(attachment_type, 0) + 1
    return {
        "attachment_count": len(items),
        "type_counts": type_counts,
        "items": items,
    }


def attachment_review_candidate_rule_ids() -> set[str]:
    return {"ATTACHMENT_REQUIRED_MISSING", "ATTACHMENT_REPORT_MISSING"}


def _requirement_applies(requirement: dict[str, Any], order: dict[str, Any], rf_tables: set[str]) -> bool:
    if requirement.get("enabled") is False:
        return False

    order_types = {str(item) for item in requirement.get("order_types", [])}
    if order_types and str(order.get("DDWORKINGORDERTYPE") or "") not in order_types:
        return False

    maintenance_types = {str(item) for item in requirement.get("maintenance_types", [])}
    maintenance_type = str(order.get("MAINTENANCETYPE") or "")
    if maintenance_types and maintenance_type not in maintenance_types:
        return False

    required_rf_tables = {str(item) for item in requirement.get("rf_tables", [])}
    if required_rf_tables and not (required_rf_tables & rf_tables):
        return False

    title_keywords = [str(item).lower() for item in requirement.get("title_keywords", [])]
    if title_keywords:
        title_text = f"{order.get('ORDERTITLE') or ''} {order.get('ORDERCONTENT') or ''}".lower()
        if not any(keyword in title_text for keyword in title_keywords):
            return False
    return True


def _requirement_is_not_applicable(requirement: dict[str, Any], forms: list[tuple[str, dict[str, Any]]]) -> bool:
    relevant_forms = _requirement_forms(requirement, forms)
    if not relevant_forms:
        return False

    text = " ".join(_form_exemption_text(form) for _table, form in relevant_forms)
    if _has_not_applicable_device_marker(text):
        return True
    if requirement.get("id") == "MONTH_STATION_MAINTAIN_PHOTOS" and _has_special_station_maintenance_marker(text):
        return True
    return False


def _requirement_forms(requirement: dict[str, Any], forms: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    required_rf_tables = {str(item) for item in requirement.get("rf_tables", [])}
    if not required_rf_tables:
        return forms
    return [(table, form) for table, form in forms if table in required_rf_tables and not form.get("_query_error")]


def _form_exemption_text(form: dict[str, Any]) -> str:
    fields = (
        "REMARK",
        "Remark",
        "remark",
        "DESCRIPTION",
        "Description",
        "DESCRIPTIONTA",
        "SITUATION",
        "Situation",
    )
    return " ".join(str(form.get(field) or "").strip() for field in fields if str(form.get(field) or "").strip())


def _has_not_applicable_device_marker(text: str) -> bool:
    markers = (
        "无该设备",
        "无此设备",
        "无对应设备",
        "无设备",
        "未配置",
        "不适用",
        "无需",
        "无此项",
    )
    return any(marker in text for marker in markers)


def _has_special_station_maintenance_marker(text: str) -> bool:
    markers = (
        "流动监测车",
        "监测车",
        "非常规",
        "不完全一样",
        "停运状态",
    )
    return any(marker in text for marker in markers)


def _add_missing_issue(
    order: dict[str, Any],
    requirement: dict[str, Any],
    missing_types: list[str],
    inventory: dict[str, Any],
    issues: list[Issue],
    filename_semantic_review: dict[str, Any] | None = None,
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "requirement_id": requirement.get("id"),
        "requirement_name": requirement.get("name"),
        "required_types": requirement.get("required_types", []),
        "missing_types": missing_types,
        "attachment_count": inventory["attachment_count"],
        "type_counts": inventory["type_counts"],
        "sample_attachments": inventory["items"][:8],
    }
    if filename_semantic_review:
        evidence["filename_semantic_review"] = filename_semantic_review
    add_issue(
        issues,
        "ATTACHMENT_REQUIRED_MISSING",
        "附件清单",
        str(requirement.get("severity") or "高"),
        f"attachment.{requirement.get('id')}.missing",
        f"{requirement.get('name') or '必需附件'}缺失：{', '.join(missing_types)}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_report_only_photo_issue(
    order: dict[str, Any],
    requirement: dict[str, Any],
    inventory: dict[str, Any],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "requirement_id": requirement.get("id"),
        "requirement_name": requirement.get("name"),
        "attachment_count": inventory["attachment_count"],
        "type_counts": inventory["type_counts"],
        "sample_attachments": inventory["items"][:8],
    }
    add_issue(
        issues,
        "ATTACHMENT_REPORT_MISSING",
        "附件清单",
        "中",
        f"attachment.{requirement.get('id')}.report",
        f"{requirement.get('name') or '报告类附件'}疑似只有照片，缺少报告文件",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_station_maintain_photo_semantic_candidate(
    order: dict[str, Any],
    requirement: dict[str, Any],
    inventory: dict[str, Any],
    issues: list[Issue],
) -> None:
    sample_attachments = _requirement_relevant_attachments(requirement, inventory)
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "requirement_id": requirement.get("id"),
        "requirement_name": requirement.get("name"),
        "required_types": requirement.get("required_types", []),
        "attachment_count": inventory["attachment_count"],
        "type_counts": inventory["type_counts"],
        "sample_attachments": sample_attachments,
    }
    add_issue(
        issues,
        "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING",
        "附件清单",
        str(requirement.get("severity") or "中"),
        f"attachment.{requirement.get('id')}.filename_semantics",
        f"{requirement.get('name') or '站点设备维护现场照片'}需通过文件名语义判断是否覆盖必需照片类型",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _resolve_missing_attachment_types(
    order: dict[str, Any],
    requirement: dict[str, Any],
    required_types: list[str],
    inventory: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    return [
        attachment_type
        for attachment_type in required_types
        if not inventory["type_counts"].get(attachment_type)
    ], None


def _requirement_relevant_attachments(requirement: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(inventory.get("items") or [])
    if requirement.get("id") != "MONTH_STATION_MAINTAIN_PHOTOS":
        return items[:20]

    rf_tables = [str(item) for item in requirement.get("rf_tables", []) if str(item).strip()]
    relevant = [
        item
        for item in items
        if _matches_any_rf_table_alias(
            " ".join(
                str(value or "")
                for value in (item.get("typecode"), item.get("descriptor"), item.get("name"))
            ),
            rf_tables,
        )
    ]
    return _dedupe_attachments(relevant or items)[:50]


def _matches_any_rf_table_alias(text: str, rf_tables: list[str]) -> bool:
    normalized_text = _normalize_alias(text)
    if not normalized_text:
        return False
    return any(_normalize_alias(table) in normalized_text for table in rf_tables)


def _normalize_alias(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _dedupe_attachments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("name") or ""), str(item.get("descriptor") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _requirement_relevant_attachments(requirement: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(inventory.get("items") or [])
    if requirement.get("id") != "MONTH_STATION_MAINTAIN_PHOTOS":
        return items[:20]

    rf_tables = [str(item) for item in requirement.get("rf_tables", []) if str(item).strip()]
    relevant = [
        item
        for item in items
        if _matches_any_rf_table_alias(
            " ".join(
                str(value or "")
                for value in (item.get("typecode"), item.get("descriptor"), item.get("name"))
            ),
            rf_tables,
        )
    ]
    return _dedupe_attachments(relevant or items)[:50]


def _matches_any_rf_table_alias(text: str, rf_tables: list[str]) -> bool:
    normalized_text = _normalize_alias(text)
    if not normalized_text:
        return False
    return any(_normalize_alias(table) in normalized_text for table in rf_tables)


def _normalize_alias(value: str) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _dedupe_attachments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("name") or ""), str(item.get("descriptor") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


SEMANTIC_FILENAME_ATTACHMENT_TYPES = {
    "particle_clock_photo",
    "data_logger_clock_photo",
    "filter_cleaning_photo",
}


def _classify_attachment(descriptor: str) -> set[str]:
    classified_types = set(
        classify_attachment_metadata(
            descriptor,
            filename=_descriptor_file_name(descriptor),
            global_keywords=ATTACHMENT_PROFILE.get("global_keywords", {}),
            photo_extensions=ATTACHMENT_PROFILE.get("photo_extensions", []),
        )["types"]
    )
    return classified_types - SEMANTIC_FILENAME_ATTACHMENT_TYPES


def _attachment_descriptor(record: dict[str, Any]) -> str:
    values = []
    for field in _name_fields() + ["REMARK", "remark", "FILEPATH", "filepath", "URL", "url", "CONTENTTYPE", "contenttype"]:
        value = record.get(field)
        if value is not None and str(value).strip():
            values.append(str(value))
    if not values:
        values = [str(value) for value in record.values() if value is not None and str(value).strip()]
    return " ".join(values)


def _descriptor_file_name(descriptor: str) -> str:
    return descriptor.replace("\\", "/").split("/")[-1].split()[0] if descriptor else ""


def _name_fields() -> list[str]:
    return [
        "FILENAME",
        "filename",
        "FileName",
        "FILE_NAME",
        "NAME",
        "name",
        "ORIGINALFILENAME",
        "originalfilename",
        "COMMONFILENAME",
        "commonfilename",
        "TITLE",
        "title",
    ]


def _first_present(record: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return value
    return None
