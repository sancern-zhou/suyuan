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
MAX_STRUCTURED_EVIDENCE_ITEMS = 5


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
            lines.extend(_format_structured_evidence_lines(fact))
            lines.extend(_format_evidence_images(fact, report_path))
        explanations = [
            item for item in ordered if item.get("issue_component") in ABNORMAL_EXPLANATION_COMPONENTS
        ]
        if not explanations:
            fact_with_remarks = next((item for item in ordered if _has_remark_context(item)), None)
            if fact_with_remarks is not None:
                lines.extend(_format_remark_context_lines(fact_with_remarks))
        for explanation in explanations:
            lines.extend(_format_remark_context_lines(explanation))
            judgment_label = _display_value(
                explanation.get("remark_judgment_label"),
                "说明缺失或无效",
            )
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
        lines.extend(_format_structured_evidence_lines(item))
        lines.extend(_format_remark_context_lines(item))
        lines.extend(_format_evidence_images(item, report_path))
    return lines


def _format_remark_context_lines(item: dict[str, Any]) -> list[str]:
    if not _has_remark_context(item):
        return []
    return [
        *_format_original_remark_lines(item),
        f"   - 备注状态：{_remark_status_text(item)}",
    ]


def _has_remark_context(item: dict[str, Any]) -> bool:
    return any(
        key in item
        for key in (
            "original_remarks",
            "original_remark_text",
            "remark_status",
            "remark_status_label",
            "remark_review_status",
            "remark_review_status_label",
            "remark_judgment",
            "remark_judgment_label",
        )
    )


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


def _format_structured_evidence_lines(item: dict[str, Any]) -> list[str]:
    if item.get("rule_id") == "RF_DEVICE_IDENTITY_INCONSISTENT":
        return []
    evidence = _parse_evidence(item.get("evidence"))
    if not evidence:
        return []

    lines: list[str] = []
    lines.extend(_format_attachment_requirement_lines(evidence))
    lines.extend(_format_attachment_comparison_lines(evidence))
    if not item.get("decision_evidence"):
        lines.extend(_format_flat_field_evidence_lines(evidence))
    lines.extend(_format_violation_evidence_lines(evidence))
    return _unique_lines(lines)


def _format_attachment_requirement_lines(evidence: dict[str, Any]) -> list[str]:
    if not any(key in evidence for key in ("requirement_name", "missing_type", "missing_types", "required_types")):
        return []
    parts = [
        f"要求 {_display_value(evidence.get('requirement_name') or evidence.get('requirement_id'), '未命名附件要求')}",
    ]
    if "required_types" in evidence:
        parts.append(f"应有 {_format_sequence(evidence.get('required_types'), '未记录')}")
    missing = evidence.get("missing_types")
    if missing is None and "missing_type" in evidence:
        missing = [evidence.get("missing_type")]
    if missing is not None:
        parts.append(f"缺失 {_format_sequence(missing, '未记录')}")
    if "attachment_count" in evidence:
        parts.append(f"当前附件 {evidence.get('attachment_count')} 个")
    type_counts = evidence.get("type_counts")
    if isinstance(type_counts, dict):
        parts.append(f"类型分布 {_format_mapping(type_counts, '无')}")
    samples = _attachment_sample_names(evidence.get("sample_attachments"))
    if samples:
        parts.append(f"附件样例 {samples}")
    return [f"   - 附件核查：{'；'.join(parts)}"]


def _format_attachment_comparison_lines(evidence: dict[str, Any]) -> list[str]:
    comparisons = evidence.get("comparisons")
    if isinstance(comparisons, list):
        comparison_items = [item for item in comparisons if isinstance(item, dict)]
    elif isinstance(evidence.get("comparison"), dict):
        comparison_items = [evidence["comparison"]]
    else:
        return []
    if not comparison_items:
        return []

    attachment = evidence.get("attachment")
    filename = (
        str(attachment.get("filename") or "").strip()
        if isinstance(attachment, dict)
        else ""
    )
    lines: list[str] = []
    multiple = len(comparison_items) > 1
    for index, comparison in enumerate(comparison_items[:MAX_STRUCTURED_EVIDENCE_ITEMS], start=1):
        parts = []
        if filename:
            parts.append(f"附件 {filename}")
        parts.append(f"字段 {_field_display_text(comparison.get('label'), comparison.get('field'))}")
        cell = comparison.get("cell") or comparison.get("configured_cell")
        if cell:
            parts.append(f"XLS单元格 {cell}")
        parts.append(f"表单值 {_display_value(comparison.get('form_value'), '空')}")
        parts.append(f"附件值 {_display_value(comparison.get('xls_value'), '空')}")
        label = f"附件比对{index}" if multiple else "附件比对"
        lines.append(f"   - {label}：{'；'.join(parts)}")
    lines.extend(_overflow_line("附件比对", len(comparison_items)))
    return lines


