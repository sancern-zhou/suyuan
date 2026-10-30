"""组分站表单档案驱动规则单测（审核二期）。

覆盖 SUP_FORMULA_RECALC / SUP_RANGE_OUT_OF_SPEC / SUP_REQUIRED_VALUE_EMPTY /
SUP_DATE_REASONABLENESS / SUP_CYCLE_TIMELINESS 的命中与豁免路径，
案例背景见 projects/guangdong/docs/sup-audit-cases/。
"""

import json
from datetime import date

import pytest

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.sup_form_rules import (
    DATE_RULE_ID,
    FORMULA_RULE_ID,
    RANGE_RULE_ID,
    REQUIRED_RULE_ID,
    TIMELINESS_RULE_ID,
    extract_date_from_filename,
    check_sup_form_rules,
)


def _run(form, order=None, wo_commonfiles=None, sup_taskitems=None):
    issues: list[Issue] = []
    check_sup_form_rules(
        order or {"WORKINGORDERCODE": "CH_TEST", "CREATETIME": "2026-09-04 10:00:00"},
        [("SUP_RF_COMMON", form)],
        issues,
        wo_commonfiles or [],
        sup_taskitems or [],
    )
    return issues


def _rule_ids(issues):
    return {issue.rule_id for issue in issues}


# ---------------------------------------------------------------------------
# SUP_FORMULA_RECALC（PANs 设定误差，案例：潮州西园路 CH2609041788520167552）
# ---------------------------------------------------------------------------


def _pans_form(**overrides):
    form = {
        "RULEITEMTAG": "Sup_RF_PANsFlowCheck",
        "POLLUTANTTYPE": "PANs",
        "CHECKDATE": "2026-09-04 00:00:00",
        "string13": "992.13",
        "string14": "1063",
        "string16": "7.14%",
        "string17": "4.04",
        "string18": "5.16",
        "string20": "27.72%",
        "string21": "19.80",
        "string22": "22.23",
        "string24": "12.27%",
    }
    form.update(overrides)
    return form


