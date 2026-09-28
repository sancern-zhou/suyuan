from dataclasses import asdict

import pytest

from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.rules.rf_visibility_rules import (
    DEVICE_FIELDS,
    VISIBILITY_TABLES,
    check_rf_visibility_values,
)


@pytest.mark.parametrize("table", sorted(VISIBILITY_TABLES))
@pytest.mark.parametrize("placeholder", ["?", "？", " ? ", " ？ "])
def test_no_device_question_mark_placeholders_are_not_conflicts(table, placeholder):
    form = {
        "REMARK": "站点无能见度仪器，合同站点无该项仪器",
        **dict.fromkeys(DEVICE_FIELDS, placeholder),
    }
    issues = []

    check_rf_visibility_values(
        {"WORKINGORDERCODE": "CH2608261787709484945"}, [(table, form)], issues
    )

    assert issues == []


@pytest.mark.parametrize("description_field", ["REMARK", "JIAOZHUNRESULT", "OTHERVALUE"])
@pytest.mark.parametrize("device_field,value", [("DEVICEMODEL", "49i"), ("DEVICECODE", "CM12529095")])
def test_actual_device_conflict_keeps_original_explanation(description_field, device_field, value):
    remark = "站点无能见度仪器，合同站点无该项仪器"
    form = {
        **dict.fromkeys(DEVICE_FIELDS, "?"),
        description_field: remark,
        device_field: value,
    }
    issues = []
    check_rf_visibility_values(
        {"WORKINGORDERCODE": "WO-VISIBILITY"}, [("RF_HY_VISIBILITYCALI", form)], issues
    )

    assert len(issues) == 1
    assert issues[0].field == f"rf.RF_HY_VISIBILITYCALI.{device_field}"
    result = build_final_issue_list(
        {"records": [{"working_order_code": "WO-VISIBILITY", "scoring_issues": [asdict(issues[0])]}]},
        {"results": []},
    )
    item = result["items"][0]
    assert item["remark_status"] == "provided"
    assert item["original_remark_text"] == remark
    assert item["original_remarks"][0]["field"] == description_field
