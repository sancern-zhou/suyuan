"""Agent tools for the ops audit self-iteration loop (channels 2 & 3).

- ``ops_audit_reconcile_checklist``: reconcile a user-submitted problem
  checklist against one final issue list (channel 2) and append the
  classification matrix to the feedback ledger.
- ``ops_audit_retrospective_stats``: deterministic monthly statistics over the
  feedback ledger, optionally running the DB recheck triage (channel 3).

The stats layer counts so the LLM never does; the workflow (how to normalize a
checklist, what to write in the monthly report) lives in the
``ops_audit_retrospective`` skill.  Red line: neither tool modifies rule
configs or rewrites audit artifacts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import get_memory_dir, resolve_agent_path

logger = logging.getLogger(__name__)

MAX_ECHO_LINES = 80


def _success(tool_name: str, summary: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "success": True,
        "summary": summary,
        "data": data,
        "metadata": {"tool_name": tool_name, "generator": tool_name},
    }


def _failure(tool_name: str, summary: str, error: str) -> Dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "summary": summary,
        "data": {"error": error},
        "metadata": {"tool_name": tool_name, "generator": tool_name, "error": error},
    }


class OpsAuditReconcileChecklistTool(LLMTool):
    """Channel-2 checklist reconciliation against one final issue list."""

    def __init__(self) -> None:
        super().__init__(
            name="ops_audit_reconcile_checklist",
            description="Reconcile a user checklist against one ops audit final issue list into feedback ledger outcomes.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "ops_audit_reconcile_checklist",
                "description": (
                    "将用户核对清单与当期工单审核结果逐单对账（通道2），产出 confirmed/missed/"
                    "rejected/tacit_confirmed 分类并落反馈台账。先向用户确认全量/部分核对声明；"
                    "problem_category 必须用规则目录分类词表（错误信息会回显词表）；"
                    "对账编排细则先 view_skill: ops_audit_retrospective。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "final_issue_list_path": {
                            "type": "string",
                            "description": "当期审核的 final_issue_list JSON 路径（工具结果原值）。",
                        },
                        "checklist_items": {
                            "type": "array",
                            "description": "清单条目（从用户文档结构化）：verdict=problem(说有问题)/ok(说没问题)。",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "order_code": {"type": "string", "description": "工单编号。"},
                                    "verdict": {
                                        "type": "string",
                                        "enum": ["problem", "ok"],
                                        "description": "problem=用户说该单有问题；ok=用户说该单没问题。",
                                    },
                                    "problem_category": {
                                        "type": "string",
                                        "description": "问题分类（规则目录 category 词表，如 一致性问题/时间合理性问题）；省略=工单级任意类型匹配。",
                                    },
                                    "note": {"type": "string", "description": "用户原文描述（留档）。"},
                                },
                                "required": ["order_code", "verdict"],
                            },
                        },
                        "full_review_declared": {
                            "type": "boolean",
                            "description": "用户是否声明全量核对（true 才产生 tacit_confirmed 且错误率可算）。",
                        },
                        "dataset_path": {
                            "type": "string",
                            "description": "当期数据集 JSON 路径（可选，用于识别不在期次的工单号）。",
                        },
                        "checklist_source_path": {
                            "type": "string",
                            "description": "用户上传的原始清单文件路径（可选，归档留证）。",
                        },
                        "reviewer_name": {
                            "type": "string",
                            "description": "提交人（可选）。",
                        },
                    },
                    "required": ["final_issue_list_path", "checklist_items", "full_review_declared"],
                },
            },
            version="0.1.0",
        )

    async def execute(
        self,
        context=None,
        final_issue_list_path: str = "",
        checklist_items: Optional[List[Dict[str, Any]]] = None,
        full_review_declared: bool = False,
        dataset_path: Optional[str] = None,
        checklist_source_path: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        if not final_issue_list_path or not checklist_items:
            return _failure(
                self.name, "需要 final_issue_list_path 与 checklist_items。", "missing_arguments"
            )
        try:
            result = await asyncio.to_thread(
                _reconcile_sync,
                final_issue_list_path,
                checklist_items,
                full_review_declared,
                dataset_path,
                checklist_source_path,
                reviewer_name,
            )
            return _success(self.name, _reconcile_summary(result), result)
        except ValueError as exc:
            return _failure(self.name, f"清单对账失败: {exc}", str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("ops_audit_reconcile_checklist_failed")
            return _failure(self.name, f"清单对账失败: {exc}", str(exc))


class OpsAuditRetrospectiveStatsTool(LLMTool):
    """Deterministic monthly stats over the feedback ledger (+ channel-3 triage)."""

    def __init__(self) -> None:
        super().__init__(
            name="ops_audit_retrospective_stats",
            description="Aggregate the ops audit feedback ledger into monthly retrospective stats, optionally with DB recheck triage.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "ops_audit_retrospective_stats",
                "description": (
                    "统计反馈台账形成月度复盘 stats JSON（通道/结局计数、清单识别率与错误率、"
                    "按规则人工推翻率、候选新规则、滚动趋势），可选通道3 回库分诊"
                    "（对 rejected 项重取源数据复跑规则三分类）。只读统计，不改任何规则配置；"
                    "复盘报告写法先 view_skill: ops_audit_retrospective。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "month": {
                            "type": "string",
                            "description": "统计月份 YYYY-MM；缺省为上一自然月。",
                        },
                        "enable_db_recheck": {
                            "type": "boolean",
                            "description": "是否执行通道3 回库分诊（重取源库+复跑规则，默认 false 控 DB 负载）。",
                        },
                    },
                    "required": [],
                },
            },
            version="0.1.0",
        )

    async def execute(
        self,
        context=None,
        month: Optional[str] = None,
        enable_db_recheck: bool = False,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = await asyncio.to_thread(_stats_sync, month, bool(enable_db_recheck))
            return _success(self.name, _stats_summary(result), result)
        except ValueError as exc:
            return _failure(self.name, f"复盘统计失败: {exc}", str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("ops_audit_retrospective_stats_failed")
            return _failure(self.name, f"复盘统计失败: {exc}", str(exc))


# --------------------------------------------------------------------------
# sync worker functions (always called via asyncio.to_thread)
# --------------------------------------------------------------------------

def _reconcile_sync(
    final_issue_list_path: str,
    checklist_items: List[Dict[str, Any]],
    full_review_declared: bool,
    dataset_path: Optional[str],
    checklist_source_path: Optional[str],
    reviewer_name: Optional[str],
) -> Dict[str, Any]:
    from app.services.ops_audit import feedback_ledger
    from app.services.ops_audit.checklist_reconcile import (
        append_reconciliation_to_ledger,
        archive_reconciliation,
        normalize_checklist_items,
        reconcile_checklist,
    )

    # Validate the structured checklist first: the vocabulary error is the
    # agent's correction hook and must fire even if the issue list path is bad.
    normalize_checklist_items(checklist_items)
    issue_path = resolve_agent_path(final_issue_list_path)
    if not issue_path.is_file():
        raise ValueError(f"final_issue_list 不存在：{final_issue_list_path}")
    final_issue_list = json.loads(issue_path.read_text(encoding="utf-8"))
    dataset_orders = _dataset_order_codes(dataset_path)
    reviewer = {"name": reviewer_name} if reviewer_name else None
    reconciliation = reconcile_checklist(
        final_issue_list,
        checklist_items,
        full_review_declared=full_review_declared,
        reviewer=reviewer,
        dataset_orders=dataset_orders,
        final_issue_list_path=issue_path,
    )
    append_result = append_reconciliation_to_ledger(reconciliation)
    archive_dir = archive_reconciliation(
        reconciliation,
        final_issue_list_path=issue_path,
        checklist_source_path=resolve_agent_path(checklist_source_path)
        if checklist_source_path
        else None,
        checklist_items=checklist_items,
    )
    if not append_result["deduplicated"]:
        feedback_ledger.append_metrics_history(
            {
                "kind": "checklist_reconciliation",
                "reconciliation_id": reconciliation["reconciliation_id"],
                "full_review_declared": full_review_declared,
                "source_sha256": reconciliation["source_sha256"],
                "metrics": reconciliation["metrics"],
            }
        )
    return {
        "reconciliation_id": reconciliation["reconciliation_id"],
        "full_review_declared": full_review_declared,
        "metrics": reconciliation["metrics"],
        "classification_count": len(reconciliation["classifications"]),
        "echo_lines": reconciliation["echo_lines"][:MAX_ECHO_LINES],
        "echo_line_total": len(reconciliation["echo_lines"]),
        "unmatched_orders": [
            row["order_code"]
            for row in reconciliation["classifications"]
            if row["outcome"] == "unmatched"
        ],
        "ledger": append_result,
        "archive_dir": str(archive_dir),
    }


def _dataset_order_codes(dataset_path: Optional[str]) -> set[str] | None:
    if not dataset_path:
        return None
    path = resolve_agent_path(dataset_path)
    if not path.is_file():
        return None
    dataset = json.loads(path.read_text(encoding="utf-8"))
    codes = {
        str(order.get("working_order_code") or order.get("WORKINGORDERCODE") or "").strip()
        for order in dataset.get("orders", [])
        if isinstance(order, dict)
    }
    return codes - {""} or None


def _reconcile_summary(result: Dict[str, Any]) -> str:
    metrics = result["metrics"]
    counts = metrics["counts"]
    ledger = result["ledger"]
    dedup = "（重复提交，已去重跳过）" if ledger["deduplicated"] else ""
    unmatched = result["unmatched_orders"]
    unmatched_text = (
        f"注意：{len(unmatched)} 个工单号不在当期数据集：{'、'.join(unmatched[:5])}。"
        if unmatched
        else ""
    )
    return (
        f"清单对账完成{dedup}：确认 {counts['confirmed']}、漏报 {counts['missed']}、"
        f"误报 {counts['rejected']}、默许 {counts['tacit_confirmed']}、期外 {counts['unmatched']}。"
        f"{metrics['identification_rate']['text']}；{metrics['error_rate']['text']}。"
        f"{unmatched_text}台账落账 {ledger['appended']} 条，归档 {result['archive_dir']}。"
    )


def _stats_sync(month: Optional[str], enable_db_recheck: bool) -> Dict[str, Any]:
    from app.services.ops_audit import feedback_ledger
    from app.services.ops_audit.retrospective_stats import (
        build_retrospective_stats,
        run_db_recheck,
    )

    stats = build_retrospective_stats(month=month)
    month_key = stats["month"]
    recheck: Dict[str, Any] | None = None
    if enable_db_recheck:
        records = feedback_ledger.read_records()
        recheck = run_db_recheck(
            records,
            month=month_key,
            output_dir=get_memory_dir() / "ops" / "audit" / "recheck",
        )
        _append_recheck_ledger(recheck)
    archive_dir = get_memory_dir() / "ops" / "audit" / "retrospective"
    archive_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(stats)
    if recheck is not None:
        payload["db_recheck"] = {
            key: recheck[key]
            for key in ("month", "eligible_count", "counts", "archive_path")
            if key in recheck
        }
    archive_path = archive_dir / f"stats_{month_key}.json"
    archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    feedback_ledger.append_metrics_history(
        {
            "kind": "monthly_retrospective",
            "month": month_key,
            "checklist_metrics": stats["checklist_metrics"],
            "panel_metrics": stats["panel_metrics"],
        }
    )
    return {**payload, "archive_path": str(archive_path)}


def _append_recheck_ledger(recheck: Dict[str, Any]) -> None:
    from app.services.ops_audit import feedback_ledger

    records = recheck.get("ledger_records") or []
    if not records:
        return
    feedback_id = str(records[0].get("feedback_id") or "")
    already = [
        record
        for record in feedback_ledger.read_records()
        if record.get("feedback_id") == feedback_id
    ]
    if already:
        recheck["ledger"] = {"appended": 0, "deduplicated": True, "existing_count": len(already)}
        return
    written = feedback_ledger.append_records(records)
    recheck["ledger"] = {"appended": len(written), "deduplicated": False}


def _stats_summary(result: Dict[str, Any]) -> str:
    checklist = result["checklist_metrics"]
    panel = result["panel_metrics"]
    recheck = result.get("db_recheck")
    recheck_text = ""
    if isinstance(recheck, dict):
        counts = recheck.get("counts") or {}
        recheck_text = (
            f"回库分诊 {recheck.get('eligible_count', 0)} 条："
            + "、".join(f"{key} {value}" for key, value in sorted(counts.items()))
            + "。"
            if counts
            else f"回库分诊：无 eligible rejected 记录。"
        )
    top_rules = result["by_rule"][:3]
    rule_text = (
        "高推翻规则：" + "、".join(f"{row['rule_id']} {row['overturn_text']}" for row in top_rules)
        if top_rules
        else "本月无按规则的显式判定记录。"
    )
    return (
        f"{result['month']} 复盘统计：台账 {result['record_count']} 条。"
        f"{checklist['identification_rate']['text']}；{checklist['error_rate']['text']}；"
        f"{panel['panel_confirm_rate']['text']}；{panel['panel_exclude_rate']['text']}。"
        f"候选新规则信号 {result['candidate_new_rules']['missed_without_rule_count']} 条。"
        f"{rule_text}{recheck_text}统计归档 {result['archive_path']}。"
    )


__all__ = ["OpsAuditReconcileChecklistTool", "OpsAuditRetrospectiveStatsTool"]
