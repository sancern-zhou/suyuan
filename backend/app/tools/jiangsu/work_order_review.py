"""Agent hand-off tools for Jiangsu fault work-order reviews."""

from __future__ import annotations

from typing import Any

import structlog

from app.services.jiangsu_work_order_review import (
    create_review_visual,
    resources_for_review,
    submit_agent_review,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


def _exclusion_interval_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "data_impact_index": {
                    "type": "integer",
                    "description": "对应的 data_impact 数组下标（从 0 起）；剔除区间的污染物、粒度和起止时间以该条 data_impact 为准，不重复填写。",
                },
                "boundary_sources": {"type": "array", "items": {"type": "string"}},
                "reasonableness_check": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["pass", "uncertain", "fail"]},
                        "basis": {"type": "string"},
                    },
                    "required": ["status", "basis"],
                },
            },
            "required": ["data_impact_index", "boundary_sources", "reasonableness_check"],
        },
        "description": "涉及剔除时必填；通过 data_impact_index 引用 data_impact 条目并补充边界来源与合理性判断。",
    }


def _gate_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pass", "fail", "uncertain", "not_applicable"],
            },
            "basis": {"type": "string"},
            "missing_evidence": {"type": "array", "items": {"type": "string"}},
            "scope": {
                "type": "string",
                "enum": ["core", "supporting", "rebuttal"],
                "description": "门禁层级；core 为核心闭环，supporting 为辅助证据，rebuttal 为反证。",
            },
        },
        "required": ["status"],
    }


