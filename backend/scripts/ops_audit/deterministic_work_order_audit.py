#!/usr/bin/env python3
"""Fetch and audit recent finished operations work orders.

The script intentionally keeps the first pass deterministic: it only checks
field completeness, status/time consistency, workflow coverage, and obvious RF
form quality issues. Semantic judgement can consume the produced JSON later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyodbc


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config.settings import Settings  # noqa: E402


OUTPUT_DIR = BACKEND / "backend_data_registry" / "memory" / "ops" / "audit"

RF_TABLES = [
    "RF_W_GASEOUSCHECK_CO",
    "RF_W_GASEOUSCHECK_NOX",
    "RF_W_GASEOUSCHECK_O3",
    "RF_W_GASEOUSCHECK_SO2",
    "RF_W_INSPECTIONSUMMARY",
    "RF_W_OTHERDEVICECHECK",
    "RF_TW_CleanCuttingHead",
    "RF_TW_PmFlowCalibrate",
    "RF_TW_PmFlowCheck",
    "RF_M_GASEOUSCALICHECK",
    "RF_M_GASEOUSCALIDEVICECHECK",
    "RF_M_GASEOUSFLOWCHECK",
    "RF_M_MANUALCOMPARISON",
    "RF_M_MANUALCOMPARISONDETAIL",
    "RF_M_MEMBRANEWEIGHING",
    "RF_M_PMDEVICEMAINTAIN",
    "RF_M_STATIONDEVICEMAINTAIN",
    "RF_M_StationMaintainCheck",
    "RF_Q_GASEOUSMULTIPOINT_CO",
    "RF_Q_GASEOUSMULTIPOINT_NO2",
    "RF_Q_GASEOUSMULTIPOINT_O3",
    "RF_Q_GASEOUSMULTIPOINT_SO2",
    "RF_Q_GASEOUSPRECISION_CO",
    "RF_Q_GASEOUSPRECISION_NO2",
    "RF_Q_GASEOUSPRECISION_O3",
    "RF_Q_GASEOUSPRECISION_SO2",
    "RF_Q_GaseousFlowCheck",
    "RF_Q_LONGOPTICALPATH_NO2",
    "RF_Q_LONGOPTICALPATH_O3",
    "RF_Q_LONGOPTICALPATH_SO2",
    "RF_Q_PM10RUNSTATUSCHECK",
    "RF_Q_PM25RUNSTATUSCHECK",
    "RF_Q_PMPRESSURE",
    "RF_Q_STATIONDEVICECLEAN",
    "RF_Q_StationMaintainCheck",
    "RF_SEC_INSPECTION",
    "RF_SEC_INSTRUMENTRECORD",
    "RF_SEC_MONITORINGCHECK",
]

LOW_VALUE_REMARKS = {
    "正常",
    "已完成",
    "完成",
    "无",
    "任务检查单",
    "计划任务单",
    "创建工单",
    "清洗",
    "检查",
    "合格",
}


@dataclass
class Issue:
    rule_id: str
    category: str
    severity: str
    field: str
    message: str
    evidence: str
    suggestion: str


def connect() -> pyodbc.Connection:
    settings = Settings()
    conn_str = re.sub(
        r"DATABASE=\w+",
        "DATABASE=AirPollutionAnalysis",
        settings.sqlserver_connection_string,
        flags=re.IGNORECASE,
    )
    return pyodbc.connect(conn_str, timeout=30)


def rows(cursor: pyodbc.Cursor, sql: str) -> list[dict[str, Any]]:
    cursor.execute(sql)
    columns = [column[0] for column in cursor.description]
    result = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        for key, value in list(record.items()):
            if isinstance(value, datetime):
                record[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, Decimal):
                record[key] = float(value)
            elif isinstance(value, bytes):
                record[key] = value.hex()
        result.append(record)
    return result


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def fetch_dataset(limit: int) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.cursor()
        orders = rows(
            cursor,
            f"""
            SELECT TOP {limit}
                WORKINGORDERID, STATIONID, DEVICEID, WORKINGORDERCODE,
                CREATETIME, UPDATETIME, DDORDERCREATETYPE, DDWORKINGORDERTYPE,
                DDURGENCYTYPE, DDWORKINGORDERSTATUS, DDISSUEDTYPE, ORDERTITLE,
                ORDERCONTENT, CURRENTWORKFLOWSTATUS, CURRENTWORKFLOWPOINT,
                FINISHTIME, PLANFINISHTIME, MAINTENANCETYPE, TOTALOVERTIME,
                TOTALEXPENSE
            FROM dbo.working_orders
            WHERE DDWORKINGORDERSTATUS = N'Finish'
            ORDER BY FINISHTIME DESC, CREATETIME DESC
            """,
        )
        codes = [row["WORKINGORDERCODE"] for row in orders if row.get("WORKINGORDERCODE")]
        if not codes:
            return {"orders": [], "details": [], "attachments": [], "rf_forms": {}}

        in_codes = ", ".join(quote(code) for code in codes)
        details = rows(
            cursor,
            f"""
            SELECT
                WORKINGORDERCODE, PROCESSSTEP, PROCESSSTARTDATETIME,
                PROCESSENDDATETIME, PROCESSUSERID, PROCESSSTATUS,
                SUBMITREMARK, DESCRIPTIONTA, EXPENSE, PROCESSTIME
            FROM dbo.working_order_details
            WHERE WORKINGORDERCODE IN ({in_codes})
            ORDER BY WORKINGORDERCODE, PROCESSSTARTDATETIME, PROCESSSTEP
            """,
        )
        attachments = rows(
            cursor,
            f"""
            SELECT TOP 2000 *
            FROM dbo.wo_commonfile_links
            WHERE refid IN ({in_codes}) OR remark IN ({in_codes})
            ORDER BY createdate DESC
            """,
        )

        rf_forms: dict[str, list[dict[str, Any]]] = {}
        for table in RF_TABLES:
            try:
                rf_forms[table] = rows(
                    cursor,
                    f"""
                    SELECT TOP 2000 *
                    FROM dbo.{table}
                    WHERE WORKINGORDERCODE IN ({in_codes})
                    """,
                )
            except Exception as exc:  # keep extraction useful if one table drifts
                rf_forms[table] = [{"_query_error": str(exc)}]
                conn.rollback()

    return {
        "query_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": "AirPollutionAnalysis",
            "order_filter": "DDWORKINGORDERSTATUS = 'Finish'",
            "order_by": "FINISHTIME DESC, CREATETIME DESC",
            "limit": limit,
        },
        "orders": orders,
        "details": details,
        "attachments": attachments,
        "rf_forms": rf_forms,
    }


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def add_issue(
    issues: list[Issue],
    rule_id: str,
    category: str,
    severity: str,
    field: str,
    message: str,
    evidence: str,
    suggestion: str,
) -> None:
    issues.append(Issue(rule_id, category, severity, field, message, evidence, suggestion))


def check_workflow(order: dict[str, Any], details: list[dict[str, Any]], issues: list[Issue]) -> None:
    if not details:
        add_issue(issues, "FLOW_MISSING", "流程完整性", "高", "working_order_details", "完工工单无流程详情", "", "按工单编号补查或修复流程记录关联")
        return

    steps = [detail.get("PROCESSSTEP") for detail in details]
    if "CreateOrder" not in steps:
        add_issue(issues, "FLOW_NO_CREATE", "流程完整性", "高", "PROCESSSTEP", "缺少创建步骤", ",".join(map(str, steps)), "补齐 CreateOrder 流程记录")

    if order.get("DDWORKINGORDERTYPE") in {"Check", "SupCheck", "Fault"} and not ({"CheckOrder", "SupCheck_Check"} & set(steps)):
        add_issue(issues, "FLOW_NO_CHECK", "流程完整性", "高", "PROCESSSTEP", "缺少检查/巡检处理步骤", ",".join(map(str, steps)), "补齐检查处理环节")

    if order.get("DDWORKINGORDERTYPE") in {"Check", "SupCheck"} and "Review" not in steps:
        add_issue(issues, "FLOW_NO_REVIEW", "流程完整性", "中", "PROCESSSTEP", "检查/巡检工单缺少复核步骤", ",".join(map(str, steps)), "按业务流程补齐复核")

    previous_start = None
    for detail in details:
        step = detail.get("PROCESSSTEP") or ""
        start = parse_time(detail.get("PROCESSSTARTDATETIME"))
        end = parse_time(detail.get("PROCESSENDDATETIME"))
        if detail.get("PROCESSSTATUS") in {"1.00", 1, 1.0} and step != "CreateOrder" and end is None:
            add_issue(issues, "FLOW_END_EMPTY", "流程完整性", "中", "PROCESSENDDATETIME", "已完成流程步骤结束时间为空", step, "补齐流程结束时间")
        if start and end and end < start:
            add_issue(issues, "FLOW_TIME_ORDER", "时间合理性", "高", "PROCESSENDDATETIME", "流程结束时间早于开始时间", f"{step}: {end} < {start}", "修正流程节点时间")
        if previous_start and start and start < previous_start:
            add_issue(issues, "FLOW_SEQUENCE", "时间合理性", "中", "PROCESSSTARTDATETIME", "流程开始时间顺序倒置", f"{step}: {start}", "核对流程节点顺序")
        if start:
            previous_start = start

        remark = detail.get("SUBMITREMARK")
        if step != "CreateOrder" and (is_blank(remark) or str(remark).strip() in LOW_VALUE_REMARKS):
            add_issue(issues, "FLOW_REMARK_LOW_VALUE", "填报规范性", "中", "SUBMITREMARK", "处理备注为空或信息量低", str(remark), "补充原因、措施、结果")


def check_rf_forms(order: dict[str, Any], forms: list[tuple[str, dict[str, Any]]], issues: list[Issue]) -> None:
    for table, form in forms:
        if form.get("_query_error"):
            continue
        prefix = table
        station = form.get("STATIONID")
        if station and str(station) != str(order.get("STATIONID")):
            add_issue(issues, "RF_STATION_MISMATCH", "一致性", "高", f"{prefix}.STATIONID", "RF 表单站点与工单站点不一致", f"form={station}, order={order.get('STATIONID')}", "核对表单和工单关联")

        if "PREPARERUSERID" in form and is_blank(form.get("PREPARERUSERID")):
            add_issue(issues, "RF_PREPARER_EMPTY", "表单完整性", "中", f"{prefix}.PREPARERUSERID", "表单编制人为空", "", "补齐编制人")
        if "REVIEWUSERID" in form and is_blank(form.get("REVIEWUSERID")):
            add_issue(issues, "RF_REVIEW_EMPTY", "表单完整性", "中", f"{prefix}.REVIEWUSERID", "表单复核人为空", "", "补齐复核人或说明免复核原因")
        if "AUDITORUSERID" in form and is_blank(form.get("AUDITORUSERID")):
            add_issue(issues, "RF_AUDITOR_EMPTY", "表单完整性", "低", f"{prefix}.AUDITORUSERID", "表单审批人为空", "", "补齐审批人或说明免审批原因")
        if "CREATEDATE" in form and is_blank(form.get("CREATEDATE")):
            add_issue(issues, "RF_CREATEDATE_EMPTY", "表单完整性", "中", f"{prefix}.CREATEDATE", "表单创建日期为空", "", "补齐表单创建日期")

        if table == "RF_TW_CleanCuttingHead":
            if form.get("PollutantType") and form.get("PM_DeviceType") and str(form["PollutantType"]).upper() != str(form["PM_DeviceType"]).upper():
                add_issue(issues, "RF_TW_POLLUTANT_MISMATCH", "一致性", "高", "PollutantType/PM_DeviceType", "污染物类型与设备类型不一致", f"{form['PollutantType']} vs {form['PM_DeviceType']}", "核对切割头清洗对象")
            remark = form.get("CleaningRemark")
            if is_blank(remark) or str(remark).strip() in LOW_VALUE_REMARKS:
                add_issue(issues, "RF_TW_REMARK_LOW_VALUE", "填报规范性", "中", "CleaningRemark", "清洗备注为空或信息量低", str(remark), "说明清洗对象、动作和结果")

        if table.startswith("RF_Q_GASEOUSMULTIPOINT"):
            for field in ["XL", "JU", "XGXS"]:
                if field in form and is_blank(form.get(field)):
                    add_issue(issues, "RF_Q_MULTIPOINT_METRIC_EMPTY", "表单完整性", "高", field, "多点校准关键指标为空", "", "补齐斜率、截距、相关系数")
            if str(form.get("XZJG")) in {"0", "0.0"} and is_blank(form.get("REMARKS")):
                add_issue(issues, "RF_Q_PENDING_NO_REMARK", "结果合理性", "高", "XZJG/REMARKS", "校准结果待定/不合格但无说明", f"XZJG={form.get('XZJG')}", "说明异常原因、处置措施和复测安排")


def severity_score(issues: list[Issue]) -> int:
    score = 100
    for issue in issues:
        if issue.severity == "高":
            score -= 18
        elif issue.severity == "中":
            score -= 8
        else:
            score -= 3
    return max(score, 0)


def risk_level(score: int, issues: list[Issue]) -> str:
    if any(issue.severity == "高" for issue in issues) and score < 70:
        return "高风险"
    if score >= 85:
        return "通过"
    if score >= 70:
        return "轻微问题"
    if score >= 50:
        return "需补正"
    return "高风险"


def audit_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    details_by_code = defaultdict(list)
    for detail in dataset.get("details", []):
        details_by_code[detail.get("WORKINGORDERCODE")].append(detail)

    forms_by_code = defaultdict(list)
    for table, forms in dataset.get("rf_forms", {}).items():
        for form in forms:
            code = form.get("WORKINGORDERCODE")
            if code:
                forms_by_code[code].append((table, form))

    records = []
    for order in dataset.get("orders", []):
        code = order.get("WORKINGORDERCODE")
        issues: list[Issue] = []
        check_workflow(order, details_by_code.get(code, []), issues)
        check_rf_forms(order, forms_by_code.get(code, []), issues)
        score = severity_score(issues)
        records.append(
            {
                "working_order_code": code,
                "station_id": order.get("STATIONID"),
                "order_type": order.get("DDWORKINGORDERTYPE"),
                "create_type": order.get("DDORDERCREATETYPE"),
                "maintenance_type": order.get("MAINTENANCETYPE"),
                "finish_time": order.get("FINISHTIME"),
                "score": score,
                "audit_level": risk_level(score, issues),
                "issue_count": len(issues),
                "issues": [asdict(issue) for issue in issues],
                "workflow_steps": [d.get("PROCESSSTEP") for d in details_by_code.get(code, [])],
                "rf_tables": sorted({table for table, _ in forms_by_code.get(code, [])}),
            }
        )

    issue_counter = Counter()
    severity_counter = Counter()
    category_counter = Counter()
    level_counter = Counter(record["audit_level"] for record in records)
    for record in records:
        for issue in record["issues"]:
            issue_counter[issue["rule_id"]] += 1
            severity_counter[issue["severity"]] += 1
            category_counter[issue["category"]] += 1

    return {
        "audit_info": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "order_count": len(records),
            "rule_stage": "deterministic",
        },
        "summary": {
            "audit_level_counts": dict(level_counter),
            "severity_counts": dict(severity_counter),
            "category_counts": dict(category_counter),
            "top_rules": issue_counter.most_common(20),
        },
        "records": records,
    }


def write_report(audit: dict[str, Any], path: Path) -> None:
    summary = audit["summary"]
    records = audit["records"]
    high_risk = [record for record in records if record["audit_level"] == "高风险"]
    need_fix = [record for record in records if record["audit_level"] == "需补正"]

    lines = [
        "# 最近已完成工单确定性规则审核报告",
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
    lines.extend(["", "## 问题类别分布", ""])
    for key, value in summary["category_counts"].items():
        lines.append(f"- {key}：{value}")
    lines.extend(["", "## 高频规则", ""])
    for rule_id, count in summary["top_rules"][:10]:
        lines.append(f"- {rule_id}：{count}")

    lines.extend(["", "## 高风险/需补正工单", ""])
    for record in high_risk + need_fix:
        first_issue = record["issues"][0]["message"] if record["issues"] else ""
        lines.append(
            f"- {record['working_order_code']} | 站点 {record['station_id']} | "
            f"{record['order_type']}/{record['maintenance_type']} | "
            f"{record['audit_level']} | {record['score']}分 | {first_issue}"
        )

    lines.extend(["", "## 后续语义审核输入建议", ""])
    lines.append("- 对存在 `FLOW_REMARK_LOW_VALUE`、报警/故障处置闭环不足的工单，进入大模型语义审核。")
    lines.append("- 语义审核重点判断备注是否覆盖原因、措施、结果，报警是否说明数据有效性和恢复情况。")
    lines.append("- 大模型只消费确定性规则筛出的异常工单，降低成本并减少误判面。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_semantic_candidates(audit: dict[str, Any]) -> dict[str, Any]:
    semantic_rule_ids = {
        "FLOW_REMARK_LOW_VALUE",
        "RF_TW_REMARK_LOW_VALUE",
        "RF_Q_PENDING_NO_REMARK",
    }
    candidates = []
    for record in audit["records"]:
        matched_issues = [
            issue
            for issue in record["issues"]
            if issue["rule_id"] in semantic_rule_ids or issue["severity"] == "高"
        ]
        if not matched_issues:
            continue
        candidates.append(
            {
                "working_order_code": record["working_order_code"],
                "station_id": record["station_id"],
                "order_type": record["order_type"],
                "maintenance_type": record["maintenance_type"],
                "finish_time": record["finish_time"],
                "deterministic_score": record["score"],
                "deterministic_level": record["audit_level"],
                "workflow_steps": record["workflow_steps"],
                "rf_tables": record["rf_tables"],
                "semantic_focus": sorted({issue["rule_id"] for issue in matched_issues}),
                "evidence_issues": matched_issues[:12],
            }
        )
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "input_candidates_for_llm_semantic_audit",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--input", type=Path, help="Use an existing fetched dataset JSON instead of querying SQL Server")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.input:
        dataset = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        dataset = fetch_dataset(args.limit)
        (args.output_dir / "latest_finished_work_orders_dataset.json").write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    audit = audit_dataset(dataset)
    (args.output_dir / "latest_finished_work_orders_deterministic_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    semantic_candidates = build_semantic_candidates(audit)
    (args.output_dir / "latest_finished_work_orders_semantic_candidates.json").write_text(
        json.dumps(semantic_candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(audit, args.output_dir / "latest_finished_work_orders_deterministic_report.md")
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
