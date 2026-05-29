"""Markdown report writer for deterministic ops audits."""

from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXCLUDED_REPORT_RULE_IDS = {
    "RF_AUDITOR_EMPTY",
    "RF_CREATEDATE_EMPTY",
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
                    "audit_level": record.get("audit_level", ""),
                    "rule_id": issue.get("rule_id", ""),
                    "severity": issue.get("severity", ""),
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


def write_report(audit: dict[str, Any], path: Path, dataset: dict[str, Any] | None = None) -> None:
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
        "## 总体分布",
        "",
    ]
    for key, value in summary["audit_level_counts"].items():
        lines.append(f"- {key}：{value}")

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
            lines.append(f"- {issue['rule_id']}（{issue['severity']}）：{issue['message']}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
