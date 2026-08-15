"""Attachment inventory rules for operations work order audits."""

from __future__ import annotations

import json
from typing import Any
import re

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
        # 优先使用基于出厂编号的检查（针对 MONTH_FLOW_CHECK_REPORT）
        if check_attachment_requirements_by_factory_code(order, requirement, forms, inventory, issues):
            continue  # 已通过出厂编号检查，跳过原有检查

        required_types = [str(item) for item in requirement.get("required_types", []) if item]
        if requirement.get("id") == "MONTH_STATION_MAINTAIN_PHOTOS":
            _add_station_maintain_photo_semantic_candidate(order, requirement, inventory, issues)
            continue
        if _requirement_is_not_applicable(requirement, forms):
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
    if requirement.get("id") == "VISIBILITY_CALIBRATION_EVIDENCE" and _has_no_visibility_device_marker(text):
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


def _has_no_visibility_device_marker(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or ""))
    if not normalized:
        return False
    no_device_patterns = (
        r"无.*能见度.*(分析仪|仪器|设备|仪|传感器|检测仪)",
        r"未配置.*能见度.*(分析仪|仪器|设备|仪|传感器|检测仪)",
        r"无.*散射仪",
        r"未配置.*散射仪",
    )
    return any(re.search(pattern, normalized) for pattern in no_device_patterns)


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
    for missing_type in missing_types:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "requirement_id": requirement.get("id"),
            "requirement_name": requirement.get("name"),
            "required_types": requirement.get("required_types", []),
            "missing_type": missing_type,
            "missing_types": [missing_type],
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
            f"attachment.{requirement.get('id')}.{missing_type}.missing",
            f"{requirement.get('name') or '必需附件'}缺失：{missing_type}",
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
    any_of_types = [str(item) for item in requirement.get("any_of_types", []) if item]
    if any_of_types:
        if any(inventory["type_counts"].get(attachment_type) for attachment_type in any_of_types):
            return [], None
        return any_of_types, None

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
    if not descriptor:
        return ""
    # 保留带空格的完整文件名；扩展名提取由 metadata classifier 统一处理。
    match = re.search(
        r"([^\\/\r\n]*\.(?:jpg|jpeg|png|bmp|gif|webp|heic|pdf|doc|docx|xls|xlsx))(?=\s|$|/)",
        str(descriptor),
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return descriptor.replace("\\", "/").split("/")[-1].strip()


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


def _normalize_factory_code(value: Any) -> str:
    """标准化出厂编号：移除所有非字母数字字符并转为大写"""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _factory_code_from_text(text: Any) -> str:
    """从文本中提取出厂编号（支持标签和通用格式）"""
    value = str(text or "")
    # 匹配标签格式：出厂编号: xxx, Serial No: xxx 等
    label_match = re.search(
        r"(?:出厂编号|出厂号|设备编号|序列号|编号|Serial\s*No\.?|S/?N)[:：\s]*([A-Z0-9][A-Z0-9\-_/]{4,})",
        value,
        flags=re.IGNORECASE,
    )
    if label_match:
        return _normalize_factory_code(label_match.group(1))

    # 匹配完整出厂编号格式：字母数字组合，可能包含连字符
    # 优先匹配更长、更完整的格式（如 THM-703-A741905036）
    full_match = re.search(r"\b[A-Z]{2,4}[-_/]?\d{3,}[-_/]?[A-Z0-9]{4,}\b", value, flags=re.IGNORECASE)
    if full_match:
        return _normalize_factory_code(full_match.group(0))

    # 匹配通用格式：字母开头+6位以上数字+字母数字组合
    generic_match = re.search(r"\b[A-Z]\d{6,}[A-Z0-9]*\b", value, flags=re.IGNORECASE)
    if generic_match:
        return _normalize_factory_code(generic_match.group(0))

    return ""


def extract_factory_codes_from_form(form: dict[str, Any]) -> set[str]:
    """从RF表单中提取流量计出厂编号"""
    codes = set()

    # RF表单中可能的出厂编号字段（根据实际表单结构调整）
    factory_fields = [
        "REFERENCEFLOWMETERSERIALNO",  # 参考流量计出厂编号
        "FLOWMETERSERIALNO",            # 流量计出厂编号
        "STANDARDFLOWMETERNO",          # 标准流量计编号
        "FLOWMETERNO",                  # 流量计编号
        "FLOWMETERCODE",                # 流量计代码
        "STANDARDFLOWMETERCODE",        # 标准流量计代码
        "REFERENCEFLOWMETERCODE",       # 参考流量计代码
        # 可能的其他字段名变体
        "FLOWMETER_SERIALNO",
        "FLOWMETER_SERIAL_NO",
        "FLOWMETER_ID",
    ]

    for field in factory_fields:
        value = form.get(field)
        if value:
            normalized = _normalize_factory_code(value)
            if normalized and len(normalized) >= 4:  # 至少4位有效字符
                codes.add(normalized)

    return codes


def extract_factory_codes_from_attachments(items: list[dict[str, Any]]) -> set[str]:
    """从附件元数据中提取出厂编号（无需OCR）"""
    codes = set()

    for item in items:
        # 从文件名、备注等字段中提取
        text = " ".join([
            str(item.get("name", "")),
            str(item.get("descriptor", "")),
        ])

        code = _factory_code_from_text(text)
        if code and len(code) >= 4:  # 至少4位有效字符
            codes.add(code)

    return codes


def check_attachment_requirements_by_factory_code(
    order: dict[str, Any],
    requirement: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    inventory: dict[str, Any],
    issues: list[Issue],
) -> bool:
    """基于出厂编号检查附件完整性（ MONTH_FLOW_CHECK_REPORT 专用）

    返回 True 表示已处理，False 表示应继续原有的关键词检查
    """
    # 只对月度流量检查报告规则启用出厂编号检查
    if requirement.get("id") != "MONTH_FLOW_CHECK_REPORT":
        return False

    # 获取 RF_M_GASEOUSFLOWCHECK 表单
    relevant_forms = [
        (table, form) for table, form in forms
        if table in {"RF_M_GASEOUSFLOWCHECK", "RF_Q_GaseousFlowCheck"}
        and not form.get("_query_error")
    ]

    if not relevant_forms:
        return False  # 没有相关表单，使用原有检查

    # 从所有相关表单中提取出厂编号
    required_codes = set()
    for table, form in relevant_forms:
        form_codes = extract_factory_codes_from_form(form)
        required_codes.update(form_codes)

    if not required_codes:
        return False  # 表单中没有出厂编号信息，使用原有检查

    # 从附件中提取已有的出厂编号
    attachment_codes = extract_factory_codes_from_attachments(inventory.get("items", []))

    # 检查是否有缺失
    missing_codes = required_codes - attachment_codes

    if missing_codes:
        # 生成基于出厂编号的问题报告
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "requirement_id": requirement.get("id"),
            "requirement_name": requirement.get("name"),
            "required_factory_codes": sorted(required_codes),
            "found_factory_codes": sorted(attachment_codes),
            "missing_factory_codes": sorted(missing_codes),
            "attachment_count": inventory.get("attachment_count", 0),
            "sample_attachments": inventory.get("items", [])[:8],
        }

        add_issue(
            issues,
            "ATTACHMENT_REQUIRED_MISSING",
            "附件清单",
            str(requirement.get("severity", "高")),
            f"attachment.{requirement.get('id')}.factory_code_missing",
            f"{requirement.get('name') or '流量计证书'}缺失以下出厂编号对应的附件：{', '.join(sorted(missing_codes))}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )

        return True  # 已处理，不需要继续原有检查

    # 检查是否有证书类型附件（至少有一个包含出厂编号的证书）
    certificate_count = sum(
        1 for item in inventory.get("items", [])
        if "certificate" in item.get("types", [])
    )

    if certificate_count == 0:
        # 有出厂编号但没有识别到证书类型附件
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "requirement_id": requirement.get("id"),
            "requirement_name": requirement.get("name"),
            "required_factory_codes": sorted(required_codes),
            "found_factory_codes": sorted(attachment_codes),
            "note": "附件中包含出厂编号，但未识别到证书类型附件",
            "attachment_count": inventory.get("attachment_count", 0),
            "sample_attachments": inventory.get("items", [])[:8],
        }

        add_issue(
            issues,
            "ATTACHMENT_REQUIRED_MISSING",
            "附件清单",
            str(requirement.get("severity", "高")),
            f"attachment.{requirement.get('id')}.certificate_type_missing",
            f"{requirement.get('name') or '流量计证书'}：检测到出厂编号 {', '.join(sorted(attachment_codes))}，但未识别到证书类型附件",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )

        return True

    return True  # 检查通过，不需要继续原有检查
