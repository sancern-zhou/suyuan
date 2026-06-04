"""Markdown report writer for deterministic ops audits."""

from __future__ import annotations

import json
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXCLUDED_REPORT_RULE_IDS = {
    "RF_AUDITOR_EMPTY",
    "RF_REVIEW_EMPTY",
    "RF_REQUIRED_FIELD_LOW_VALUE",
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
    summary = audit["summary"]
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
        lines.extend(_format_final_issue_list_by_operation_unit(final_issue_list))
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


def _format_final_issue_list_by_operation_unit(final_issue_list: dict[str, Any]) -> list[str]:
    items = [item for item in final_issue_list.get("items", []) if isinstance(item, dict)]
    affected_orders = {item.get("working_order_code") for item in items if item.get("working_order_code")}
    lines = ["", "## 问题工单明细", ""]
    lines.append(f"- 问题工单数：{len(affected_orders)} 条")
    lines.append(f"- 问题条目数：{len(items)} 条")
    lines.append("")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        operation_unit = _display_value(item.get("operation_unit"), "未关联运维单位")
        grouped.setdefault(operation_unit, []).append(item)

    for operation_unit in sorted(grouped):
        lines.append(f"### {operation_unit}")
        lines.append("")
        for index, item in enumerate(_sort_issue_items(grouped[operation_unit]), start=1):
            lines.append(
                f"{index}. {_issue_station_label(item)}、"
                f"{_display_value(item.get('rf_form_name'), '未关联中文表单')}、"
                f"{_display_value(item.get('working_order_code'), '未关联工单号')}、"
                f"{_issue_message(item)}、"
                f"{_display_value(item.get('rule_id'), '未关联规则')}"
            )
        lines.append("")
    return lines


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
