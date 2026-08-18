"""Markdown report writer for deterministic ops audits."""

from __future__ import annotations

import json
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

EXCLUDED_REPORT_RULE_IDS = {
    "ATTACHMENT_FLOW_VISUAL_DIAGNOSTIC",
    "RF_AUDITOR_EMPTY",
    "RF_RANGE_UNIT_MISMATCH",
    "RF_REVIEW_EMPTY",
    "RF_REQUIRED_FIELD_LOW_VALUE",
}

ABNORMAL_FACT_COMPONENTS = {"value_abnormal", "value_missing", "abnormal_fact", "data_suspect"}
ABNORMAL_EXPLANATION_COMPONENTS = {"abnormal_explanation_issue", "abnormal_without_explanation"}
LINKED_ABNORMAL_COMPONENTS = ABNORMAL_FACT_COMPONENTS | ABNORMAL_EXPLANATION_COMPONENTS
ABNORMAL_FACT_LABELS = {
    "value_abnormal": "值异常",
    "value_missing": "值缺失",
    "abnormal_fact": "异常状态",
    "data_suspect": "数据疑点",
}


def _parse_date(value: str | None) -> str:
    if not value:
        return ""
    return value.split(" ")[0]


def _build_scope_title(records: list[dict[str, Any]]) -> str:
    create_times = sorted(
        record.get("create_time")
        for record in records
        if record.get("create_time")
    )
    if not create_times:
        return "运维工单审核报告"
    return f"运维工单审核报告（{_parse_date(create_times[0])} 至 {_parse_date(create_times[-1])} 创建）"


