"""Service entrypoints for operations work order audits.

This module gives the application a stable service API for the current
deterministic audit chain. The implementation reuses the offline script for
now so the data extraction and rules stay identical while the Agent tool and
future scheduler integration are wired up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from app.services.ops_work_order_audit_engine import (
    OUTPUT_DIR,
)
from app.services.ops_audit.dataset_fetcher import DatasetFetchRequest, fetch_ops_audit_dataset as modular_fetch_ops_audit_dataset
from app.services.ops_audit.rule_engine import (
    inspect_rule_engine,
    list_rule_catalog as modular_list_rule_catalog,
    run_rule_engine as modular_run_rule_engine,
)

logger = structlog.get_logger()


RULE_CATALOG = [
    {
        "rule_id": "MAIN_REQUIRED",
        "name": "工单主表关键字段为空",
        "category": "主表完整性",
        "default_severity": "高",
        "scope": "working_orders",
        "rationale": "工单编号、站点、创建时间、完成时间是追溯和统计的基础。",
    },
    {
        "rule_id": "MAIN_STATUS",
        "name": "完工查询结果中工单状态不是 Finish",
        "category": "状态一致性",
        "default_severity": "高",
        "scope": "working_orders",
        "rationale": "审核对象必须是已完成工单。",
    },
    {
        "rule_id": "MAIN_WORKFLOW_STATUS",
        "name": "工作流状态不是 Finish",
        "category": "状态一致性",
        "default_severity": "中",
        "scope": "working_orders",
        "rationale": "主表状态和流程状态不一致会影响是否真正闭环的判断。",
    },
    {
        "rule_id": "MAIN_TIME_ORDER",
        "name": "完成时间早于创建时间",
        "category": "时间合理性",
        "default_severity": "高",
        "scope": "working_orders",
        "rationale": "时间倒置属于明显数据错误。",
    },
    {
        "rule_id": "LIFECYCLE_FINISH_NEAR_DEADLINE",
        "name": "工单临近计划截止时间完成",
        "category": "生命周期闭环风险",
        "default_severity": "低",
        "scope": "working_orders/working_order_details",
        "rationale": "临近截止完成可能是正常赶办，也可能是到期自动完成或补录完成，需要结合流程、RF 和附件复核。",
    },
    {
        "rule_id": "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
        "name": "已完成工单缺少有效闭环证据",
        "category": "生命周期闭环风险",
        "default_severity": "高",
        "scope": "working_orders/working_order_details",
        "rationale": "系统状态为完成不等于实质闭环，缺少处理节点或处理说明时应优先复核。",
    },
    {
        "rule_id": "MAIN_CONTENT_EMPTY",
        "name": "检查/巡检类工单内容为空",
        "category": "主表完整性",
        "default_severity": "中",
        "scope": "working_orders",
        "rationale": "主表内容为空会导致任务要求不可追溯；若 RF 表完整，后续可讨论降级。",
    },
    {
        "rule_id": "MAIN_GENERIC_TITLE",
        "name": "工单标题过于泛化",
        "category": "填报规范性",
        "default_severity": "低",
        "scope": "working_orders",
        "rationale": "标题仅为任务检查单/计划任务单时，无法直接识别任务对象。",
    },
    {
        "rule_id": "MAIN_DEVICE_EMPTY",
        "name": "检查/巡检类工单设备为空或无效",
        "category": "主表完整性",
        "default_severity": "中",
        "scope": "working_orders",
        "rationale": "设备级检查应关联设备；站点级任务需业务口径确认是否豁免。",
    },
    {
        "rule_id": "FLOW_MISSING",
        "name": "完工工单无流程详情",
        "category": "流程完整性",
        "default_severity": "高",
        "scope": "working_order_details",
        "rationale": "缺少流程详情时无法证明工单经过处理闭环。",
    },
    {
        "rule_id": "FLOW_NO_CREATE",
        "name": "缺少创建流程步骤",
        "category": "流程完整性",
        "default_severity": "高",
        "scope": "working_order_details",
        "rationale": "创建步骤是流程链路起点。",
    },
    {
        "rule_id": "FLOW_NO_CHECK",
        "name": "缺少检查/巡检处理步骤",
        "category": "流程完整性",
        "default_severity": "高",
        "scope": "working_order_details",
        "rationale": "检查、巡检、故障类工单应有实际处理节点。",
    },
    {
        "rule_id": "FLOW_NO_REVIEW",
        "name": "检查/巡检工单缺少复核步骤",
        "category": "流程完整性",
        "default_severity": "中",
        "scope": "working_order_details",
        "rationale": "复核是否强制需要按业务流程确认，当前作为可校准规则。",
    },
    {
        "rule_id": "FLOW_END_EMPTY",
        "name": "已完成流程步骤结束时间为空",
        "category": "流程完整性",
        "default_severity": "中",
        "scope": "working_order_details",
        "rationale": "结束时间为空会影响节点时效性计算。",
    },
    {
        "rule_id": "FLOW_REMARK_LOW_VALUE",
        "name": "处理备注为空或信息量低",
        "category": "填报规范性",
        "default_severity": "中",
        "scope": "working_order_details",
        "rationale": "备注缺少原因、措施、结果时，需要语义审核进一步判断闭环性。",
    },
    {
        "rule_id": "RF_AUDITOR_EMPTY",
        "name": "RF 表单审批人为空",
        "category": "表单完整性",
        "default_severity": "低",
        "scope": "RF_*",
        "rationale": "当前作为提示项，需确认审批字段是否实际启用。",
    },
    {
        "rule_id": "RF_REQUIRED_FIELD_LOW_VALUE",
        "name": "RF 表单关键字段为空或低价值",
        "category": "表单完整性",
        "default_severity": "中",
        "scope": "RF_*",
        "rationale": "人员、车辆、备注等关键字段不能为空或仅填写 /、正常、无等低信息内容。",
    },
    {
        "rule_id": "RF_ENV_TEMP_HUMIDITY_EMPTY",
        "name": "RF 表单室内温湿度未填",
        "category": "表单完整性",
        "default_severity": "中",
        "scope": "RF_*",
        "rationale": "巡检和校准记录中的室内温湿度是判断作业环境的重要证据。",
    },
    {
        "rule_id": "RF_CHECK_TIME_OUTSIDE_RANGE",
        "name": "RF 表单检查时间不在开始结束时间内",
        "category": "时间合理性",
        "default_severity": "高",
        "scope": "RF_*",
        "rationale": "检查时间应落在表单记录的开始时间与结束时间之间。",
    },
    {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "name": "RF 表单异常值无说明",
        "category": "结果合理性",
        "default_severity": "中",
        "scope": "RF_*",
        "rationale": "检查值超限或关键值漏填时，应说明原因、处置或免填依据。",
    },
    {
        "rule_id": "RF_Q_MULTIPOINT_METRIC_EMPTY",
        "name": "多点校准关键指标为空",
        "category": "表单完整性",
        "default_severity": "高",
        "scope": "RF_Q_GASEOUSMULTIPOINT_*",
        "rationale": "斜率、截距、相关系数是校准结果判断的关键数据。",
    },
    {
        "rule_id": "RF_Q_PENDING_NO_REMARK",
        "name": "校准结果待定/不合格但无说明",
        "category": "结果合理性",
        "default_severity": "高",
        "scope": "RF_Q_GASEOUSMULTIPOINT_*",
        "rationale": "异常结果必须说明原因、处置和复测安排。",
    },
    {
        "rule_id": "RF_RANGE_BRAND_UNKNOWN",
        "name": "RF 表单仪器品牌无法匹配范围配置",
        "category": "表单结果合理性",
        "default_severity": "低",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "品牌无法识别时不能选择对应正常范围，需要补充品牌别名或核对表单字段。",
    },
    {
        "rule_id": "RF_RANGE_PROFILE_MISSING",
        "name": "RF 表单缺少品牌正常范围配置",
        "category": "表单结果合理性",
        "default_severity": "低",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "该品牌已识别，但具体检查项目还没有配置正常范围。",
    },
    {
        "rule_id": "RF_RANGE_VALUE_MISSING",
        "name": "RF 表单应检项目检查值为空",
        "category": "表单完整性",
        "default_severity": "高",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "当前品牌要求检查的项目缺少检查值，无法判断仪器运行状态。",
    },
    {
        "rule_id": "RF_RANGE_OUT_OF_SPEC",
        "name": "RF 表单检查值超出品牌正常范围",
        "category": "表单结果合理性",
        "default_severity": "高",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "检查值超出对应品牌正常范围，需核对单位、复测或补充异常处理记录。",
    },
]
RULE_CATALOG = modular_list_rule_catalog().get("rules", [])


@dataclass
class OpsWorkOrderAuditConfig:
    """Configuration for a deterministic work order audit run."""

    limit: int = 200
    order_statuses: Optional[list[str]] = None  # 工单状态列表，支持 Finish/Doing/Wait/Invalid，不填默认查所有状态工单
    create_time_start: Optional[str] = None
    create_time_end: Optional[str] = None
    finish_time_start: Optional[str] = None
    finish_time_end: Optional[str] = None
    audit_window_preset: Optional[str] = "weekly_created"
    station_ids: Optional[list[str]] = None
    order_types: Optional[list[str]] = None
    maintenance_types: Optional[list[str]] = None
    working_order_codes: Optional[list[str]] = None
    output_dir: Optional[Path] = None
    input_dataset_path: Optional[Path] = None
    evidence_level: str = "summary"
    persist_dataset: bool = True
    persist_outputs: bool = True


def list_ops_audit_rules() -> dict[str, Any]:
    """Return deterministic rule metadata for discussion and calibration."""

    result = modular_list_rule_catalog()
    result["calibration_notes"] = [
        "RF_AUDITOR_EMPTY 是否计为问题，需要按当前业务流程确认。",
        "MAIN_CONTENT_EMPTY 若 RF 表单完整，可考虑从中风险降为提示。",
        "FLOW_NO_REVIEW 是否强制，应按工单类型、维护类型和流程配置校准。",
    ]
    return result


def fetch_ops_audit_dataset(config: Optional[OpsWorkOrderAuditConfig] = None) -> dict[str, Any]:
    """Fetch and persist the aligned dataset without running audit rules."""
    config = config or OpsWorkOrderAuditConfig()
    request = DatasetFetchRequest(
        limit=config.limit,
        order_statuses=config.order_statuses,
        create_time_start=config.create_time_start,
        create_time_end=config.create_time_end,
        finish_time_start=config.finish_time_start,
        finish_time_end=config.finish_time_end,
        audit_window_preset=config.audit_window_preset,
        station_ids=config.station_ids,
        order_types=config.order_types,
        maintenance_types=config.maintenance_types,
        working_order_codes=config.working_order_codes,
        evidence_level=config.evidence_level,
        output_dir=config.output_dir,
        persist_dataset=config.persist_dataset,
    )
    return modular_fetch_ops_audit_dataset(request)


def run_ops_audit_rules(
    dataset_path: Path,
    output_dir: Optional[Path] = None,
    *,
    persist_outputs: bool = True,
    evidence_level: str = "summary",
    enable_visual: bool = True,
) -> dict[str, Any]:
    """Run audit rules against an existing dataset and assemble final issues."""
    resolved_dataset_path = dataset_path.resolve()
    dataset = json.loads(resolved_dataset_path.read_text(encoding="utf-8"))
    result = modular_run_rule_engine(
        dataset,
        output_dir=output_dir or resolved_dataset_path.parent,
        persist_outputs=persist_outputs,
        evidence_level=evidence_level,
        enable_visual=enable_visual,
    )
    result["dataset_path"] = str(resolved_dataset_path)
    result["calibration_questions"] = [
        "RF 表单审批人为空是否在当前业务流程中必须判为问题，还是仅作为提示？",
        "巡检类工单主表内容为空但 RF 表完整时，是否应降低风险等级？",
        "缺少 Review 是否对全部 Check/SupCheck 生效，还是只对部分维护类型生效？",
        "流程备注为空是否直接判不规范，还是交给语义审核结合 RF 表和附件判断？",
    ]
    return result


def inspect_ops_audit(
    audit_result_path: Path,
    *,
    dataset_path: Optional[Path] = None,
    mode: str = "sample_rule",
    working_order_code: Optional[str] = None,
    rule_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Inspect existing audit output for conversation and calibration."""
    return inspect_rule_engine(
        audit_result_path,
        dataset_path=dataset_path,
        mode=mode,
        working_order_code=working_order_code,
        rule_id=rule_id,
        risk_level=risk_level,
        limit=limit,
    )