def _format_flat_field_evidence_lines(evidence: dict[str, Any]) -> list[str]:
    if "violations" in evidence or "violation" in evidence:
        return []
    interesting_keys = {
        "raw_value",
        "value",
        "expected",
        "expected_min",
        "expected_max",
        "allowed_min",
        "allowed_max",
        "device_model",
        "instrument_type",
        "problem_reason",
        "temperature_value",
        "temperature_status",
        "missing",
        "abnormal_status",
        "out_of_range",
    }
    if "field" not in evidence or not any(key in evidence for key in interesting_keys):
        return []
    parts = [f"字段 {_field_display_text(evidence.get('field_label') or evidence.get('label'), evidence.get('field'))}"]
    if "raw_value" in evidence:
        parts.append(f"原始值 {_display_value(evidence.get('raw_value'), '空')}")
    if "value" in evidence and evidence.get("value") != evidence.get("raw_value"):
        parts.append(f"解析值 {_display_value(evidence.get('value'), '空')}")
    if "expected" in evidence:
        parts.append(f"要求 {_single_line_text(evidence.get('expected'))}")
    range_text = _expected_range_text(evidence)
    if range_text:
        parts.append(f"期望范围 {range_text}")
    if "temperature_value" in evidence:
        parts.append(f"温度值 {_display_value(evidence.get('temperature_value'), '空')}")
    if "temperature_status" in evidence:
        parts.append(f"温度状态 {_display_value(evidence.get('temperature_status'), '空')}")
    if "missing" in evidence:
        parts.append(f"是否缺失 {_bool_text(evidence.get('missing'))}")
    if "abnormal_status" in evidence:
        parts.append(f"状态是否异常 {_bool_text(evidence.get('abnormal_status'))}")
    if "out_of_range" in evidence:
        parts.append(f"是否超范围 {_bool_text(evidence.get('out_of_range'))}")
    if "device_model" in evidence:
        parts.append(f"设备型号 {_display_value(evidence.get('device_model'), '未记录')}")
    if "instrument_type" in evidence:
        parts.append(f"仪器类型 {_display_value(evidence.get('instrument_type'), '未记录')}")
    if "problem_reason" in evidence:
        parts.append(f"原因 {_single_line_text(evidence.get('problem_reason'))}")
    return [f"   - 字段核查：{'；'.join(parts)}"]


def _format_violation_evidence_lines(evidence: dict[str, Any]) -> list[str]:
    violations = evidence.get("violations")
    if isinstance(violations, list):
        violation_items = [item for item in violations if isinstance(item, dict)]
    elif isinstance(evidence.get("violation"), dict):
        violation_items = [evidence["violation"]]
    else:
        return []
    if not violation_items:
        return []

    lines: list[str] = []
    multiple = len(violation_items) > 1
    for index, violation in enumerate(violation_items[:MAX_STRUCTURED_EVIDENCE_ITEMS], start=1):
        detail = _violation_detail_text(violation)
        if detail:
            label = f"核查明细{index}" if multiple else "核查明细"
            lines.append(f"   - {label}：{detail}")
    lines.extend(_overflow_line("核查明细", len(violation_items)))
    return lines


