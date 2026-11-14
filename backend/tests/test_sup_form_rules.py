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
    ABNORMAL_RULE_ID,
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


# ---------------------------------------------------------------------------
# PANs 周巡检状态检查参数（Sup_RF_PANsWeekCheck 档案范围/异常勾选）
# ---------------------------------------------------------------------------


def _pans_week_form(**overrides):
    form = {
        "RULEITEMTAG": "Sup_RF_PANsWeekCheck",
        "POLLUTANTTYPE": "PANs",
        "CHECKDATE": "2026-09-03 00:00:00",
        "string18": "Y=8.35E-009X",
        "string19": "0.9992",
        "string20": "12",
        "string22": "50",
        "string24": "18",
        "string26": "24.7",
        "string28": "41.10",
        "string30": "干净",
        "string32": "否",
        "string34": "正常",
        "string36": "检查",
        "string38": "检查",
        "string40": "否",
    }
    form.update(overrides)
    return form


def test_pans_week_status_out_of_range_without_remark_hits_high():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    issues = _run(_pans_week_form(string20="13.2", string26="27"))

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    evidence = json.loads(matched[0].evidence)
    assert {item["column"] for item in evidence["violations"]} == {"string20", "string26"}
    assert matched[0].message.count("超出标准范围") == 1
    assert ABNORMAL_RULE_ID not in _rule_ids(issues)


def test_pans_week_prepressure_with_remark_downgrades_to_review():
    issues = _run(
        _pans_week_form(string24="15", string25="根据该站点仪器性能，柱前压设定值为15kPa")
    )

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    evidence = json.loads(matched[0].evidence)
    assert evidence["with_remark"] is True
    assert evidence["needs_semantic_review"] is True


def test_pans_week_status_in_range_passes():
    issues = _run(_pans_week_form())

    assert issues == []


def test_pans_week_condensation_yes_without_remark_hits():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    issues = _run(_pans_week_form(string32="是"))

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    assert "采样管路是否有冷凝水" in matched[0].message


def test_pans_week_abnormal_with_remark_exempt():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    issues = _run(
        _pans_week_form(string32="是", string33="已现场整改，清理冷凝水", string40="是", string41="正常未调整")
    )

    assert ABNORMAL_RULE_ID not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# 2026-11 扩面：活跃无档案类型建档（列语义来自运维平台源码映射文档）
# ---------------------------------------------------------------------------


NEW_PROFILE_TAGS = [
    "Sup_RF_HP_DalyHealth",
    "Sup_RF_WeekSecurityCheck",
    "Sup_RF_PRInspectionRecord",
    "Sup_RF_HP_StationCheck",
    "Sup_RF_VocsSceneCheck",
    "Sup_RF_MSRoutineCheck",
    "Sup_RF_Month_YT_FlowCalibration",
    "Sup_RF_OCECJGMultipointCheck",
    "Sup_RF_OcecFlowVerificationCheck",
    "Sup_RF_MSQualityCalibration",
    "Sup_RF_MSParticleSizeCalibration",
    "Sup_RF_VocsFlowCheck",
    "Sup_RF_Week_YT_Check",
    "Sup_RF_thybWeekCheck",
    "Sup_RF_Month_HONOCheck",
    "Sup_RF_Month_HONOTest",
    "Sup_RF_PTR_MSQuality",
    "Sup_RF_Week_THLiDAR",
    "Sup_RF_Week_FKXLiDAR",
    "Sup_RF_HONOConsumablesReplace",
    "Sup_RF_OCECWeekCheck",
    "Sup_RF_HP_Comparability",
    "Sup_RF_Year_YT_AccuracyRecord",
    "Sup_RF_Month_THLiDAR",
    "RF_D_GreenHouseCheck",
    "RF_W_GreenHouseCheck",
]


def test_expanded_active_tags_all_profiled():
    from app.services.ops_audit.rules.sup_form_rules import SUP_FORM_PROFILES

    catalog = SUP_FORM_PROFILES["form_profiles"]
    missing = [tag for tag in NEW_PROFILE_TAGS if tag not in catalog]
    assert missing == []