def run_ops_work_order_deterministic_audit(config: Optional[OpsWorkOrderAuditConfig] = None) -> dict[str, Any]:
    """Run the complete deterministic audit chain.

    Chain:
    1. load/fetch recent finished work orders and related records
    2. execute deterministic rules
    3. build semantic audit candidates
    4. persist dataset, audit JSON, candidates JSON, and markdown report
    """

    config = config or OpsWorkOrderAuditConfig()
    if config.input_dataset_path:
        dataset_path = config.input_dataset_path.resolve()
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        result = modular_run_rule_engine(
            dataset,
            output_dir=config.output_dir or OUTPUT_DIR,
            persist_outputs=config.persist_outputs,
            evidence_level="summary",
        )
        result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["coverage"] = _dataset_coverage(dataset)
        result["paths"] = {
            "output_dir": str((config.output_dir or OUTPUT_DIR).resolve()),
            "dataset": str(dataset_path),
            "audit_json": result.get("audit_result_path"),
            "semantic_candidates": result.get("semantic_candidates_path"),
            "semantic_review_tasks": result.get("semantic_review_tasks_path"),
        }
        return result

    fetch_result = fetch_ops_audit_dataset(config)
    dataset_path = Path(fetch_result["dataset_path"])
    result = modular_run_rule_engine(
        json.loads(dataset_path.read_text(encoding="utf-8")),
        output_dir=config.output_dir or OUTPUT_DIR,
        persist_outputs=config.persist_outputs,
        evidence_level="summary",
    )
    result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["audit_window"] = fetch_result.get("audit_window")
    result["coverage"] = fetch_result.get("coverage")
    result["paths"] = {
        "output_dir": str((config.output_dir or OUTPUT_DIR).resolve()),
        "dataset": str(dataset_path),
        "audit_json": result.get("audit_result_path"),
        "semantic_candidates": result.get("semantic_candidates_path"),
        "semantic_review_tasks": result.get("semantic_review_tasks_path"),
    }
    return result


