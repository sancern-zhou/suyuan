"""组分站附件档案规则（wo_commonfile.typecode = ruleitemtag_监测项目，审核二期）。

- SUP_ATTACHMENT_REQUIRED_MISSING：维护检定/周质控类表单按档案要求报告或数据
  文件类附件，仅过程照片不满足；表单备注含豁免关键词（如"无需送检"）时跳过。
- SUP_ATTACHMENT_ITEM_MATCH：附件 typecode 监测项目后缀与表单 pollutanttype
  一致性；全部附件后缀与表单监测项目不符时判失败。

附件匹配口径：typecode 精确等于 ruleitemtag 或以 "ruleitemtag_" 为前缀。
"""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue
from app.services.ops_audit.rules.sup_form_rules import (
    SUP_FORM_PROFILES,
    attachment_filename,
    attachment_matches_tag,
    column_remark_text,
    form_item_tag,
    reload_sup_form_profiles,
)

MISSING_RULE_ID = "SUP_ATTACHMENT_REQUIRED_MISSING"
ITEM_MATCH_RULE_ID = "SUP_ATTACHMENT_ITEM_MATCH"

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic")


def check_sup_attachment_rules(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    attachments: list[dict[str, Any]],
    wo_commonfiles: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    """Run profile-driven attachment checks for sup forms of one work order."""

    # sup_form_rules 可能已刷新档案；此处跟随最新缓存。
    catalog = SUP_FORM_PROFILES.get("form_profiles") or {}
    if not catalog:
        reload_sup_form_profiles()
        catalog = SUP_FORM_PROFILES.get("form_profiles") or {}
    if not catalog:
        return
    defaults = SUP_FORM_PROFILES.get("defaults") or {}
    classes = defaults.get("attachment_classes") or {}
    exemption_keywords = [str(item) for item in defaults.get("attachment_exemption_keywords") or []]
    common_files = list(wo_commonfiles or []) + list(attachments or [])

    for table, form in forms:
        if form.get("_query_error"):
            continue
        tag = form_item_tag(form)
        if not tag:
            continue
        profile = catalog.get(tag)
        if not profile or profile.get("enabled") is False:
            continue
        display_name = profile.get("display_name") or tag
        tag_files = [record for record in common_files if attachment_matches_tag(record, tag)]
        form_remark = column_remark_text(form, None)

        _check_required_attachments(
            order,
            tag,
            display_name,
            form,
            form_remark,
            exemption_keywords,
            classes,
            tag_files,
            profile,
            issues,
        )
        _check_attachment_item_match(
            order,
            tag,
            display_name,
            form,
            tag_files,
            profile,
            issues,
        )

def _check_required_attachments(
    order: dict[str, Any],
    tag: str,
    display_name: str,
    form: dict[str, Any],
    form_remark: str,
    exemption_keywords: list[str],
    classes: dict[str, Any],
    tag_files: list[dict[str, Any]],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    requirements = profile.get("required_attachments") or []
    if not requirements:
        return
    if form_remark and any(keyword in form_remark for keyword in exemption_keywords):
        return
    missing = []
    for requirement in requirements:
        class_name = str(requirement.get("class") or "")
        class_spec = classes.get(class_name) or {}
        if _has_matching_attachment(tag_files, class_spec):
            continue
        missing.append(
            {
                "class": class_name,
                "description": class_spec.get("description") or class_name,
                "extensions": class_spec.get("extensions") or [],
                "filename_keywords": class_spec.get("filename_keywords") or [],
                "severity": requirement.get("severity") or "高",
                "suggestion": requirement.get("suggestion"),
            }
        )
    if not missing:
        return
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "attachment_count": len(tag_files),
        "sample_attachments": [
            {"typecode": _record_typecode(record), "filename": attachment_filename(record)}
            for record in tag_files[:12]
        ],
        "missing": missing,
    }
    first = missing[0]
    severity = str(first.get("severity") or "高")
    photo_count = sum(1 for record in tag_files if _is_image(record))
    suggestion = first.get("suggestion") or f"补充{first['description']}"
    message = (
        f"{display_name}：缺少{first['description']}（"
        f"现有附件 {len(tag_files)} 个，其中照片 {photo_count} 个），{suggestion}"
    )
    add_issue(
        issues,
        MISSING_RULE_ID,
        "附件清单",
        severity,
        f"sup_rf_common.{tag}.attachment.{first['class']}",
        message,
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_attachment_item_match(
    order: dict[str, Any],
    tag: str,
    display_name: str,
    form: dict[str, Any],
    tag_files: list[dict[str, Any]],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    if profile.get("item_match_enabled") is False:
        return
    pollutant = _form_pollutant(form)
    if not pollutant or not tag_files:
        return
    matched, mismatched = _split_by_pollutant(tag_files, tag, pollutant)
    if matched or not mismatched:
        return
    # 全部附件的监测项目后缀与表单不符：附件与表单疑似不属于同一监测项目。
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "ruleitemtag": tag,
        "form_pollutant_type": pollutant,
        "mismatched_attachments": [
            {"typecode": _record_typecode(record), "filename": attachment_filename(record)}
            for record in mismatched[:12]
        ],
    }
    sample = mismatched[0]
    add_issue(
        issues,
        ITEM_MATCH_RULE_ID,
        "一致性",
        "高",
        f"sup_rf_common.{tag}.attachment.item_match",
        (
            f"{display_name}：表单监测项目为 {pollutant}，但全部附件类型码指向其他监测项目"
            f"（如 {_record_typecode(sample) or attachment_filename(sample)}），"
            "疑似附件与表单不一致"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _has_matching_attachment(tag_files: list[dict[str, Any]], class_spec: dict[str, Any]) -> bool:
    extensions = [str(item).lower() for item in class_spec.get("extensions") or []]
    keywords = [str(item).lower() for item in class_spec.get("filename_keywords") or []]
    for record in tag_files:
        filename = attachment_filename(record)
        lower = filename.lower()
        if extensions and any(lower.endswith(ext) for ext in extensions):
            return True
        if keywords and any(keyword in lower for keyword in keywords):
            return True
    return False


def _form_pollutant(form: dict[str, Any]) -> str | None:
    for key in ("POLLUTANTTYPE", "pollutanttype", "PollutantType"):
        value = form.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _split_by_pollutant(
    tag_files: list[dict[str, Any]], tag: str, pollutant: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 typecode 监测项目后缀分组：后缀 = typecode 去掉 "tag_" 前缀的剩余部分。"""

    matched = []
    mismatched = []
    normalized = pollutant.strip().lower().replace("-", "").replace("_", "")
    prefix = f"{tag.strip().lower()}_"
    for record in tag_files:
        typecode = _record_typecode(record)
        lower = typecode.lower()
        suffix = typecode[len(prefix):] if lower.startswith(prefix) else typecode
        suffix_normalized = suffix.strip().lower().replace("-", "").replace("_", "")
        filename = attachment_filename(record).lower()
        if (suffix_normalized and suffix_normalized == normalized) or (
            not suffix_normalized and normalized in filename
        ):
            matched.append(record)
        else:
            mismatched.append(record)
    return matched, mismatched


def _record_typecode(record: dict[str, Any]) -> str:
    return str(
        record.get("TYPECODE") or record.get("typecode") or record.get("TypeCode") or ""
    ).strip()


def _is_image(record: dict[str, Any]) -> bool:
    filename = attachment_filename(record).lower()
    return any(filename.endswith(ext) for ext in _IMAGE_EXTENSIONS)
