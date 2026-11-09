"""工单表单数据在位性护栏规则。

背景（2026-10-26 组分站周审核复盘）：取数只覆盖部分表单载体时，无表单工单
对所有表单类规则零命中，最终报告呈现为"零问题"，结论证据不足。本规则把
"整单没有任何RF表单数据"本身作为待确认问题输出，使数据覆盖缺口在审核
结果中可见，而不是被静默当作审核通过。

范围收敛（2026-11-09 组分站误报复盘）：未闭环工单（Doing/Wait）本就是
"表单尚未提交"的常态，对其判"无表单"属于把正常在办工单算成问题。实测
组分站一个窗口内 74 条命中里 48 条是 Doing 单，占 65%。本规则改为只对
已闭环工单（Finish）输出，并在证据里带上工单状态便于人工分层核实。
"""

from __future__ import annotations

from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

FORM_DATA_MISSING_RULE_ID = "FORM_DATA_MISSING"

# 只有已闭环工单才要求表单在位；未闭环（Doing/Wait）允许表单尚未提交。
FORM_COMPLETED_STATUSES = frozenset({"finish", "finished", "complete", "completed"})


def check_form_data_missing(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """已闭环工单未关联到任何RF表单数据时输出护栏问题（每单至多一条）。"""

    if forms:
        return
    status = str(order.get("DDWORKINGORDERSTATUS") or "").strip()
    if status.lower() not in FORM_COMPLETED_STATUSES:
        return
    code = order.get("WORKINGORDERCODE")
    add_issue(
        issues,
        FORM_DATA_MISSING_RULE_ID,
        "完整性问题",
        "中",
        "RF_FORMS",
        "已闭环工单无任何RF表单数据，表单类规则无法审核，需核实是漏填报还是表单数据未同步/未纳入取数",
        (
            f"working_order_code={code}; "
            f"order_status={status or 'unknown'}; "
            "rf_forms=0; 表单在位性检查未在数据集中发现该工单的任何RF表单记录，"
            "本轮全部表单字段/数值/附件对应规则对该单不生效。"
        ),
    )