def test_formula_recalc_hits_miscalculated_pans_error():
    issues = _run(_pans_form(string16="1.88%", string20="0.5%", string24="-1.84"))

    matched = [issue for issue in issues if issue.rule_id == FORMULA_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    columns = {item["column"] for item in evidence["violations"]}
    assert columns == {"string16", "string20", "string24"}
    assert matched[0].severity == "高"


def test_formula_recalc_passes_within_tolerance():
    issues = _run(_pans_form(string20="27.5%"))

    assert FORMULA_RULE_ID not in _rule_ids(issues)


def test_formula_recalc_skips_when_inputs_missing():
    issues = _run(_pans_form(string18=None, string20="0.5%"))

    evidence = [json.loads(issue.evidence) for issue in issues if issue.rule_id == FORMULA_RULE_ID]
    assert all(
        "string20" not in {item["column"] for item in item["violations"]} for item in evidence
    )


def test_formula_recalc_ignores_non_sup_form():
    form = {"string13": "1", "string14": "2", "string16": "999%"}
    issues = _run(form)

    assert issues == []


# ---------------------------------------------------------------------------
# SUP_RANGE_OUT_OF_SPEC（OCEC 升温程序温度偏差 ±10%，案例：清远技师学院）
# ---------------------------------------------------------------------------


def _ocec_form(**overrides):
    form = {
        "RULEITEMTAG": "Sup_RF_OCECJGWeekCheck",
        "POLLUTANTTYPE": "OCEC",
        "CHECKDATE": "2026-09-30 00:00:00",
        "string33": "851.3",
        "string35": "850.2",
        "string42": "0.15%",
        "string43": "加热温度会上下浮动",
        "string44": "0.02%",
    }
    form.update(overrides)
    return form


def test_range_without_remark_hits_high():
    issues = _run(_ocec_form(string42="851.3", string43=None))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    assert "超出标准范围" in matched[0].message


def test_range_with_remark_downgrades_to_manual_review():
    issues = _run(_ocec_form(string42="851.3", string43="加热温度会上下浮动"))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    evidence = json.loads(matched[0].evidence)
    assert evidence["with_remark"] is True
    assert evidence["needs_semantic_review"] is True


def test_range_in_spec_passes():
    issues = _run(_ocec_form())

    assert RANGE_RULE_ID not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# SUP_REQUIRED_VALUE_EMPTY（OCEC 升温程序数值空白，案例：韶关市八中）
# ---------------------------------------------------------------------------


def test_required_value_blank_hits_high():
    issues = _run(_ocec_form(string33=None, string35=None))

    matched = [issue for issue in issues if issue.rule_id == REQUIRED_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    evidence = json.loads(matched[0].evidence)
    assert {item["column"] for item in evidence["items"]} == {"string33", "string35"}


def test_required_value_slash_without_remark_flags_review():
    issues = _run(_ocec_form(string44="/"))

    matched = [issue for issue in issues if issue.rule_id == REQUIRED_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"


def test_required_value_slash_with_remark_is_exempt():
    issues = _run(_ocec_form(string44="/", string45="内标阶段为降温，无升温程序"))

    assert REQUIRED_RULE_ID not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# SUP_DATE_REASONABLENESS（案例：惠州下埔动态校准仪 56 天、东莞东城甲醛标液有效期）
# ---------------------------------------------------------------------------


def test_date_pair_interval_not_standard_hits():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-07 00:00:00",
        "time1": "2026-01-28 00:00:00",
        "time2": "2027-01-27 00:00:00",
        "time3": "2026-08-11 00:00:00",
        "time4": "2026-10-06 00:00:00",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    kinds = {item["kind"] for item in evidence["violations"]}
    assert kinds == {"interval_not_standard"}


def test_date_pair_expired_before_checkdate_hits():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_HONOCheck",
        "POLLUTANTTYPE": "HONO",
        "CHECKDATE": "2026-07-01 00:00:00",
        "time1": "2026-05-01 00:00:00",
        "time2": "2026-05-31 00:00:00",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    # 5/1→5/31 为 30 天标准周期，仅"有效期早于检查日期"命中。
    assert {item["kind"] for item in evidence["violations"]} == {"expired_before_checkdate"}


def test_date_pair_equal_dates_placeholder_skipped():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_HONOCheck",
        "POLLUTANTTYPE": "HONO",
        "CHECKDATE": "2026-07-01 00:00:00",
        "time1": "2026-07-01 00:00:00",
        "time2": "2026-07-01 00:00:00",
    }
    issues = _run(form)

    assert DATE_RULE_ID not in _rule_ids(issues)


def test_date_pair_standard_interval_passes():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-07 00:00:00",
        "time1": "2026-01-28 00:00:00",
        "time2": "2027-01-27 00:00:00",
        "time3": "2026-08-11 00:00:00",
        "time4": "2026-09-10 00:00:00",
    }
    issues = _run(form)

    assert DATE_RULE_ID not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# SUP_CYCLE_TIMELINESS（表单侧口径；案例：惠州江北 8/30 数据 9/7 上传）
# ---------------------------------------------------------------------------


def test_timeliness_stale_data_file_hits():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-07 00:00:00",
    }
    files = [
        {
            "TYPECODE": "Sup_RF_Week_NMHCQC_NMHC",
            "FILENAME": "2026年8月30日甲烷非甲烷分析仪质控检查.xlsx",
        }
    ]
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-09-07 10:30:01"}, wo_commonfiles=files)

    matched = [issue for issue in issues if issue.rule_id == TIMELINESS_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["violations"][0]["kind"] == "stale_data_file"
    assert evidence["violations"][0]["stale_days"] == 8


def test_timeliness_fill_lag_hits_for_quarter_form():
    form = {
        "RULEITEMTAG": "Sup_RF_HY_NMHCMaintenanceRecord",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-08-01 00:00:00",
    }
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-09-20 10:00:00"})

    matched = [issue for issue in issues if issue.rule_id == TIMELINESS_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["violations"][0]["kind"] == "fill_lag"


def test_timeliness_plan_overdue_hits_when_creation_exceeds_grace():
    """计划口径：质控计划完成日 8/5，工单 8/15 才创建（超宽限 5 天）→ 命中。"""

    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-08-05 00:00:00",
    }
    taskitems = [
        {"WORKINGORDERCODE": "CH_T", "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
         "POLLUTANTTYPE": "NMHC", "PLANFINISHTIME": "2026-08-05 00:00:00",
         "FINISHTIME": None, "STATUS": 1},
    ]
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-08-15 10:00:00"}, wo_commonfiles=[], sup_taskitems=taskitems)

    matched = [issue for issue in issues if issue.rule_id == TIMELINESS_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["violations"][0]["kind"] == "plan_overdue"
    assert "计划口径" in evidence["口径"]


def test_timeliness_plan_anchor_replaces_form_side_lag():
    """有计划任务项时计划口径优先：创建仅晚计划 2 天（宽限内）不命中，即使按表单口径滞后更大。"""

    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-08-02 00:00:00",
    }
    taskitems = [
        {"WORKINGORDERCODE": "CH_T", "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
         "POLLUTANTTYPE": "NMHC", "PLANFINISHTIME": "2026-08-05 00:00:00",
         "FINISHTIME": None, "STATUS": 1},
    ]
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-08-07 10:00:00"}, sup_taskitems=taskitems)

    assert TIMELINESS_RULE_ID not in _rule_ids(issues)


def test_timeliness_falls_back_to_form_side_without_taskitems():
    """无计划任务项时维持表单侧口径（回归保护）。"""

    form = {
        "RULEITEMTAG": "Sup_RF_HY_NMHCMaintenanceRecord",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-08-01 00:00:00",
    }
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-09-20 10:00:00"}, sup_taskitems=[])

    evidence = json.loads(
        [i for i in issues if i.rule_id == TIMELINESS_RULE_ID][0].evidence
    )
    assert "表单侧口径" in evidence["口径"]


def test_timeliness_passes_fresh_weekly_data():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-28 00:00:00",
    }
    files = [
        {"TYPECODE": "Sup_RF_Week_NMHCQC_NMHC", "FILENAME": "NMHC监测仪零气空白等质控数据-9月23日.xlsx"},
        {"TYPECODE": "Sup_RF_Week_NMHCQC_NMHC", "FILENAME": "单点.jpg"},
    ]
    issues = _run(form, order={"WORKINGORDERCODE": "CH_T", "CREATETIME": "2026-09-28 10:46:50"}, wo_commonfiles=files)

    assert TIMELINESS_RULE_ID not in _rule_ids(issues)


