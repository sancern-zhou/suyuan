"""组分站审核误报护栏单测（2026-11-09 组分站误报复盘）。

背景：组分站周审核报告里 287 条问题中 232 条（81%）来自两个结构性误报：

1. 主网规则 RF_ENV_TEMP_HUMIDITY_EMPTY 无表范围限制，命中 sup_rf_* 分表里
   与主网同名的 temperature/humidity 列。这些列在源库是恒空列（全量 NULL），
   规则因此 100% 命中（一个窗口内 2931 行全空），属于列名撞车而非业务问题。
2. FORM_DATA_MISSING 对未闭环工单（Doing/Wait）也判"无表单"，但这些工单
   本就允许表单尚未提交；一个窗口内 74 条命中里 48 条（65%）是 Doing 单。

本文件锁住两处行为，防止回退。
"""

from __future__ import annotations

import json

from app.services.ops_audit.rules.form_presence_rules import (
    FORM_DATA_MISSING_RULE_ID,
    check_form_data_missing,
)
from app.services.ops_audit.rules.rf_required_rules import check_rf_required_fields


def _env_temp_issues(form, table):
    issues = []
    check_rf_required_fields({"WORKINGORDERCODE": "CH_TEST"}, [(table, form)], issues)
    return [issue for issue in issues if issue.rule_id == "RF_ENV_TEMP_HUMIDITY_EMPTY"]


def test_sup_sub_table_still_flagged_on_main_net():
    """主网表单同名列恒空时仍应命中（确认规则本身未被削掉）。"""

    issues = _env_temp_issues(
        {"WORKINGORDERCODE": "CH_TEST", "TEMPERATURE": None, "HUMIDITY": None, "REMARK": ""},
        "RF_HY_ENVIRONMENTHUMIDITY",
    )
    assert len(issues) == 2
    dimensions = {json.loads(issue.evidence)["missing_dimension"] for issue in issues}
    assert dimensions == {"temperature", "humidity"}


def test_sup_rf_sub_table_skips_main_net_temp_humidity_rule():
    """组分站专用分表的同名列恒空（源库全量 NULL），不应被主网规则判为问题。"""

    for table in (
        "SUP_RF_PM1MONITORINSPECTION",
        "SUP_RF_MONITORINSPECTION",
        "SUP_RF_DEVICEFLOWCHECK",
    ):
        issues = _env_temp_issues(
            {"WORKINGORDERCODE": "CH_TEST", "temperature": None, "humidity": None},
            table,
        )
        assert issues == [], f"{table} 被主网温湿度规则误命中"


def test_sup_rf_common_skips_main_net_temp_humidity_rule():
    """sup_rf_common 的列语义按 ruleitemtag 建档，不走主网字段档案。"""

    issues = _env_temp_issues(
        {"WORKINGORDERCODE": "CH_TEST", "temperature": None, "humidity": None},
        "SUP_RF_COMMON",
    )
    assert issues == []


def _form_missing_issues(order, forms=None):
    issues = []
    check_form_data_missing(order, forms or [], issues)
    return [issue for issue in issues if issue.rule_id == FORM_DATA_MISSING_RULE_ID]


def test_form_data_missing_skips_unclosed_doing_order():
    """未闭环工单允许表单未提交，不应判"无表单"。"""

    issues = _form_missing_issues(
        {"WORKINGORDERCODE": "CH_DOING", "DDWORKINGORDERSTATUS": "Doing"}
    )
    assert issues == []


def test_form_data_missing_skips_unclosed_wait_order():
    issues = _form_missing_issues(
        {"WORKINGORDERCODE": "CH_WAIT", "DDWORKINGORDERSTATUS": "Wait"}
    )
    assert issues == []


def test_form_data_missing_flags_finished_order_without_forms():
    """已闭环工单无表单仍需护栏提示，属于真实取数/填报缺口。"""

    issues = _form_missing_issues(
        {"WORKINGORDERCODE": "CH_FINISH", "DDWORKINGORDERSTATUS": "Finish"}
    )
    assert len(issues) == 1
    assert "order_status=Finish" in issues[0].evidence


def test_form_data_missing_silent_when_forms_present():
    issues = _form_missing_issues(
        {"WORKINGORDERCODE": "CH_OK", "DDWORKINGORDERSTATUS": "Finish"},
        [("SUP_RF_COMMON", {"WORKINGORDERCODE": "CH_OK"})],
    )
    assert issues == []