def _count_field(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get(field) or "<空>")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _dataset_coverage(dataset: dict[str, Any]) -> dict[str, Any]:
    orders = dataset.get("orders", [])
    create_times = sorted(str(order.get("CREATETIME")) for order in orders if order.get("CREATETIME"))
    finish_times = sorted(str(order.get("FINISHTIME")) for order in orders if order.get("FINISHTIME"))
    station_ids = {str(order.get("STATIONID")) for order in orders if order.get("STATIONID")}
    return {
        "query_info": dataset.get("query_info", {}),
        "actual_create_time_start": create_times[0] if create_times else None,
        "actual_create_time_end": create_times[-1] if create_times else None,
        "actual_finish_time_start": finish_times[0] if finish_times else None,
        "actual_finish_time_end": finish_times[-1] if finish_times else None,
        "station_count": len(station_ids),
        "station_sample": sorted(station_ids)[:20],
        "has_orders": bool(orders),
    }


def _business_review_summary(audit: dict[str, Any]) -> dict[str, Any]:
    records = audit.get("records", [])
    confirmed_rules: dict[str, dict[str, Any]] = {}
    candidate_rules: dict[str, dict[str, Any]] = {}
    calibration_rules: dict[str, dict[str, Any]] = {}

    for record in records:
        for issue in record.get("issues", []):
            target = candidate_rules
            assessment = issue.get("assessment")
            if assessment == "deterministic_issue":
                target = confirmed_rules
            rule_id = issue.get("rule_id") or "<unknown>"
            entry = target.setdefault(
                rule_id,
                {
                    "rule_id": rule_id,
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                    "category": issue.get("category"),
                    "hit_count": 0,
                    "affected_order_codes": set(),
                    "sample_order_codes": [],
                },
            )
            entry["hit_count"] += 1
            code = record.get("working_order_code")
            if code:
                entry["affected_order_codes"].add(code)
                if len(entry["sample_order_codes"]) < 5 and code not in entry["sample_order_codes"]:
                    entry["sample_order_codes"].append(code)

    return {
        "confirmed_issues": _finalize_rule_group(confirmed_rules),
        "candidate_issues": _finalize_rule_group(candidate_rules),
        "calibration_items": [],
        "recommended_next_steps": [
            "先处理 confirmed_issues 中的确定性规则问题。",
            "对 candidate_issues 抽样查看 RF 表、流程备注和附件后再批量定性。",
        ],
    }