def test_extract_date_from_filename_variants():
    assert extract_date_from_filename("2026年8月30日甲烷质控.xlsx") == date(2026, 8, 30)
    assert extract_date_from_filename("质控数据-9月23日.xlsx", default_year=2026) == date(2026, 9, 23)
    assert extract_date_from_filename("PTR-MS质控数据20260825.xlsx") == date(2026, 8, 25)
    # 区间文件名取区间末（周期覆盖至 10-18，对 10-20 检查日不算过期）。
    assert extract_date_from_filename("梅华_VOCs_2026-10-12至2026-10-18_周质控.xlsx") == date(2026, 10, 18)
    assert extract_date_from_filename("无日期.xlsx") is None


@pytest.mark.parametrize(
    "form",
    [
        {"string16": "1.88%"},
        {"RULEITEMTAG": "Sup_RF_UnknownType", "string16": "999%"},
    ],
)
def test_rules_skip_unprofiled_forms(form):
    assert _run(form) == []


# ---------------------------------------------------------------------------
# 通用表单族（2026-10-27 tag 盘点建档）：流量核查 / 温压核查 / 单日期 not_past /
# 异常勾选未备注。数据依据 docs/sup-instrument-rules/tag-inventory.md。
# ---------------------------------------------------------------------------


def _flow_check_form(**overrides):
    form = {
        "RULEITEMTAG": "Sup_RF_DeviceFlowCheck",
        "CHECKDATE": "2026-10-27 00:00:00",
        "calibratedateprev1": "2026-02-03 00:00:00",
        "calibratedatenext1": "2027-02-02 00:00:00",
        "slope1": "1.00986",
        "intercept1": "-0.01640",
        "targetvalue1": "16.67",
        "displayvalue1": "16.546",
        "correctionvalue1": "16.69",
        "error1": "0.12",
        "indicationerror1": "-0.12",
        # 未执行校准的"校准后"行按 0 占位。
        "targetvalue2": "0",
        "displayvalue2": "0",
        "correctionvalue2": "0",
        "error2": "0",
        "indicationerror2": "0",
    }
    form.update(overrides)
    return form


def test_flow_check_recalc_and_zero_placeholder_pass():
    issues = _run(_flow_check_form())

    assert issues == []


def test_flow_check_recalc_hits_wrong_correction():
    issues = _run(_flow_check_form(correctionvalue1="16.80"))

    matched = [issue for issue in issues if issue.rule_id == FORMULA_RULE_ID]
    assert matched, "修正值偏离复算值应命中"
    assert matched[0].severity == "高"


def test_flow_check_zero_placeholder_skips_recalc():
    issues = _run(_flow_check_form())

    formula_columns = {
        item["column"]
        for issue in issues
        if issue.rule_id == FORMULA_RULE_ID
        for item in json.loads(issue.evidence)["violations"]
    }
    assert "correctionvalue2" not in formula_columns
    assert "error2" not in formula_columns


def test_flow_check_relative_error_out_of_range_hits():
    issues = _run(_flow_check_form(error1="7.6"))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"


def test_flow_check_indication_error_out_of_range_hits():
    issues = _run(_flow_check_form(indicationerror1="-2.91", error1="0.12"))

    assert RANGE_RULE_ID in _rule_ids(issues)


def test_flow_check_certificate_expired_hits():
    issues = _run(_flow_check_form(calibratedatenext1="2026-09-05 00:00:00"))

    matched = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert matched
    assert any("有效期" in issue.message for issue in matched)


def test_flow_check_prev_calibration_date_not_future_hits():
    issues = _run(_flow_check_form(calibratedateprev1="2026-12-03 00:00:00"))

    matched = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert matched
    assert any("晚于检查日期" in issue.message for issue in matched)