def _collect_visible_issues(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_issues: list[dict[str, Any]] = []
    for record in records:
        for issue in record.get("deterministic_issues") or record.get("scoring_issues") or []:
            if issue.get("rule_id") in EXCLUDED_REPORT_RULE_IDS:
                continue
            visible_issues.append(
                {
                    "working_order_code": record.get("working_order_code", ""),
                    "station_id": record.get("station_id", ""),
                    "order_type": record.get("order_type", ""),
                    "maintenance_type": record.get("maintenance_type", ""),
                    "rule_id": issue.get("rule_id", ""),
                    "message": issue.get("message", ""),
                }
            )
    return visible_issues


def _summarize_dataset(dataset: dict[str, Any] | None) -> dict[str, Any]:
    if not dataset:
        return {}

    orders = dataset.get("orders", [])
    details = dataset.get("details", [])
    rf_forms = dataset.get("rf_forms", {})
    attachments = dataset.get("attachments", [])
    devices = dataset.get("devices", [])
    wo_commonfile = dataset.get("wo_commonfile", [])

    rf_record_count = 0
    if isinstance(rf_forms, dict):
        rf_record_count = sum(len(value) for value in rf_forms.values() if isinstance(value, list))

    station_ids = {str(order.get("STATIONID")) for order in orders if order.get("STATIONID") is not None}
    order_type_counts = Counter(order.get("DDWORKINGORDERTYPE", "<空>") for order in orders)
    maintenance_type_counts = Counter(order.get("MAINTENANCETYPE", "<空>") for order in orders)

    return {
        "order_count": len(orders),
        "detail_count": len(details),
        "rf_table_count": len(rf_forms) if isinstance(rf_forms, dict) else 0,
        "rf_record_count": rf_record_count,
        "attachment_count": len(attachments),
        "wo_commonfile_count": len(wo_commonfile),
        "station_count": len(station_ids),
        "device_count": len(devices),
        "create_time_min": min((order.get("CREATETIME") for order in orders if order.get("CREATETIME")), default=""),
        "create_time_max": max((order.get("CREATETIME") for order in orders if order.get("CREATETIME")), default=""),
        "order_type_counts": OrderedDict(sorted(order_type_counts.items(), key=lambda item: item[0])),
        "maintenance_type_counts": OrderedDict(sorted(maintenance_type_counts.items(), key=lambda item: item[0])),
    }


def write_report(
    audit: dict[str, Any],
    path: Path,
    dataset: dict[str, Any] | None = None,
    final_issue_list: dict[str, Any] | None = None,
) -> None:
    records = audit["records"]
    visible_issues = _collect_visible_issues(records)
    visible_records = {
        issue["working_order_code"]
        for issue in visible_issues
    }
    dataset_summary = _summarize_dataset(dataset)

    lines = [
        f"# {_build_scope_title(records)}",
        "",
        f"- 生成时间：{audit['audit_info']['generated_at']}",
        f"- 审核阶段：{audit['audit_info']['rule_stage']}",
        f"- 工单数量：{audit['audit_info']['order_count']}",
        "",
    ]

    if dataset_summary:
        lines.extend(["", "## 数据覆盖情况", ""])
        lines.append(f"- 工单：{dataset_summary['order_count']} 条")
        lines.append(f"- 流程详情：{dataset_summary['detail_count']} 条")
        lines.append(f"- RF 表记录：{dataset_summary['rf_record_count']} 条")
        lines.append(f"- 附件：{dataset_summary['attachment_count']} 条")
        lines.append(f"- 站点：{dataset_summary['station_count']} 个")
        lines.append(f"- 通用文件：{dataset_summary['wo_commonfile_count']} 条")
        lines.append(f"- 设备记录：{dataset_summary['device_count']} 条")
        lines.extend(["", "### 工单类型分布", ""])
        for key, value in dataset_summary["order_type_counts"].items():
            lines.append(f"- {key}：{value} 条")
        lines.extend(["", "### 维护类型分布", ""])
        for key, value in dataset_summary["maintenance_type_counts"].items():
            lines.append(f"- {key}：{value} 条")

    if final_issue_list is not None:
        lines.extend(_format_final_issue_list_by_operation_unit(final_issue_list, path))
        lines.extend(_format_pending_visual_reviews(audit, final_issue_list, path))
    else:
        lines.extend(["", "## 问题工单明细", ""])
        lines.append(f"- 问题工单数：{len(visible_records)} 条")
        lines.append(f"- 问题条目数：{len(visible_issues)} 条")
        lines.append("")

        issues_by_order: dict[str, list[dict[str, Any]]] = {}
        order_meta: dict[str, dict[str, Any]] = {}
        for issue in visible_issues:
            code = issue["working_order_code"]
            issues_by_order.setdefault(code, []).append(issue)
        for record in records:
            code = record.get("working_order_code")
            if code in visible_records:
                order_meta[code] = record

        for code in sorted(issues_by_order.keys()):
            record = order_meta.get(code, {})
            lines.append(
                f"### {code} | 站点 {record.get('station_id', '')} | "
                f"{record.get('order_type', '')}/{record.get('maintenance_type', '')}"
            )
            for issue in issues_by_order[code]:
                lines.append(f"- {issue['rule_id']}：{issue['message']}")
            lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_final_issue_list_by_operation_unit(
    final_issue_list: dict[str, Any], report_path: Path
) -> list[str]:
    items = [item for item in final_issue_list.get("items", []) if isinstance(item, dict)]
    affected_orders = {item.get("working_order_code") for item in items if item.get("working_order_code")}
    lines = ["", "## 问题工单明细", ""]
    lines.append(f"- 问题工单数：{len(affected_orders)} 条")
    lines.append(f"- 问题条目数：{len(items)} 条")
    linked_group_count = len(
        {
            item.get("issue_group_id")
            for item in items
            if item.get("issue_component") in LINKED_ABNORMAL_COMPONENTS and item.get("issue_group_id")
        }
    )
    if linked_group_count:
        lines.append(f"- 异常事实与说明关联组数：{linked_group_count} 组")
    lines.append("")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        operation_unit = _display_value(item.get("operation_unit"), "未关联运维单位")
        grouped.setdefault(operation_unit, []).append(item)

    for operation_unit in sorted(grouped):
        lines.append(f"### {operation_unit}")
        lines.append("")
        operation_items = grouped[operation_unit]
        linked_items = [
            item for item in operation_items if item.get("issue_component") in LINKED_ABNORMAL_COMPONENTS
        ]
        if linked_items:
            lines.extend(["#### 异常事实与说明对照", ""])
            lines.extend(_format_linked_abnormal_groups(linked_items, report_path))
        other_items = [
            item for item in operation_items if item.get("issue_component") not in LINKED_ABNORMAL_COMPONENTS
        ]
        lines.extend(_format_numbered_issue_items(other_items, report_path))
        lines.append("")
    return lines


def _format_linked_abnormal_groups(
    items: list[dict[str, Any]],
    report_path: Path,
) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        group_id = str(item.get("issue_group_id") or _fallback_issue_group_id(item))
        grouped.setdefault(group_id, []).append(item)

    groups = sorted(grouped.values(), key=_linked_group_sort_key)
    lines: list[str] = []
    for index, group in enumerate(groups, start=1):
        ordered = _sort_issue_items(group)
        representative = next(
            (item for item in ordered if item.get("issue_component") in ABNORMAL_FACT_COMPONENTS),
            ordered[0],
        )
        lines.append(
            f"{index}. {_issue_station_label(representative)}、"
            f"{_display_value(representative.get('rf_form_name'), '未关联中文表单')}、"
            f"{_display_value(representative.get('working_order_code'), '未关联工单号')}"
        )
        for fact in (item for item in ordered if item.get("issue_component") in ABNORMAL_FACT_COMPONENTS):
            label = ABNORMAL_FACT_LABELS.get(str(fact.get("issue_component")), "异常事实")
            lines.append(
                f"   - 异常事实（{label}）：{_issue_message(fact)}"
                f"（规则：{_display_value(fact.get('rule_id'), '未关联规则')}）"
            )
            lines.extend(_format_decision_evidence_lines(fact))
            lines.extend(_format_evidence_images(fact, report_path))
        explanations = [
            item for item in ordered if item.get("issue_component") in ABNORMAL_EXPLANATION_COMPONENTS
        ]
        if not explanations:
            fact_with_remarks = next((item for item in ordered if "remark_status" in item), None)
            if fact_with_remarks is not None:
                lines.extend(_format_original_remark_lines(fact_with_remarks))
                lines.append(f"   - 备注状态：{_remark_status_text(fact_with_remarks)}")
        for explanation in explanations:
            lines.extend(_format_original_remark_lines(explanation))
            judgment_label = _display_value(
                explanation.get("remark_judgment_label"),
                "说明缺失或无效",
            )
            lines.append(f"   - 备注状态：{_remark_status_text(explanation)}")
            lines.append(f"   - 说明判断：{judgment_label}")
            lines.append(f"   - 语义结论：{_issue_message(explanation)}")
            lines.extend(_format_evidence_images(explanation, report_path))
    return lines


def _linked_group_sort_key(group: list[dict[str, Any]]) -> tuple[str, str, str]:
    first = _sort_issue_items(group)[0]
    return (
        str(first.get("station_name") or first.get("station_id") or ""),
        str(first.get("working_order_code") or ""),
        str(first.get("field") or ""),
    )


def _fallback_issue_group_id(item: dict[str, Any]) -> str:
    return "::".join(
        str(item.get(key) or "")
        for key in ("working_order_code", "rf_table", "field", "rule_id")
    )


def _format_numbered_issue_items(
    items: list[dict[str, Any]],
    report_path: Path,
    *,
    component_label: str | None = None,
) -> list[str]:
    lines: list[str] = []
    prefix = f"[{component_label}] " if component_label else ""
    for index, item in enumerate(_sort_issue_items(items), start=1):
        lines.append(
            f"{index}. {prefix}{_issue_station_label(item)}、"
            f"{_display_value(item.get('rf_form_name'), '未关联中文表单')}、"
            f"{_display_value(item.get('working_order_code'), '未关联工单号')}、"
            f"{_issue_message(item)}、"
            f"{_display_value(item.get('rule_id'), '未关联规则')}"
        )
        if item.get("issue_component") in {"abnormal_explanation_issue", "abnormal_without_explanation"}:
            lines.extend(_format_original_remark_lines(item))
        lines.extend(_format_evidence_images(item, report_path))
    return lines


def _format_original_remark_lines(item: dict[str, Any]) -> list[str]:
    entries = item.get("original_remarks")
    if isinstance(entries, list):
        nonempty_entries = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("value") or "").strip()]
        if nonempty_entries:
            lines = []
            for entry in nonempty_entries:
                raw_field = _display_value(entry.get("field"), "备注")
                field_label = _display_value(entry.get("field_label"), raw_field)
                field = field_label if field_label == raw_field else f"{field_label}/{raw_field}"
                value = _single_line_text(entry.get("value"))
                lines.append(f"   - 原备注（{field}）：{value}")
            return lines

    fallback = str(item.get("original_remark_text") or "").strip()
    if fallback:
        return [f"   - 原备注：{_single_line_text(fallback)}"]
    return ["   - 原备注：未填写"]