def test_daly_health_out_of_range_hits_high():
    form = {
        "RULEITEMTAG": "Sup_RF_HP_DalyHealth",
        "CHECKDATE": "2026-09-04 00:00:00",
        "string1": "45.0",
        "string2": "50.0",
        "string3": "140",
        "string5": "0.02",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    assert "腔室温度" in matched[0].message


def test_week_security_humidity_and_lightning_date_hit():
    form = {
        "RULEITEMTAG": "Sup_RF_WeekSecurityCheck",
        "CHECKDATE": "2026-09-04 00:00:00",
        "string12": "26",
        "string13": "218",
        "time1": "2025-08-01 00:00:00",
        "bool_1": "0",
        "bool_28": "0",
    }
    issues = _run(form)

    range_hit = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(range_hit) == 1
    assert "站房内部湿度" in range_hit[0].message
    date_hit = [issue for issue in issues if issue.rule_id == DATE_RULE_ID]
    assert len(date_hit) == 1
    assert "防雷检定" in date_hit[0].message
    assert "399" in date_hit[0].message
    # bool 全 0 是该表单数据常态（勾选框未使用），不得判异常。
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    assert ABNORMAL_RULE_ID not in _rule_ids(issues)


def test_week_security_recent_lightning_date_passes():
    form = {
        "RULEITEMTAG": "Sup_RF_WeekSecurityCheck",
        "CHECKDATE": "2026-09-04 00:00:00",
        "string12": "26",
        "string13": "46",
        "time1": "2026-03-06 00:00:00",
    }
    issues = _run(form)

    assert DATE_RULE_ID not in _rule_ids(issues)
    assert RANGE_RULE_ID not in _rule_ids(issues)


def test_pr_inspection_abnormal_bool_without_remark_hits():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    form = {
        "RULEITEMTAG": "Sup_RF_PRInspectionRecord",
        "CHECKDATE": "2026-09-04 00:00:00",
        "bool_1": 0,
        "string1": None,
        "bool_8": 0,
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert "仪器状态" in matched[0].message


def test_pr_inspection_abnormal_bool_with_remark_exempt():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    form = {
        "RULEITEMTAG": "Sup_RF_PRInspectionRecord",
        "CHECKDATE": "2026-09-04 00:00:00",
        "bool_2": 0,
        "string2": "已现场清洁接收头",
    }
    issues = _run(form)

    assert ABNORMAL_RULE_ID not in _rule_ids(issues)


def test_station_check_bool_zero_hits_manual_review():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    form = {
        "RULEITEMTAG": "Sup_RF_HP_StationCheck",
        "CHECKDATE": "2026-09-04 00:00:00",
        **{f"bool_{i}": 1 for i in range(1, 30)},
        "bool_17": 0,
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    assert "采样管冷凝水" in matched[0].message


def test_ms_routine_check_skips_majority_zero_bool():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    form = {
        "RULEITEMTAG": "Sup_RF_MSRoutineCheck",
        "CHECKDATE": "2026-09-04 00:00:00",
        "bool_13": 0,
        "bool_2": 0,
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert "分子涡轮泵工作状态" in matched[0].message


def test_ms_quality_calibration_abnormal_result_hits():
    from app.services.ops_audit.rules.sup_form_rules import ABNORMAL_RULE_ID

    form = {
        "RULEITEMTAG": "Sup_RF_MSQualityCalibration",
        "CHECKDATE": "2026-09-14 00:00:00",
        "string9": "合格",
        "string12": "异常",
        "time1": "2026-05-29 00:00:00",
        "time2": "2026-11-11 00:00:00",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == ABNORMAL_RULE_ID]
    assert len(matched) == 1
    assert "208Pb+" in matched[0].message
    assert DATE_RULE_ID not in _rule_ids(issues)


def test_vocs_scene_temp_over_range_with_remark_downgrades():
    form = {
        "RULEITEMTAG": "Sup_RF_VocsSceneCheck",
        "CHECKDATE": "2026-09-04 00:00:00",
        "string1": "27.8",
        "string2": "50",
        "remark1": "站房巡检时开门导致温度偏高",
    }
    issues = _run(form)

    matched = [issue for issue in issues if issue.rule_id == RANGE_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    evidence = json.loads(matched[0].evidence)
    assert evidence["with_remark"] is True


# ---------------------------------------------------------------------------
# Sup_RF_NH3Calibration（2026-11-09 建档）：数值区间规则
# 数据形态为"数值+单位"混填，需确认解析后按文档标称区间判定。
# ---------------------------------------------------------------------------


def _run_nh3(form, order=None):
    issues: list[Issue] = []
    check_sup_form_rules(
        order or {"WORKINGORDERCODE": "CH_NH3", "CREATETIME": "2026-09-04 10:00:00"},
        [("SUP_RF_NH3CALIBRATION", form)],
        issues,
        [],
        [],
    )
    return issues


def test_nh3_calibration_in_range_values_pass():
    """带单位的合规值（0.730 / 326.3℃ / 774.5℃ / 88.9mmhg）不应命中。"""

    issues = _run_nh3(
        {
            "RULEITEMTAG": "Sup_RF_NH3Calibration",
            "WORKINGORDERCODE": "CH_NH3",
            "CHECKDATE": "2026-10-20",
            "string1": "0.730",
            "string6": "326.3℃",
            "string7": "774.5℃",
            "string8": "88.9mmhg",
        }
    )
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_nh3_calibration_out_of_range_hits():
    """整行错位的真实错误（温度填进流量列、转化炉填反应室温度）应命中。"""

    issues = _run_nh3(
        {
            "RULEITEMTAG": "Sup_RF_NH3Calibration",
            "WORKINGORDERCODE": "CH_NH3",
            "CHECKDATE": "2026-10-31",
            "string1": "0.730",
            "string6": "95.4",
            "string7": "325.8",
            "string8": "780.2",
        }
    )
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    labels = {
        v["label"]
        for v in json.loads(hits[0].evidence)["violations"]
    }
    assert labels == {"反应室温度", "转化炉温度", "反应室压力"}


def test_nh3_calibration_cx_variant_reuses_profile():
    """CX 变体共用同一张分表与同一套题目项列，档案合并复用。"""

    issues = _run_nh3(
        {
            "RULEITEMTAG": "Sup_RF_NH3CalibrationCX",
            "WORKINGORDERCODE": "CH_NH3CX",
            "CHECKDATE": "2026-10-20",
            "string6": "95.4",
        }
    )
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID]


def test_daily_inspection_has_no_numeric_range_rule():
    """日巡检的温度/压力列是站内自设值与 MPa/psi 混填，不得落数值区间规则
    （2026-11-09 全量 531 行实证：按 400℃ 判会误报 8.7%）。"""

    issues = _run_nh3(
        {
            "RULEITEMTAG": "Sup_RF_DailyInspection",
            "WORKINGORDERCODE": "CH_DAILY",
            "CHECKDATE": "2026-10-20",
            "string1": "431",     # 站内自设温度，不是异常
            "string2": "58psi",   # 与 MPa 混填
            "string3": "0.4",
        }
    )
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


# ---------------------------------------------------------------------------
# Sup_RF_GACWeekMaintain（2026-11-09 建档）：品牌分档区间
# 同一题号在不同色谱柱规格下量程不同，只能按 devicebrand 反推档位。
# ---------------------------------------------------------------------------


def _run_gac(form, brand):
    issues: list[Issue] = []
    payload = {"RULEITEMTAG": "Sup_RF_GACWeekMaintain", "WORKINGORDERCODE": "CH_GAC",
               "CREATETIME": "2026-10-20 10:00:00", "DEVICEBRAND": brand}
    payload.update(form)
    check_sup_form_rules(
        {"WORKINGORDERCODE": "CH_GAC"},
        [("SUP_RF_GACWEEKMAINTAIN", payload)],
        issues,
        [],
        [],
    )
    return issues


def test_gac_pengyuchangya_2mm_column_flow_passes():
    """2mm 柱口径（0.30/0.25 ml/min、抑制器 23/11 mA）在 Pengyuchangya 下不应命中。"""

    issues = _run_gac(
        {"anioncolumnresult": "0.30", "cationcolumnresult": "0.25",
         "anionsuppressorresult": "23", "cationsuppressorresult": "11"},
        "Pengyuchangya",
    )
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_gac_th_4mm_column_flow_passes():
    """4mm 柱口径（0.70/0.60、抑制器 30/25）在 TH 下不应命中。"""

    issues = _run_gac(
        {"anioncolumnresult": "0.70", "cationcolumnresult": "0.60",
         "anionsuppressorresult": "30", "cationsuppressorresult": "25"},
        "TH",
    )
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_gac_brand_mismatch_value_hits():
    """Pengyuchangya 站点填了 4mm 口径的柱流量应命中（档位用错）。"""

    issues = _run_gac({"anioncolumnresult": "0.70", "cationcolumnresult": "0.25"}, "Pengyuchangya")
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    violations = json.loads(hits[0].evidence)["violations"]
    assert violations[0]["column"] == "anioncolumnresult"
    assert violations[0]["brand"] == "Pengyuchangya"
    assert violations[0]["min"] == 0.2 and violations[0]["max"] == 0.35


def test_gac_unknown_brand_skips_range_check():
    """品牌未命中分档时跳过判定，不得用错误档位产生误报。"""

    issues = _run_gac({"anioncolumnresult": "99", "cationcolumnresult": "99"}, "UnknownBrand")
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


# ---------------------------------------------------------------------------
# Sup_RF_PM1MonitorInspection_*（2026-11-09 建档）
# 关键：标志位方向为 0=是/正常、1=否/异常（Vue 映射确认），
# 且仅在异常项未填 otherremarks 时报问题。
# ---------------------------------------------------------------------------


def _run_pm1(tag, form):
    issues: list[Issue] = []
    payload = {"RULEITEMTAG": tag, "WORKINGORDERCODE": "CH_PM1",
               "CREATETIME": "2026-10-20 10:00:00"}
    payload.update(form)
    check_sup_form_rules({"WORKINGORDERCODE": "CH_PM1"},
                         [("SUP_RF_PM1MONITORINSPECTION", payload)], issues, [], [])
    return issues


def test_pm1_week_all_yes_passes():
    """三项全 0（是/正常）且无备注，不应命中。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_Week", {
        "dtisitcalibrated": 0, "ipisitcalibrated": 0, "papertapeisitcalibrated": 0,
        "otherremarks": "",
    })
    assert issues == []


def test_pm1_week_abnormal_with_remark_passes():
    """任一项为 1（否/异常）但填了 otherremarks，视为已说明，不报。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_Week", {
        "dtisitcalibrated": 0, "ipisitcalibrated": 1, "papertapeisitcalibrated": 0,
        "otherremarks": "仪器故障停运，已报备",
    })
    assert issues == []


def test_pm1_week_abnormal_without_remark_hits():
    """任一项为 1 且无备注，应判异常未说明。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_Week", {
        "dtisitcalibrated": 0, "ipisitcalibrated": 1, "papertapeisitcalibrated": 0,
        "otherremarks": "",
    })
    hits = [i for i in issues if i.rule_id == ABNORMAL_RULE_ID]
    assert len(hits) == 1
    items = json.loads(hits[0].evidence)["items"]
    assert items[0]["column"] == "ipisitcalibrated"
    assert items[0]["label"] == "仪器参数"


def test_pm1_month_merror_out_of_5pct_hits():
    """校准膜测定误差超 ±5% 应命中（文档红字阈值）。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_Month", {"merror": "7.2%"})
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    assert json.loads(hits[0].evidence)["violations"][0]["value"] == 7.2


def test_pm1_month_merror_in_range_passes():
    """全量 610 行无越界，正常值不得命中。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_Month", {"merror": "0.9%"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_pm1_halfyear_abnormal_direction_confirmed():
    """半年检标志位方向经 92 行全量+备注实证落定（2026-11-14）：
    external/insideisitclean 1=否-需处理（异常）、leakwhether 0=是-漏气（异常）。
    1/0 值无备注命中；带备注豁免。"""

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_HalfYear", {
        "externalisitclean": 1, "insideisitclean": 1, "leakwhether": 0,
        "otherremarks": "",
    })
    hits = [i for i in issues if i.rule_id == ABNORMAL_RULE_ID]
    # 同表多列命中打包为一条 Issue，evidence.items 逐列记录
    assert len(hits) == 1
    evidence_items = json.loads(hits[0].evidence)["items"]
    cols = {item["column"] for item in evidence_items}
    assert cols == {"externalisitclean", "insideisitclean", "leakwhether"}

    issues = _run_pm1("Sup_RF_PM1MonitorInspection_HalfYear", {
        "externalisitclean": 1, "insideisitclean": 1, "leakwhether": 0,
        "otherremarks": "厂家告知无分析腔体清洁，采样泵内置损坏直接更换",
    })
    assert [i for i in issues if i.rule_id == ABNORMAL_RULE_ID] == []


# ---------------------------------------------------------------------------
# 收益摸底批次（2026-11-09）：SpeedMeterMaintain / CO2Inspection /
# EquipmentStatus / URGWeekMaintain
# ---------------------------------------------------------------------------


def _run_tag(tag, table, form, order=None):
    issues: list[Issue] = []
    payload = {"RULEITEMTAG": tag, "WORKINGORDERCODE": "CH_SCAN",
               "CREATETIME": "2026-10-20 10:00:00"}
    payload.update(form)
    check_sup_form_rules(order or {"WORKINGORDERCODE": "CH_SCAN"},
                         [(table, payload)], issues, [], [])
    return issues


def test_speedmeter_abnormal_without_remark_hits():
    """isitnormal=1（不正常）且配对备注与全局备注均空，应命中。"""

    issues = _run_tag("Sup_RF_SpeedMeterMaintain", "SUP_RF_SPEEDMETERMAINTAIN",
                      {"dctisitnormal": 1, "dctremarks": "", "remarks": ""})
    hits = [i for i in issues if i.rule_id == ABNORMAL_RULE_ID]
    assert len(hits) == 1
    assert json.loads(hits[0].evidence)["items"][0]["label"] == "DCT 部件"


def test_speedmeter_abnormal_with_paired_remark_passes():
    """配对备注列有值即豁免。"""

    issues = _run_tag("Sup_RF_SpeedMeterMaintain", "SUP_RF_SPEEDMETERMAINTAIN",
                      {"dctisitnormal": 1, "dctremarks": "已更换，运行正常", "remarks": ""})
    assert [i for i in issues if i.rule_id == ABNORMAL_RULE_ID] == []


def test_speedmeter_abnormal_with_global_remark_passes():
    """全局 remarks 列有值也应豁免（挪机/停运类说明）。"""

    issues = _run_tag("Sup_RF_SpeedMeterMaintain", "SUP_RF_SPEEDMETERMAINTAIN",
                      {"dctisitnormal": 1, "dctremarks": "", "remarks": "挪机安装调试中"})
    assert [i for i in issues if i.rule_id == ABNORMAL_RULE_ID] == []


def test_speedmeter_all_normal_passes():
    issues = _run_tag("Sup_RF_SpeedMeterMaintain", "SUP_RF_SPEEDMETERMAINTAIN",
                      {c: 0 for c in ("nstisitnormal", "acstisitnormal", "dctisitnormal")})
    assert [i for i in issues if i.rule_id == ABNORMAL_RULE_ID] == []


def test_co2_inspection_ranges_pass_on_typical_values():
    """实测分布（气压 731~776 / 流量 0.99~1.1 / 内温 33~36）不得命中。"""

    issues = _run_tag("Sup_RF_CO2Inspection", "SUP_RF_CO2INSPECTION",
                      {"string3": "749.5", "string4": "1.018L/min", "string5": "34.4"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_co2_inspection_out_of_range_hits():
    issues = _run_tag("Sup_RF_CO2Inspection", "SUP_RF_CO2INSPECTION",
                      {"string5": "50.0"})
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    assert json.loads(hits[0].evidence)["violations"][0]["column"] == "string5"


def test_equipment_status_tih200_out_of_range_hits():
    """TiH200（Etraninc）蠕动泵1流量越界应命中；泵2（string5）区间已停用
    （2026-11-14 全年验证：梅华恒填 0.2/莲花山恒填 0.6，站点泵管口径差异，
    35/35 命中为档位不适用，待业务确认各站规格）。"""

    issues = _run_tag("Sup_RF_EquipmentStatus", "SUP_RF_EQUIPMENTSTATUS",
                      {"DEVICEBRAND": "Etraninc", "DEVICEMODEL": "TiH200",
                       "string4": "0.80", "string5": "0.6"})
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    violations = json.loads(hits[0].evidence)["violations"]
    assert violations[0]["column"] == "string4"
    assert violations[0]["brand"] == "Etraninc"

    # string5 已停用：越界值不再命中
    issues = _run_tag("Sup_RF_EquipmentStatus", "SUP_RF_EQUIPMENTSTATUS",
                      {"DEVICEBRAND": "Etraninc", "DEVICEMODEL": "TiH200",
                       "string5": "0.6"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_equipment_status_sdl_skipped_without_range():
    """SDL（Model4050）的 string4 是另一道题（电压），无档位不得按流量区间判定。"""

    issues = _run_tag("Sup_RF_EquipmentStatus", "SUP_RF_EQUIPMENTSTATUS",
                      {"DEVICEBRAND": "SDL", "DEVICEMODEL": "Model4050",
                       "string4": "640v", "string5": "1.0"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_urg_cation_pressure_in_range_passes():
    """URG9000D 阳离子柱压实测 1519~1840 psi，不得命中。"""

    issues = _run_tag("Sup_RF_URGWeekMaintain", "SUP_RF_URGWEEKMAINTAIN",
                      {"cationpressureresult": "1840"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_urg_water_peak_not_profiled_yet():
    """水峰 0.25/0.38 双稳态聚集待业务确认，不得落区间规则。"""

    issues = _run_tag("Sup_RF_URGWeekMaintain", "SUP_RF_URGWEEKMAINTAIN",
                      {"anionicwaterpeak1": "0.38"})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []


def test_parse_duration_seconds_text_forms():
    """时长解析覆盖真实填报形态（NH3 响应时间 T90）。"""

    from app.services.ops_audit.rules.sup_form_rules import parse_duration_seconds

    assert parse_duration_seconds("5min") == 300.0
    assert parse_duration_seconds("45MIN") == 2700.0
    assert parse_duration_seconds("3分钟") == 180.0
    assert parse_duration_seconds("89.99s") == 89.99
    assert parse_duration_seconds("290s") == 290.0
    assert parse_duration_seconds("3min35") == 215.0
    assert parse_duration_seconds("5min12s") == 312.0
    assert parse_duration_seconds("129") == 129.0
    assert parse_duration_seconds(600) == 600.0
    # 单位误填与其他物理量：不判（None），避免首数字解析误判
    assert parse_duration_seconds("147ppb") is None
    assert parse_duration_seconds("-") is None
    assert parse_duration_seconds(None) is None


def test_response_time_duration_range_uses_value_type():
    """value_type=duration_seconds 的 range 规则：45min(2700s) 超标命中、5min 通过。

    档案 Sup_RF_NH3ResponseTimeInspection 的 T90≤600s 规则（HJ 1393-2024 红字）。
    """

    issues = _run_tag("Sup_RF_NH3ResponseTimeInspection", "SUP_RF_NH3RESPONSETIMEINSPECTION",
                      {"responsetimet90": "45min", "remark1": ""})
    hits = [i for i in issues if i.rule_id == RANGE_RULE_ID]
    assert len(hits) == 1
    assert "45min" in (hits[0].message or "")
    assert "2700.0" in json.dumps(hits[0].evidence or {}, ensure_ascii=False)

    issues = _run_tag("Sup_RF_NH3ResponseTimeInspection", "SUP_RF_NH3RESPONSETIMEINSPECTION",
                      {"responsetimet90": "5min", "remark1": ""})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []

    # 单位误填（147ppb）解析为 None，不产生命中
    issues = _run_tag("Sup_RF_NH3ResponseTimeInspection", "SUP_RF_NH3RESPONSETIMEINSPECTION",
                      {"responsetimet90": "147ppb", "remark1": ""})
    assert [i for i in issues if i.rule_id == RANGE_RULE_ID] == []
