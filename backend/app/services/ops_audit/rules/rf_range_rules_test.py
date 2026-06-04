from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values


def test_nox_thermo_ozone_flow_greater_than_threshold_text_is_in_spec():
    issues = []
    order = {"WORKINGORDERCODE": "CH2605191779151736054"}
    form = {
        "WORKINGORDERCODE": "CH2605191779151736054",
        "DEVICEBRAND": "Thermo",
        "POLLUTANTTYPE": "NOX",
        "CYLLIANGCHECKVALUE": "＞50",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_reference_pmt_out_of_spec_carries_abnormal_handling_for_semantic_review():
    issues = []
    order = {"WORKINGORDERCODE": "WO-NOX-PMT"}
    form = {
        "WORKINGORDERCODE": "WO-NOX-PMT",
        "DEVICEBRAND": "FPI",
        "POLLUTANTTYPE": "NOX",
        "PMTCHECKVALUE": "0.002",
        "EXCEPTIONHANDLINGRECORD": "检查发现参考PMT偏低，已清洁光室并复测恢复正常。",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert len(matched) == 1
    evidence = __import__("json").loads(matched[0].evidence)
    assert evidence["needs_semantic_review"] is True
    assert evidence["handling_record_candidates"] == {
        "EXCEPTIONHANDLINGRECORD": "检查发现参考PMT偏低，已清洁光室并复测恢复正常。"
    }
    assert evidence["out_of_spec_values"][0]["field"] == "PMTCHECKVALUE"
    assert evidence["out_of_spec_values"][0]["label"] == "参考PMT信号"