def _format_decision_evidence_lines(item: dict[str, Any]) -> list[str]:
    evidence = item.get("decision_evidence")
    if not isinstance(evidence, dict):
        return []

    raw_value = _display_value(evidence.get("raw_value"), "未记录")
    parts = [f"原始值 {raw_value}"]
    if evidence.get("unit_conversion_applied"):
        normalized = _display_value(evidence.get("normalized_value"), "未记录")
        normalized_unit = str(evidence.get("normalized_unit") or "").strip()
        parts.append(f"换算值 {normalized}{f' {normalized_unit}' if normalized_unit else ''}")
    brand = str(evidence.get("brand") or "").strip()
    expected_range = _display_value(evidence.get("expected_range"), "未配置")
    parts.append(f"{f'{brand} 品牌' if brand else ''}正常范围 {expected_range}")
    return [f"   - 判定依据：{'；'.join(parts)}"]


def _remark_status_text(item: dict[str, Any]) -> str:
    status = _display_value(item.get("remark_status_label"), "未确认")
    review = str(item.get("remark_review_status_label") or "").strip()
    if not review or review == status or (status == "未填写" and review == "未填写备注"):
        return status
    return f"{status}；{review}"


def _single_line_text(value: Any) -> str:
    return " / ".join(part.strip() for part in str(value or "").splitlines() if part.strip()) or "未填写"