def _review_schema(*, tool_name: str, description: str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "event_id": {"type": "string", "description": "触发审核任务的事件 ID。"},
        "sop_id": {
            "type": "string",
            "enum": ["SOP-01", "SOP-02", "SOP-03"],
            "description": "审核 SOP 编号；SOP-01 为质控/校准，SOP-02 为监测数据与采样、供电、站房环境异常，SOP-03 为数据传输、平台离线与数据缺失。",
        },
        "evidence_pack_path": {"type": "string", "description": "已读取的审核证据包路径。"},
        "work_order_code": {"type": "string", "description": "完整故障工单号。"},
        "station": {"type": "object", "description": "站点对象，至少包含 station_code/station_name。"},
        "device_id": {"type": "string", "description": "设备 ID；未知时可不填。"},
        "device_type": {"type": "string"},
        "pollutants": {"type": "array", "items": {"type": "string"}},
        "qc_event_type": {"type": "string"},
        "transmission_status": {
            "type": "string",
            "description": "SOP-03 数据传输状态，例如 offline/not_uploaded/retransmitted/timestamp_error/missing/uncertain。",
        },
        "event_type": {
            "type": "string",
            "enum": [
                "high",
                "low",
                "zero",
                "constant",
                "missing",
                "flow",
                "power",
                "temperature",
                "offline",
                "not_uploaded",
                "retransmitted",
                "timestamp_error",
                "uncertain",
            ],
            "description": "SOP-02 异常表现或 SOP-03 传输缺失表现；SOP-01 可留空。",
        },
        "failure_fact": {"type": "object"},
        "disposal": {"type": "object"},
        "recovery": {"type": "object"},
        "retest": {"type": "object"},
        "transmission": {"type": "object"},
        "gates": {
            "type": "object",
            "description": (
                "SOP-01 填 M1-M6（M3 核验处置与附件证据对应关系）；SOP-02 填 E1-E8（E5/E6 分别核验处置、恢复及其附件证据）；SOP-03 填 T1-T7（T5/T6 核验补传、时间戳及其证据）。每项建议 {status, basis, missing_evidence, scope}，"
                "其中 scope 可选 core/supporting/rebuttal。core 表示核心闭环门禁，"
                "supporting 表示辅助证据，rebuttal 表示反证线索。"
            ),
            "additionalProperties": _gate_item_schema(),
        },
        "data_impact": {
            "type": "array",
            "items": {"type": "object", "properties": {"granularity": {"type": "string", "enum": ["hour"]}}, "required": ["granularity"]},
            "description": (
                "数据影响结论数组；decision 可为 keep/partial_exclude/exclude/"
                "missing_no_delete/not_applicable/needs_evidence；提出 partial_exclude 或 exclude 时"
                "对应条目必须填写明确 pollutant、granularity、start、end。granularity 只能是 hour；"
                "仅审核小时数据有效性及剔除时段，5分钟数据仅作参考，不生成分钟级处置。"
            ),
        },
        "flag_boundary": {"type": "object"},
        "neighbor_comparison": {
            "type": "string",
            "description": "SOP-02 填同步/不同步/未查询及依据摘要。",
        },
        "exclusion_intervals": _exclusion_interval_schema(),
        "work_order_decision": {
            "type": "string",
            "enum": ["approve", "reject", "needs_evidence"],
            "description": (
                "工单审核结论。核心证据闭环时应给 approve；只有核心材料缺失、关键冲突或边界不明且"
                "无法由其他核心证据补足时才给 needs_evidence。非实质性工单措辞瑕疵不得单独触发退回。"
            ),
        },
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "review_comment": {
            "type": "string",
            "description": "详细审核意见。开头先给核心结论，后续再列必要依据和缺口。",
        },
        "review_summary": {
            "type": "string",
            "description": "一句话用户摘要，收敛为审核结论、数据处置和核心原因，不罗列门禁编号。",
        },
    }
    required = ["sop_id", "work_order_code", "work_order_decision", "gates", "data_impact", "review_comment"]
    return {
        "name": tool_name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


class JiangsuFaultWorkOrderReviewSubmitTool(LLMTool):
    """Persist a SOP review and publish a right-panel confirmation card."""

    source_name = "agent_fault_work_order_review"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_submit_fault_work_order_review",
            description=(
                "提交江苏故障工单 SOP 审核结论，支持 SOP-01、SOP-02 与 SOP-03，生成右侧人工确认归档卡片。"
                "涉及数据剔除时必须填写剔除污染物、异常起止时间、边界来源和合理性判断。"
            ),
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema=_review_schema(
                tool_name="jiangsu_submit_fault_work_order_review",
                description=(
                    "保存一张故障工单的 AI 审核结论并生成右侧确认卡片。"
                    "SOP-02 必须区分有效异常、伪值、缺失和暂时不可见；SOP-03 必须区分未产生、未上传、暂时不可见和补传完整性。"
                    "没有明确异常时间段时不得给 partial_exclude 或 exclude。"
                ),
            ),
        )

    async def execute(self, context=None, **kwargs: Any) -> dict[str, Any]:
        try:
            payload = dict(kwargs)
            review = submit_agent_review(payload)
            visual = create_review_visual(review)
            sop_id = str(review["sop_id"]).strip().upper()
            if sop_id == "SOP-03":
                label = "传输缺失类故障工单"
            elif sop_id == "SOP-02":
                label = "数据异常类故障工单"
            else:
                label = "质控类故障工单"
            return {
                "status": "pending_review",
                "success": True,
                "data": {
                    "review_id": review["review_id"],
                    "sop_id": sop_id,
                    "work_order_code": review["work_order_code"],
                    "work_order_decision": review["work_order_decision"],
                    "exclusion_required": review["exclusion_required"],
                    "requires_human_exclusion_confirmation": review[
                        "requires_human_exclusion_confirmation"
                    ],
                    "audit_warnings": review.get("audit_warnings", []),
                },
                "visuals": [visual],
                "resources": resources_for_review(review, tool_name=self.name),
                "metadata": {
                    "source": self.source_name,
                    "visual_behavior": "fault_work_order_review",
                    "review_id": review["review_id"],
                    "sop_id": sop_id,
                },
                "summary": (
                    f"{sop_id} {label} {review['work_order_code']} 的 AI 审核结论已生成，"
                    "右侧面板等待人工确认归档。"
                    + ("涉及数据剔除，请重点核对异常时间段和合理性。" if review["exclusion_required"] else "")
                ),
            }
        except ValueError as exc:
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "summary": f"故障工单审核结论提交失败：{exc}",
            }
        except Exception as exc:
            logger.warning("jiangsu_work_order_review_submit_failed", tool=self.name, error=str(exc))
            return {
                "status": "failed",
                "success": False,
                "data": {},
                "summary": "故障工单审核结论提交发生未预期错误。",
            }