def _violation_detail_text(violation: dict[str, Any]) -> str:
    parts: list[str] = []
    description = str(violation.get("description") or "").strip()
    if description:
        parts.append(_single_line_text(description))
    else:
        context = []
        for key, label in (
            ("label", "项目"),
            ("gas_type", "气体"),
            ("point", "点位"),
            ("field", "字段"),
            ("display_field", "标示字段"),
            ("measured_field", "测量字段"),
            ("error_field", "误差字段"),
            ("actual_field", "字段"),
            ("prev_field", "上次校准字段"),
            ("next_field", "有效期字段"),
            ("formula_id", "公式"),
        ):
            if _has_value(violation.get(key)):
                context.append(f"{label}{_single_line_text(violation.get(key))}")
        if context:
            parts.append("，".join(context))

    for key, label in (
        ("value", "填写值"),
        ("actual", "实填值"),
        ("expected", "复算值"),
        ("expected_target", "目标值"),
        ("delta", "差值"),
        ("tolerance", "容差"),
        ("allowed_tolerance", "允许偏差"),
        ("display_value", "标示值"),
        ("measured_value", "测量值"),
        ("expected_error", "复算误差"),
    ):
        if _has_value(violation.get(key)):
            parts.append(f"{label}{_single_line_text(violation.get(key))}")

    range_text = _expected_range_text(violation)
    if range_text:
        parts.append(f"允许范围 {range_text}")
    if _has_value(violation.get("model_field")) or _has_value(violation.get("model_value")):
        parts.append(
            f"设备型号字段 {_display_value(violation.get('model_field'), '-')}"
            f"={_display_value(violation.get('model_value'), '空')}"
        )
    if _has_value(violation.get("situation_field")) or _has_value(violation.get("situation_value")):
        parts.append(
            f"运行情况字段 {_display_value(violation.get('situation_field'), '-')}"
            f"={_display_value(violation.get('situation_value'), '空')}"
        )
    related_values = violation.get("related_values")
    if isinstance(related_values, dict) and related_values:
        parts.append(f"关联字段 {_format_mapping(related_values, '无')}")
    inputs = violation.get("inputs")
    if isinstance(inputs, dict) and inputs:
        parts.append(f"输入 {_format_mapping(inputs, '无')}")
    if _has_value(violation.get("reason")):
        parts.append(f"原因 {_single_line_text(violation.get('reason'))}")
    return "；".join(parts)


def _field_display_text(label: Any, field: Any) -> str:
    label_text = str(label or "").strip()
    field_text = str(field or "").strip()
    if label_text and field_text and label_text != field_text:
        return f"{label_text}/{field_text}"
    return _display_value(label_text or field_text, "未关联字段")


def _expected_range_text(source: dict[str, Any]) -> str:
    minimum = source.get("expected_min", source.get("allowed_min"))
    maximum = source.get("expected_max", source.get("allowed_max"))
    if not (_has_value(minimum) or _has_value(maximum)):
        return ""
    unit = str(source.get("unit") or "").strip()
    if _has_value(minimum) and _has_value(maximum):
        text = f"{minimum}-{maximum}"
    elif _has_value(minimum):
        text = f">={minimum}"
    else:
        text = f"<={maximum}"
    return f"{text}{unit}".strip()


def _format_sequence(value: Any, fallback: str) -> str:
    if isinstance(value, (list, tuple, set)):
        parts = [_single_line_text(item) for item in value if _has_value(item)]
        return "、".join(parts) if parts else fallback
    if _has_value(value):
        return _single_line_text(value)
    return fallback


def _format_mapping(value: dict[str, Any], fallback: str) -> str:
    parts = [
        f"{key}={_display_value(raw_value, '空')}"
        for key, raw_value in value.items()
        if _has_value(key)
    ]
    return "，".join(parts) if parts else fallback


def _bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return _display_value(value, "未记录")


def _attachment_sample_names(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names = []
    for item in value[:3]:
        if isinstance(item, dict):
            name = item.get("filename") or item.get("FILENAME") or item.get("name")
        else:
            name = item
        if _has_value(name):
            names.append(_single_line_text(name))
    return "、".join(names)


def _overflow_line(label: str, total_count: int) -> list[str]:
    overflow = total_count - MAX_STRUCTURED_EVIDENCE_ITEMS
    if overflow <= 0:
        return []
    return [f"   - {label}：另有 {overflow} 条明细未展开，详见最终问题清单。"]


def _unique_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


def _remark_status_text(item: dict[str, Any]) -> str:
    status = _display_value(item.get("remark_status_label"), "未确认")
    review = str(item.get("remark_review_status_label") or "").strip()
    if not review or review == status or (status == "未填写" and review == "未填写备注"):
        return status
    return f"{status}；{review}"


def _single_line_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return " / ".join(part.strip() for part in text.splitlines() if part.strip()) or "未填写"


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
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""