def _format_pending_visual_reviews(
    audit: dict[str, Any],
    final_issue_list: dict[str, Any],
    report_path: Path,
) -> list[str]:
    items = _collect_pending_visual_reviews(audit, final_issue_list)
    if not items:
        return []
    lines = ["", "## 视觉待人工复核", ""]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        operation_unit = _display_value(item.get("operation_unit"), "未关联运维单位")
        grouped.setdefault(operation_unit, []).append(item)
    for operation_unit in sorted(grouped):
        lines.extend([f"### {operation_unit}", ""])
        for index, item in enumerate(_sort_issue_items(grouped[operation_unit]), start=1):
            classification = _display_value(
                item.get("report_classification"), "视觉证据待人工复核"
            )
            lines.append(
                f"{index}. {_issue_station_label(item)}、"
                f"{_display_value(item.get('working_order_code'), '未关联工单号')}、"
                f"{classification}、"
                f"{_display_value(item.get('message'), '未填写复核说明')}、"
                f"{_display_value(item.get('rule_id'), '未关联规则')}"
            )
            lines.extend(_format_evidence_images(item, report_path))
        lines.append("")
    return lines


def _collect_pending_visual_reviews(
    audit: dict[str, Any], final_issue_list: dict[str, Any]
) -> list[dict[str, Any]]:
    final_keys = {
        _visual_issue_key(item)
        for item in final_issue_list.get("items", [])
        if isinstance(item, dict)
    }
    pending = []
    for record in audit.get("records", []):
        for issue in record.get("scoring_issues", []):
            if not isinstance(issue, dict):
                continue
            evidence = _parse_evidence(issue.get("evidence"))
            images = evidence.get("evidence_images")
            if not isinstance(images, list) or not images:
                continue
            rule_id = str(issue.get("rule_id") or "")
            if not (
                evidence.get("needs_visual_review") is True
                or evidence.get("needs_manual_review") is True
                or rule_id == "ATTACHMENT_FLOW_VISUAL_ERROR"
            ):
                continue
            item = {
                "working_order_code": record.get("working_order_code"),
                "station_id": record.get("station_id"),
                "station_name": record.get("station_name"),
                "operation_unit": record.get("operation_unit"),
                "rule_id": rule_id,
                "field": issue.get("field"),
                "message": issue.get("message"),
                "report_classification": evidence.get("report_classification"),
                "evidence_images": images,
            }
            if _visual_issue_key(item) not in final_keys:
                pending.append(item)
    return pending


