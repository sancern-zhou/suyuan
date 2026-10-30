"""组分站附件档案规则单测（审核二期）。

覆盖 SUP_ATTACHMENT_REQUIRED_MISSING / SUP_ATTACHMENT_ITEM_MATCH 的命中、
豁免与通过路径；案例背景：丰顺八乡山 BC 年检缺报告、博罗石下周质控等。
"""

import json

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.sup_attachment_rules import (
    MISSING_RULE_ID,
    ITEM_MATCH_RULE_ID,
    check_sup_attachment_rules,
)


def _run(forms, wo_commonfiles=None, attachments=None):
    issues: list[Issue] = []
    check_sup_attachment_rules(
        {"WORKINGORDERCODE": "CH_TEST"},
        forms,
        attachments or [],
        wo_commonfiles or [],
        issues,
    )
    return issues


def _file(typecode, filename):
    return {"TYPECODE": typecode, "FILENAME": filename}


def _year_form(**overrides):
    form = {
        "WORKINGORDERCODE": "CH2609241790216699673",
        "RULEITEMTAG": "Sup_RF_PDLIYearCheck",
        "POLLUTANTTYPE": "BC",
        "CHECKDATE": "2026-09-23 00:00:00",
    }
    form.update(overrides)
    return [("SUP_RF_COMMON", form)]


# ---------------------------------------------------------------------------
# SUP_ATTACHMENT_REQUIRED_MISSING（案例：丰顺八乡山 7 张 jpg 无维护报告）
# ---------------------------------------------------------------------------


def test_missing_report_hits_when_only_process_photos():
    files = [
        _file("Sup_RF_PDLIYearCheck_BC", "气路清洁.jpg"),
        _file("Sup_RF_PDLIYearCheck_BC", "稳定性测试 (7).jpg"),
        _file("Sup_RF_PDLIYearCheck_BC", "零点测试 (5).jpg"),
    ]
    issues = _run(_year_form(), wo_commonfiles=files)

    matched = [issue for issue in issues if issue.rule_id == MISSING_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    assert "报告" in matched[0].message
    evidence = json.loads(matched[0].evidence)
    assert evidence["attachment_count"] == 3
    assert evidence["missing"][0]["class"] == "report"


def test_report_document_passes():
    files = [
        _file("Sup_RF_PDLIYearCheck_BC", "2026丰顺八乡山非常规仪器预防性维护报告.doc"),
        _file("Sup_RF_PDLIYearCheck_BC", "气路清洁.jpg"),
    ]
    issues = _run(_year_form(), wo_commonfiles=files)

    assert MISSING_RULE_ID not in {issue.rule_id for issue in issues}


def test_exemption_remark_skips_report_requirement():
    files = [_file("Sup_RF_PDLIYearCheck_BC", "仪器参数.jpg")]
    forms = _year_form(remark="设备运行正常，无需送检，预防性维护")
    issues = _run(forms, wo_commonfiles=files)

    assert issues == []


def test_missing_data_file_hits_for_week_qc():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-14 00:00:00",
    }
    files = [
        _file("Sup_RF_Week_NMHCQC_NMHC", "甲烷非甲烷零点核查.jpg"),
        _file("Sup_RF_Week_NMHCQC_NMHC", "甲烷非甲烷跨度核查.jpg"),
    ]
    issues = _run([("SUP_RF_COMMON", form)], wo_commonfiles=files)

    matched = [issue for issue in issues if issue.rule_id == MISSING_RULE_ID]
    assert len(matched) == 1
    assert "数据文件" in matched[0].message


def test_data_file_xlsx_passes_for_week_qc():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-14 00:00:00",
    }
    files = [
        _file("Sup_RF_Week_NMHCQC_NMHC", "2026年09月08日甲烷非甲烷分析仪质控检查.xlsx"),
        _file("Sup_RF_Week_NMHCQC_NMHC", "甲烷非甲烷零点核查.jpg"),
    ]
    issues = _run([("SUP_RF_COMMON", form)], wo_commonfiles=files)

    assert issues == []


def test_attachments_from_links_source_are_matched():
    """wo_commonfile_links 来源（refid 型附件表）同样参与匹配。"""

    form = {
        "RULEITEMTAG": "Sup_RF_WaterSolubleIonsQuality",
        "POLLUTANTTYPE": "WaterSolubleIons",
        "CHECKDATE": "2026-08-27 00:00:00",
    }
    links = [
        {"refid": "CH_TEST", "typecode": "Sup_RF_WaterSolubleIonsQuality_WaterSolubleIons",
         "filename": "气体-气溶胶水溶性离子质控记录表2026年8月27日.xlsx"},
    ]
    issues = _run([("SUP_RF_COMMON", form)], attachments=links)

    assert issues == []


# ---------------------------------------------------------------------------
# SUP_ATTACHMENT_ITEM_MATCH（附件类型码监测项目后缀与表单 pollutanttype 一致性）
# ---------------------------------------------------------------------------


def test_item_match_hits_when_all_typecodes_mismatch_pollutant():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-28 00:00:00",
    }
    files = [
        _file("Sup_RF_Week_NMHCQC_HCHO", "甲醛零点核查.jpg"),
        _file("Sup_RF_Week_NMHCQC_HCHO", "甲醛质控数据.xlsx"),
    ]
    issues = _run([("SUP_RF_COMMON", form)], wo_commonfiles=files)

    matched = [issue for issue in issues if issue.rule_id == ITEM_MATCH_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "高"
    assert "不一致" in matched[0].message


def test_item_match_passes_when_suffix_matches():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-28 00:00:00",
    }
    files = [
        _file("Sup_RF_Week_NMHCQC_NMHC", "甲烷非甲烷零点核查.jpg"),
        _file("Sup_RF_Week_NMHCQC_HCHO", "串门误传.jpg"),
    ]
    issues = _run([("SUP_RF_COMMON", form)], wo_commonfiles=files)

    assert ITEM_MATCH_RULE_ID not in {issue.rule_id for issue in issues}


def test_item_match_skips_without_attachments():
    form = {
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-28 00:00:00",
    }
    issues = _run([("SUP_RF_COMMON", form)], wo_commonfiles=[])

    # 无附件时 item_match 不判（无证据），但必需数据文件缺失仍命中。
    assert ITEM_MATCH_RULE_ID not in {issue.rule_id for issue in issues}
    assert MISSING_RULE_ID in {issue.rule_id for issue in issues}
