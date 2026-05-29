"""Agent tools for interactive operations work order audits."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.services.ops_work_order_audit import (
    OUTPUT_DIR,
    OpsWorkOrderAuditConfig,
    fetch_ops_audit_dataset,
    inspect_ops_audit,
    list_ops_audit_rules,
    run_ops_audit_rules,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


def _standard_success(tool_name: str, summary: str, data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {
        "tool_name": tool_name,
        "generator": tool_name,
    }
    data_id = data.get("data_id") if isinstance(data, dict) else None
    if data_id:
        metadata["data_id"] = data_id

    result = {
        "status": "success",
        "success": True,
        "summary": summary,
        "data": data,
        "metadata": metadata,
    }
    if data_id:
        result["data_id"] = data_id
    return result


def _standard_failure(tool_name: str, summary: str, error: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "summary": summary,
        "data": data or {"error": error},
        "metadata": {
            "tool_name": tool_name,
            "generator": tool_name,
            "error": error,
        },
    }



class OpsAuditFetchDatasetTool(LLMTool):
    """Fetch aligned work order data by status without auditing it."""

    def __init__(self) -> None:
        super().__init__(
            name="ops_audit_fetch_dataset",
            description="Fetch operations work orders with workflow, RF forms, and attachments by status, time, station, and type.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "ops_audit_fetch_dataset",
                "description": "抽取并对齐工单、流程、RF表单和附件，只返回数据覆盖情况，不执行审核规则。支持按状态、时间、站点、类型等多维度过滤。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "工单数量，默认200，最大2000。"},
                        "order_statuses": {"type": "array", "items": {"type": "string"}, "description": "工单状态列表，支持 Finish/Doing/Wait/Invalid，不填默认查所有状态工单。"},
                        "create_time_start": {"type": "string", "description": "创建时间起始，包含该时间，如 2026-05-13 00:00:00。周期审核优先使用创建时间。"},
                        "create_time_end": {"type": "string", "description": "创建时间结束，不包含该时间，如 2026-05-20 00:00:00。周期审核优先使用创建时间。"},
                        "finish_time_start": {"type": "string", "description": "完成时间起始，包含该时间，如 2026-05-23 00:00:00。"},
                        "finish_time_end": {"type": "string", "description": "完成时间结束，不包含该时间，如 2026-05-24 00:00:00。"},
                        "audit_window_preset": {"type": "string", "description": "审核窗口预设：weekly_created 默认按最近周三回看上上周三至上周三创建且已完成工单；none 关闭默认窗口。"},
                        "evidence_level": {"type": "string", "enum": ["summary", "detail", "raw"], "description": "证据层级：summary 默认，detail 加载结构化明细，raw 仅保存引用。"},
                        "station_id": {"type": "string", "description": "单个站点ID；如需多个站点使用 station_ids。"},
                        "station_ids": {"type": "array", "items": {"type": "string"}, "description": "站点ID列表。"},
                        "order_type": {"type": "string", "description": "单个工单类型，如 Check、Fault；如需多个类型使用 order_types。"},
                        "order_types": {"type": "array", "items": {"type": "string"}, "description": "工单类型列表。"},
                        "maintenance_type": {"type": "string", "description": "单个维护类型，如 Week、Month；如需多个类型使用 maintenance_types。"},
                        "maintenance_types": {"type": "array", "items": {"type": "string"}, "description": "维护类型列表。"},
                        "working_order_codes": {"type": "array", "items": {"type": "string"}, "description": "指定工单编号列表；用于精确抽取目标工单。"},
                        "output_dir": {"type": "string", "description": "输出目录；不填使用默认审核运维目录。"},
                    },
                    "required": [],
                },
            },
            version="0.3.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        limit: int = 200,
        order_statuses: Optional[list[str]] = None,
        create_time_start: Optional[str] = None,
        create_time_end: Optional[str] = None,
        finish_time_start: Optional[str] = None,
        finish_time_end: Optional[str] = None,
        audit_window_preset: Optional[str] = "weekly_created",
        evidence_level: str = "summary",
        station_id: Optional[str] = None,
        station_ids: Optional[list[str]] = None,
        order_type: Optional[str] = None,
        order_types: Optional[list[str]] = None,
        maintenance_type: Optional[str] = None,
        maintenance_types: Optional[list[str]] = None,
        working_order_codes: Optional[list[str]] = None,
        output_dir: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = fetch_ops_audit_dataset(
                OpsWorkOrderAuditConfig(
                    limit=max(1, min(int(limit or 200), 2000)),
                    order_statuses=_merge_single_and_many(None, order_statuses),
                    create_time_start=create_time_start,
                    create_time_end=create_time_end,
                    finish_time_start=finish_time_start,
                    finish_time_end=finish_time_end,
                    audit_window_preset=audit_window_preset,
                    station_ids=_merge_single_and_many(station_id, station_ids),
                    order_types=_merge_single_and_many(order_type, order_types),
                    maintenance_types=_merge_single_and_many(maintenance_type, maintenance_types),
                    working_order_codes=_as_list(working_order_codes),
                    evidence_level=evidence_level,
                    output_dir=Path(output_dir) if output_dir else None,
                )
            )
            summary_text = self._summary_text(result)
            result["summary_text"] = summary_text
            return _standard_success(self.name, summary_text, result)
        except Exception as exc:
            logger.error("ops_audit_fetch_dataset_failed", error=str(exc), exc_info=True)
            return _standard_failure(self.name, f"工单审核数据抽取失败: {str(exc)}", str(exc))

    def _summary_text(self, result: Dict[str, Any]) -> str:
        summary = result.get("summary", {})
        audit_window = result.get("audit_window") or {}
        window_text = ""
        if audit_window:
            window_text = (
                f"审核窗口：创建时间 {audit_window.get('create_time_start')} 至 "
                f"{audit_window.get('create_time_end')}；"
            )
        return (
            window_text +
            f"已抽取 {summary.get('order_count', 0)} 条工单，"
            f"流程 {summary.get('detail_count', 0)} 条，RF记录 {summary.get('rf_record_count', 0)} 条，"
            f"附件 {summary.get('attachment_count', 0)} 条，通用文件 {summary.get('wo_commonfile_count', 0)} 条，"
            f"设备 {summary.get('device_count', 0)} 条，"
            f"同设备历史工单 {summary.get('device_history_order_count', 0)} 条。数据集：{result.get('dataset_path')}"
        )


def _as_list(values: Optional[list[str] | str]) -> list[str] | None:
    if values is None:
        return None
    if isinstance(values, str):
        parts = [part.strip() for part in values.split(",")]
    else:
        parts = [str(value).strip() for value in values]
    cleaned = [part for part in parts if part]
    return cleaned or None


def _merge_single_and_many(single: Optional[str], many: Optional[list[str]]) -> list[str] | None:
    values = []
    if single:
        values.append(single)
    if many:
        values.extend(many)
    return _as_list(values)


def _context_summary_record(result: Dict[str, Any]) -> Dict[str, Any]:
    business = result.get("business_review", {})
    return {
        "dataset_path": result.get("dataset_path"),
        "audit_result_path": result.get("audit_result_path"),
        "semantic_candidates_path": result.get("semantic_candidates_path"),
        "semantic_review_tasks_path": result.get("semantic_review_tasks_path"),
        "semantic_review_results_path": result.get("semantic_review_results_path"),
        "final_issue_list_path": result.get("final_issue_list_path"),
        "classification_counts": result.get("summary", {}).get("audit_level_counts", {}),
        "semantic_candidate_count": result.get("semantic_candidate_count", 0),
        "semantic_review_task_count": result.get("semantic_review_task_count", 0),
        "semantic_review_result_count": result.get("semantic_review_result_count", 0),
        "final_issue_count": result.get("final_issue_count", 0),
        "final_affected_order_count": result.get("final_affected_order_count", 0),
        "confirmed_issue_types": len(business.get("confirmed_issues", [])),
        "candidate_issue_types": len(business.get("candidate_issues", [])),
    }


def _latest_dataset_path() -> Optional[Path]:
    candidates = [
        path
        for path in OUTPUT_DIR.parent.rglob("latest_finished_work_orders_dataset.json")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _resolve_dataset_path(dataset_path: Path) -> Path:
    resolved = dataset_path.expanduser().resolve()
    if resolved.exists():
        return resolved
    latest = _latest_dataset_path()
    if latest and dataset_path.name in {"latest_finished_work_orders_dataset.json"}:
        return latest.resolve()
    return resolved


class OpsAuditRunRulesTool(LLMTool):
    """Run deterministic audit rules against an existing dataset."""

    def __init__(self) -> None:
        super().__init__(
            name="ops_audit_run_rules",
            description="Run operations work order audit rules against a fetched dataset and assemble the final issue list.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "ops_audit_run_rules",
                "description": "基于已抽取数据集执行确定性规则、流量图片视觉比对和备注语义辅助复核，并生成 final_issue_list 供报告消费。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset_path": {"type": "string", "description": "ops_audit_fetch_dataset 返回的数据集JSON路径。"},
                        "output_dir": {"type": "string", "description": "审核结果输出目录；不填使用数据集所在目录。"},
                        "evidence_level": {"type": "string", "enum": ["summary", "detail", "raw"], "description": "证据层级：summary 默认，detail 加载结构化明细，raw 仅引用原始证据路径。"},
                    },
                    "required": ["dataset_path"],
                },
            },
            version="0.2.0",
            requires_context=True,
        )

    async def execute(self, context=None, dataset_path: str = "", output_dir: Optional[str] = None, evidence_level: str = "summary", **_: Any) -> Dict[str, Any]:
        if not dataset_path:
            return _standard_failure(self.name, "请提供 dataset_path。", "missing_dataset_path")
        try:
            resolved_dataset_path = _resolve_dataset_path(Path(dataset_path))
            if not resolved_dataset_path.exists():
                return _standard_failure(
                    self.name,
                    f"数据集文件不存在：{dataset_path}。请使用 ops_audit_fetch_dataset 返回的 data.dataset_path 原值。",
                    "dataset_path_not_found",
                    {"dataset_path": dataset_path, "latest_dataset_path": str(_latest_dataset_path()) if _latest_dataset_path() else None},
                )
            result = run_ops_audit_rules(
                resolved_dataset_path,
                output_dir=Path(output_dir) if output_dir else None,
                evidence_level=evidence_level,
            )
            if context and hasattr(context, "save_data"):
                result["data_id"] = context.save_data(
                    data=[_context_summary_record(result)],
                    schema="ops_audit_rule_summary",
                    metadata={"tool": self.name, "dataset_path": str(resolved_dataset_path)},
                )
            summary_text = self._summary_text(result)
            result["summary_text"] = summary_text
            return _standard_success(self.name, summary_text, result)
        except Exception as exc:
            logger.error("ops_audit_run_rules_failed", error=str(exc), exc_info=True)
            return _standard_failure(self.name, f"工单确定性规则执行失败: {str(exc)}", str(exc))

    def _summary_text(self, result: Dict[str, Any]) -> str:
        levels = result.get("summary", {}).get("audit_level_counts", {})
        top_rules = result.get("summary", {}).get("top_rules", [])[:5]
        business = result.get("business_review", {})
        level_text = "，".join(f"{key}{value}条" for key, value in levels.items())
        rule_text = "，".join(f"{rule_id}({count})" for rule_id, count in top_rules)
        return (
            f"确定性规则和流量图片视觉比对已执行。分类分布：{level_text}。"
            f"备注语义候选 {result.get('semantic_candidate_count', 0)} 条。"
            f"备注语义复核结果 {result.get('semantic_review_result_count', 0)} 条（仅用于闭环说明辅助定性）。"
            f"备注语义复核任务 {result.get('semantic_review_task_count', 0)} 条。"
            f"最终问题清单 {result.get('final_issue_count', 0)} 条，"
            f"涉及工单 {result.get('final_affected_order_count', 0)} 条。"
            f"确定问题 {len(business.get('confirmed_issues', []))} 类，"
            f"待确认问题 {len(business.get('candidate_issues', []))} 类。"
            f"跨工单设备一致性问题 {result.get('device_consistency_issue_count', 0)} 条。"
            f"附件清单问题 {result.get('attachment_issue_count', 0)} 条，"
            f"附件复核候选 {result.get('attachment_review_candidate_count', 0)} 条。"
            f"高频规则：{rule_text}。结果文件："
            f"dataset={result.get('dataset_path')}；"
            f"audit={result.get('audit_result_path')}；"
            f"semantic_candidates={result.get('semantic_candidates_path')}；"
            f"semantic_tasks={result.get('semantic_review_tasks_path')}；"
            f"semantic_results={result.get('semantic_review_results_path')}；"
            f"final_issue_list={result.get('final_issue_list_path')}"
        )


class OpsAuditInspectTool(LLMTool):
    """Inspect rules, audit records, samples, and semantic candidates."""

    def __init__(self) -> None:
        super().__init__(
            name="ops_audit_inspect",
            description="Inspect work order audit rules and existing audit outputs for conversation and calibration.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "ops_audit_inspect",
                "description": "查看确定性规则目录、抽样命中问题、查看单个工单证据或获取语义审核候选。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                        "enum": ["rules", "order", "sample_rule", "risk", "semantic_candidates", "semantic_review_results", "review_samples"],
                        "description": "查看模式。",
                    },
                        "audit_result_path": {"type": "string", "description": "审核结果JSON路径；rules模式不需要。"},
                        "dataset_path": {"type": "string", "description": "可选：原始数据集JSON路径，用于返回主表/流程/RF证据。"},
                        "working_order_code": {"type": "string", "description": "order模式使用的工单编号。"},
                        "rule_id": {"type": "string", "description": "sample_rule模式使用的规则ID。"},
                        "risk_level": {"type": "string", "description": "risk模式使用的风险等级，如 高风险/需补正。"},
                        "limit": {"type": "integer", "description": "返回条数，默认10，最大50。"},
                    },
                    "required": ["mode"],
                },
            },
            version="0.2.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        mode: str = "rules",
        audit_result_path: Optional[str] = None,
        dataset_path: Optional[str] = None,
        working_order_code: Optional[str] = None,
        rule_id: Optional[str] = None,
        risk_level: Optional[str] = None,
        limit: int = 10,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            if mode == "rules":
                result = list_ops_audit_rules()
            else:
                if not audit_result_path:
                    return _standard_failure(self.name, "该模式需要 audit_result_path。", "missing_audit_result_path")
                result = inspect_ops_audit(
                    Path(audit_result_path),
                    dataset_path=Path(dataset_path) if dataset_path else None,
                    mode=mode,
                    working_order_code=working_order_code,
                    rule_id=rule_id,
                    risk_level=risk_level,
                    limit=max(1, min(int(limit or 10), 50)),
                )
            summary_text = self._summary_text(mode, result)
            result["summary_text"] = summary_text
            return _standard_success(self.name, summary_text, result)
        except Exception as exc:
            logger.error("ops_audit_inspect_failed", error=str(exc), exc_info=True)
            return _standard_failure(self.name, f"工单审核结果查看失败: {str(exc)}", str(exc))

    def _summary_text(self, mode: str, result: Dict[str, Any]) -> str:
        if mode == "rules":
            return f"当前确定性规则 {result.get('rule_count', 0)} 条，可用于规则解释和口径校准。"
        if mode == "semantic_candidates":
            return f"已返回 {result.get('count', 0)} 条备注语义复核候选；候选不是最终结论，需结合闭环说明复核。"
        if mode == "semantic_review_results":
            return f"已返回 {result.get('count', 0)} 条备注语义复核结果；最终报告以 final_issue_list 为准。"
        if mode == "review_samples":
            return f"已返回 {result.get('count', 0)} 条抽样复核证据，可用于校准规则口径和最终结论。"
        return f"已返回 {result.get('count', 0)} 条 {mode} 检查结果。"


async def ops_audit_fetch_dataset(context=None, **kwargs: Any) -> Dict[str, Any]:
    """Function export for callers that invoke the audit tool directly."""
    return await OpsAuditFetchDatasetTool().execute(context=context, **kwargs)


async def ops_audit_run_rules(context=None, **kwargs: Any) -> Dict[str, Any]:
    """Function export for callers that invoke the audit tool directly."""
    return await OpsAuditRunRulesTool().execute(context=context, **kwargs)


async def ops_audit_inspect(context=None, **kwargs: Any) -> Dict[str, Any]:
    """Function export for callers that invoke the audit tool directly."""
    return await OpsAuditInspectTool().execute(context=context, **kwargs)


__all__ = [
    "OpsAuditFetchDatasetTool",
    "OpsAuditRunRulesTool",
    "OpsAuditInspectTool",
    "ops_audit_fetch_dataset",
    "ops_audit_run_rules",
    "ops_audit_inspect",
]