def _visual_issue_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("working_order_code") or ""),
        str(item.get("rule_id") or ""),
        str(item.get("field") or ""),
        str(item.get("message") or ""),
    )


def _format_evidence_images(
    item: dict[str, Any], report_path: Path, limit: int = 3
) -> list[str]:
    images = _evidence_images(item)
    successful: list[tuple[dict[str, Any], Path]] = []
    path_errors = []
    report_root = report_path.parent.resolve()
    for image in images:
        if image.get("status") != "success" or not image.get("local_path"):
            continue
        local_path = Path(str(image["local_path"])).resolve()
        if not local_path.is_file():
            path_errors.append(f"本地证据不存在: {local_path}")
            continue
        try:
            local_path.relative_to(report_root)
        except ValueError:
            path_errors.append(f"证据图片不在报告目录内: {local_path}")
            continue
        successful.append((image, local_path))

    lines = []
    for image, local_path in successful[:limit]:
        relative = local_path.relative_to(report_root).as_posix()
        filename = str(image.get("filename") or local_path.name)
        lines.extend(["", f"![视觉证据：{filename}]({relative})"])
    if len(successful) > limit:
        lines.extend(
            ["", f"> 报告展示 {limit} 张，证据包共保存 {len(successful)} 张。"]
        )
    if not successful:
        failed = [image for image in images if image.get("status") == "failed"]
        if failed:
            error = str(failed[0].get("error") or "未知原因")
            lines.extend(["", f"> 证据图片获取失败：{error}"])
        elif path_errors:
            lines.extend(["", f"> 证据图片获取失败：{path_errors[0]}"])
    return lines


def _evidence_images(item: dict[str, Any]) -> list[dict[str, Any]]:
    images = item.get("evidence_images")
    if not isinstance(images, list):
        images = _parse_evidence(item.get("evidence")).get("evidence_images")
    if not isinstance(images, list):
        return []
    return [image for image in images if isinstance(image, dict)]


def _sort_issue_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            str(item.get("station_name") or item.get("station_id") or ""),
            str(item.get("working_order_code") or ""),
            str(item.get("rf_form_name") or ""),
            str(item.get("rule_id") or ""),
            str(item.get("message") or ""),
        ),
    )


def _issue_station_label(item: dict[str, Any]) -> str:
    station_name = str(item.get("station_name") or "").strip()
    if station_name:
        return station_name
    station_id = str(item.get("station_id") or "").strip()
    if station_id:
        return f"站点{station_id}"
    return "未关联站点"


def _issue_message(item: dict[str, Any]) -> str:
    message = _display_value(item.get("message"), "未填写问题描述")
    detail = _issue_evidence_detail(item)
    return f"{message}（{detail}）" if detail else message


def _issue_evidence_detail(item: dict[str, Any]) -> str:
    if item.get("rule_id") != "RF_DEVICE_IDENTITY_INCONSISTENT":
        return ""
    evidence = _parse_evidence(item.get("evidence"))
    comparisons = evidence.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        return ""
    details = []
    for comparison in comparisons[:3]:
        if not isinstance(comparison, dict):
            continue
        compare_order = _display_value(comparison.get("compare_order_code"), "未关联对比工单")
        compare_time = str(comparison.get("compare_create_time") or "").strip()
        compare_label = f"对比工单{compare_order}"
        if compare_time:
            compare_label = f"{compare_label}（{compare_time}）"
        current_raw = _display_value(comparison.get("current_raw") or evidence.get("current_value"), "空")
        compare_raw = _display_value(comparison.get("compare_raw"), "空")
        source_detail = _source_detail(comparison)
        details.append(f"{compare_label}：当前值{current_raw}，历史值{compare_raw}{source_detail}")
    return "；".join(details)


def _source_detail(comparison: dict[str, Any]) -> str:
    current_source = str(comparison.get("current_source") or "").strip()
    compare_source = str(comparison.get("compare_source") or "").strip()
    if current_source or compare_source:
        return f"，字段{current_source or '-'}/{compare_source or '-'}"
    return ""


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


def _display_value(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback
