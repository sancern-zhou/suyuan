"""工单表单数据在位性护栏规则。

背景（2026-10-26 组分站周审核复盘）：取数只覆盖部分表单载体时，无表单工单
对所有表单类规则零命中，最终报告呈现为"零问题"，结论证据不足。本规则把
"整单没有任何RF表单数据"本身作为待确认问题输出，使数据覆盖缺口在审核
结果中可见，而不是被静默当作审核通过。
"""

from __future__ import annotations

from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

FORM_DATA_MISSING_RULE_ID = "FORM_DATA_MISSING"


def check_form_data_missing(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """工单未关联到任何RF表单数据时输出护栏问题（每单至多一条）。"""

    if forms:
        return
    code = order.get("WORKINGORDERCODE")
    add_issue(
        issues,
        FORM_DATA_MISSING_RULE_ID,
        "完整性问题",
        "中",
        "RF_FORMS",
        "工单无任何RF表单数据，表单类规则无法审核，需核实是漏填报还是表单数据未同步/未纳入取数",
        (
            f"working_order_code={code}; "
            "rf_forms=0; 表单在位性检查未在数据集中发现该工单的任何RF表单记录，"
            "本轮全部表单字段/数值/附件对应规则对该单不生效。"
        ),
    )