def _ambient_form(**overrides):
    form = {
        "RULEITEMTAG": "Sup_RF_AmbientTemperature",
        "CHECKDATE": "2026-10-27 00:00:00",
        "t_r_standard": "33.8",
        "t_r_prevvalue": "33.3",
        "t_r_nextvalue": "33.3",
        "p_r_standard": "101.21",
        "p_r_prevvalue": "101.14",
        "p_r_nextvalue": "101.14",
        "t_prevdate": "2026-04-27 00:00:00",
        "t_nextdate": "2027-04-26 00:00:00",
        "p_prevdate": "2026-04-27 00:00:00",
        "p_nextdate": "2027-04-26 00:00:00",
    }
    form.update(overrides)
    return form


def test_ambient_expression_range_passes_within_limits():
    issues = _run(_ambient_form())

    assert RANGE_RULE_ID not in _rule_ids(issues)


def test_ambient_expression_range_epsilon_boundary_passes():
    # 33.8-31.8 在浮点上等于 -2.0000000000000004，取整后应视为贴边合格。
    issues = _run(_ambient_form(t_r_prevvalue="31.8"))

    assert RANGE_RULE_ID not in _rule_ids(issues)


def test_ambient_expression_range_without_remark_hits_high():
    issues = _run(_ambient_form(t_r_prevvalue="35.9"))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"


def test_ambient_expression_range_with_remark_downgrades():
    issues = _run(_ambient_form(t_r_prevvalue="35.9", REMARK="温度偏高，已校准"))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"


def test_date_single_not_past_hits(monkeypatch):
    from app.services.ops_audit.rules import sup_form_rules as sfr

    profile = {
        "display_name": "测试单日期",
        "date_columns": [
            {"start": "cert_next_date", "label": "证书有效期", "single_date_rule": "not_past"},
        ],
    }
    monkeypatch.setitem(
        sfr.SUP_FORM_PROFILES["form_profiles"], "Sup_RF_NotPastTest", profile
    )
    form = {
        "RULEITEMTAG": "Sup_RF_NotPastTest",
        "CHECKDATE": "2026-10-27 00:00:00",
        "cert_next_date": "2026-09-01 00:00:00",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert len(matched) == 1
    assert "早于检查日期" in matched[0].message


def test_date_single_not_past_passes(monkeypatch):
    from app.services.ops_audit.rules import sup_form_rules as sfr

    profile = {
        "display_name": "测试单日期",
        "date_columns": [
            {"start": "cert_next_date", "label": "证书有效期", "single_date_rule": "not_past"},
        ],
    }
    monkeypatch.setitem(
        sfr.SUP_FORM_PROFILES["form_profiles"], "Sup_RF_NotPastTest", profile
    )
    form = {
        "RULEITEMTAG": "Sup_RF_NotPastTest",
        "CHECKDATE": "2026-10-27 00:00:00",
        "cert_next_date": "2027-09-01 00:00:00",
    }
    issues = _run(form)

    assert issues == []


def _abnormal_profile():
    return {
        "display_name": "测试异常勾选",
        "abnormal_columns": [
            {"column": "status", "values": ["异常", "不合格"], "label": "仪器状态"},
        ],
    }


def test_abnormal_without_remark_hits(monkeypatch):
    from app.services.ops_audit.rules import sup_form_rules as sfr
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    monkeypatch.setitem(
        sfr.SUP_FORM_PROFILES["form_profiles"], "Sup_RF_AbnormalTest", _abnormal_profile()
    )
    form = {
        "RULEITEMTAG": "Sup_RF_AbnormalTest",
        "CHECKDATE": "2026-10-27 00:00:00",
        "status": "异常",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    assert "未填写异常情况说明" in matched[0].message


def test_abnormal_with_remark_exempt(monkeypatch):
    from app.services.ops_audit.rules import sup_form_rules as sfr
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    monkeypatch.setitem(
        sfr.SUP_FORM_PROFILES["form_profiles"], "Sup_RF_AbnormalTest", _abnormal_profile()
    )
    form = {
        "RULEITEMTAG": "Sup_RF_AbnormalTest",
        "CHECKDATE": "2026-10-27 00:00:00",
        "status": "异常",
        "REMARK": "已更换滤膜并恢复正常",
    }
    issues = _run(form)

    assert ABNORMAL_RULE_ID not in _rule_ids(issues)


def test_abnormal_normal_value_passes(monkeypatch):
    from app.services.ops_audit.rules import sup_form_rules as sfr
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    monkeypatch.setitem(
        sfr.SUP_FORM_PROFILES["form_profiles"], "Sup_RF_AbnormalTest", _abnormal_profile()
    )
    form = {
        "RULEITEMTAG": "Sup_RF_AbnormalTest",
        "CHECKDATE": "2026-10-27 00:00:00",
        "status": "正常",
    }
    issues = _run(form)

    assert issues == []