def _finalize_rule_group(group: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    finalized = []
    for item in group.values():
        order_codes = item.pop("affected_order_codes")
        item["affected_order_count"] = len(order_codes)
        finalized.append(item)
    return sorted(finalized, key=lambda item: (item["affected_order_count"], item["hit_count"]), reverse=True)


def _build_dataset_filter(config: OpsWorkOrderAuditConfig) -> WorkOrderDatasetFilter:
    return WorkOrderDatasetFilter(
        limit=max(1, min(int(config.limit or 200), 3000)),
        order_statuses=config.order_statuses,
        create_time_start=config.create_time_start,
        create_time_end=config.create_time_end,
        finish_time_start=config.finish_time_start,
        finish_time_end=config.finish_time_end,
        station_ids=config.station_ids,
        order_types=config.order_types,
        maintenance_types=config.maintenance_types,
        working_order_codes=config.working_order_codes,
    )


def _apply_audit_window_defaults(config: OpsWorkOrderAuditConfig) -> dict[str, Any] | None:
    """Apply the default weekly created-time audit window when no explicit time is provided."""

    preset = (config.audit_window_preset or "").strip().lower()
    has_explicit_time = any(
        [
            config.create_time_start,
            config.create_time_end,
            config.finish_time_start,
            config.finish_time_end,
            config.working_order_codes,
        ]
    )
    if preset in {"", "none", "off", "disabled"} or has_explicit_time:
        return None
    if preset != "weekly_created":
        raise ValueError(f"不支持的审核窗口预设：{config.audit_window_preset}")

    window = calculate_weekly_created_window()
    config.create_time_start = window.create_time_start
    config.create_time_end = window.create_time_end
    if not config.order_statuses:
        config.order_statuses = window.order_statuses
    return window.to_dict()


def _representative_issues(audit: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    representatives = []
    seen_rules: set[str] = set()
    for record in audit.get("records", []):
        if not (record.get("deterministic_issues") or record.get("candidate_issues") or record.get("issues")):
            continue
        issue = (record.get("deterministic_issues") or record.get("candidate_issues") or record.get("issues"))[0]
        rule_id = issue.get("rule_id")
        if rule_id in seen_rules and len(representatives) >= limit:
            continue
        seen_rules.add(rule_id)
        representatives.append(
            {
                "working_order_code": record.get("working_order_code"),
                "station_id": record.get("station_id"),
                "order_type": record.get("order_type"),
                "audit_level": record.get("audit_level"),
                "matched_rule": issue,
                "matched_rule_count": len(record.get("issues", [])),
                "workflow_steps": record.get("workflow_steps", []),
                "rf_tables": record.get("rf_tables", []),
            }
        )
        if len(representatives) >= limit:
            break
    return representatives


def _review_samples(audit: dict[str, Any], dataset: Optional[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    business_review = _business_review_summary(audit)
    records = audit.get("records", [])
    samples = []
    per_group_limit = max(1, limit // 3)
    groups = [
        ("confirmed_issues", "硬性结构或逻辑问题，可作为整改清单候选。"),
        ("candidate_issues", "待确认问题，需要结合流程、RF 表和语义判断复核。"),
    ]
    for group_name, review_hint in groups:
        for rule in business_review.get(group_name, [])[:per_group_limit]:
            rule_id = rule.get("rule_id")
            matched = [
                record
                for record in records
                if any(issue.get("rule_id") == rule_id for issue in record.get("issues", []))
            ][:2]
            samples.append(
                {
                    "group": group_name,
                    "rule": rule,
                    "review_hint": review_hint,
                    "samples": [
                        _build_inspection_item(record, dataset, focus_rule_id=rule_id)
                        for record in matched
                    ],
                }
            )
            if len(samples) >= limit:
                return samples
    return samples


def _build_inspection_item(record: dict[str, Any], dataset: Optional[dict[str, Any]], focus_rule_id: Optional[str] = None) -> dict[str, Any]:
    code = record.get("working_order_code")
    issues = record.get("issues", [])
    if focus_rule_id:
        focused = [issue for issue in issues if issue.get("rule_id") == focus_rule_id]
        others = [issue for issue in issues if issue.get("rule_id") != focus_rule_id]
        returned_issues = focused + others[: max(0, 12 - len(focused))]
    else:
        returned_issues = issues[:12]
    item = {
        "working_order_code": code,
        "station_id": record.get("station_id"),
        "order_type": record.get("order_type"),
        "maintenance_type": record.get("maintenance_type"),
        "audit_level": record.get("audit_level"),
        "matched_rules": [issue.get("rule_id") for issue in record.get("issues", [])],
        "deterministic_rules": record.get("deterministic_rules", []),
        "candidate_rules": record.get("candidate_rules", []),
        "deterministic_issue_count": record.get("deterministic_issue_count", 0),
        "candidate_issue_count": record.get("candidate_issue_count", 0),
        "issues": returned_issues,
        "workflow_steps": record.get("workflow_steps", []),
        "rf_tables": record.get("rf_tables", []),
        "attachment_count": record.get("attachment_count", 0),
        "attachment_review_rules": record.get("attachment_review_rules", []),
    }
    if not dataset:
        return item

    orders = [order for order in dataset.get("orders", []) if order.get("WORKINGORDERCODE") == code]
    details = [detail for detail in dataset.get("details", []) if detail.get("WORKINGORDERCODE") == code]
    rf_rows = []
    for table, rows in dataset.get("rf_forms", {}).items():
        for row in rows:
            if row.get("WORKINGORDERCODE") == code:
                rf_rows.append(
                    {
                        "table": table,
                        "station_id": row.get("STATIONID"),
                        "createdate": row.get("CREATEDATE"),
                        "checkdate": row.get("CHECKDATE") or row.get("CALIBRATIONDATE"),
                        "preparer": row.get("PREPARERUSERID"),
                        "reviewer": row.get("REVIEWUSERID"),
                        "auditor": row.get("AUDITORUSERID"),
                        "pollutant": row.get("PollutantType") or row.get("POLLUTANTTYPE"),
                        "remarks": row.get("CleaningRemark") or row.get("REMARKS"),
                    }
                )
    item["order_summary"] = orders[0] if orders else None
    item["workflow_summary"] = details[:12]
    item["rf_summary"] = rf_rows[:20]
    return item
