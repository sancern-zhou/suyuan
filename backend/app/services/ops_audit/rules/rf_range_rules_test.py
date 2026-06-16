from app.services.ops_audit.rules import rf_range_rules
from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values


def test_pm_weekly_main_flow_blank_is_optional_without_semantic_issue():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606051780669608369"}
    form = {
        "WORKINGORDERCODE": "CH2606051780669608369",
        "DEVICEBRAND": "Thermo",
        "POLLUTANTTYPE": "PM10",
        "MAINFLOWVALUE": "",
        "AIRTEMPVALUE": "35.2",
        "REMARK": "",
    }

    check_rf_range_values(order, [("RF_W_PMCHECK", form)], issues)

    assert [issue.rule_id for issue in issues] == []


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


def test_nox_thermo_ozone_flow_converts_l_per_min_to_ml_per_min():
    for order_code, raw_value in [
        ("CH2606011780295532943", ">0.05l/min"),
        ("CH2606011780297365656", ">0.050L/min"),
    ]:
        issues = []
        form = {
            "WORKINGORDERCODE": order_code,
            "DEVICEBRAND": "THERMO",
            "POLLUTANTTYPE": "NOX",
            "CYLLIANGCHECKVALUE": raw_value,
        }

        check_rf_range_values({"WORKINGORDERCODE": order_code}, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

        assert [issue.rule_id for issue in issues] == []


def test_o3_signal_converts_volts_to_millivolts_before_range_check():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606011780276955877"}
    form = {
        "WORKINGORDERCODE": "CH2606011780276955877",
        "DEVICEBRAND": "天虹",
        "POLLUTANTTYPE": "O3",
        "GYCHECKVALUE": "2.333V",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_O3", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_esa_reaction_temperature_is_not_audited():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606061780721914673"}
    form = {
        "WORKINGORDERCODE": "CH2606061780721914673",
        "DEVICEBRAND": "ESA",
        "POLLUTANTTYPE": "NOX",
        "FYCHECKVALUE": "59.9℃",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_xh_reaction_pressure_is_not_audited():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606041780562726996"}
    form = {
        "WORKINGORDERCODE": "CH2606041780562726996",
        "DEVICEBRAND": "XH",
        "POLLUTANTTYPE": "NOX",
        "FYSHICHECKVALUE": "5.825",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_thermo_reaction_pressure_is_not_audited():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606031780491579385"}
    form = {
        "WORKINGORDERCODE": "CH2606031780491579385",
        "DEVICEBRAND": "THERMO",
        "POLLUTANTTYPE": "NOX",
        "FYSHICHECKVALUE": "5.825",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_xh_reaction_temperature_is_not_audited():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606041780562726996"}
    form = {
        "WORKINGORDERCODE": "CH2606041780562726996",
        "DEVICEBRAND": "XH",
        "POLLUTANTTYPE": "NOX",
        "FYCHECKVALUE": "59.9℃",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_o3_th_brand_with_thermo_model_uses_thermo_signal_ranges():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606061780704863545"}
    form = {
        "WORKINGORDERCODE": "CH2606061780704863545",
        "DEVICEBRAND": "TH",
        "DEVICEMODEL": "49i",
        "POLLUTANTTYPE": "O3",
        "GYCHECKVALUE": "45866.333HZ",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_O3", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_o3_th_brand_with_tianhong_model_uses_tianhong_signal_ranges():
    issues = []
    order = {"WORKINGORDERCODE": "WO-TH-2001H"}
    form = {
        "WORKINGORDERCODE": "WO-TH-2001H",
        "DEVICEBRAND": "TH",
        "DEVICEMODEL": "TH-2001H",
        "POLLUTANTTYPE": "O3",
        "GYCHECKVALUE": "45866.333HZ",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_O3", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert len(matched) == 1
    assert "超出TH品牌正常范围" in matched[0].message


def test_weekly_gaseous_profiles_classify_th_abbreviation_by_model():
    profiles = {
        **rf_range_rules.RANGE_PROFILES.get("o3_weekly_check_profiles", {}),
        **rf_range_rules.RANGE_PROFILES.get("nox_weekly_check_profiles", {}),
        **rf_range_rules.RANGE_PROFILES.get("so2_weekly_check_profiles", {}),
    }

    for profile in profiles.values():
        aliases = profile.get("brand_aliases", {})
        assert rf_range_rules._normalize_profile_brand("TH", aliases, "2001H") == "TH"
        assert rf_range_rules._normalize_profile_brand("TH", aliases, "2004H") == "TH"
        assert rf_range_rules._normalize_profile_brand("TH", aliases, "49i") == "THERMO"
        assert rf_range_rules._normalize_profile_brand("TH", aliases, "") == "THERMO"
        assert rf_range_rules._normalize_profile_brand("天虹", aliases) == "TH"


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


def test_nox_reference_pmt_out_of_spec_carries_field_row_explanation():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606051780652736334"}
    form = {
        "WORKINGORDERCODE": "CH2606051780652736334",
        "DEVICEBRAND": "FPI",
        "POLLUTANTTYPE": "NOX",
        "PMTCHECKVALUE": "0.002",
        "PMTCHECKROW": "表格范围有误",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert len(matched) == 1
    evidence = __import__("json").loads(matched[0].evidence)
    assert evidence["handling_record_candidates"]["PMTCHECKROW"] == "表格范围有误"


def test_nox_reference_pmt_uses_inline_factory_range_before_brand_default():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606051780659850956"}
    form = {
        "WORKINGORDERCODE": "CH2606051780659850956",
        "DEVICEBRAND": "FPI",
        "POLLUTANTTYPE": "NOX",
        "PMTCHECKVALUE": "0.018",
        "PMTCHECKROW": "厂家文件范围：0～4.096 v",
        "REMARK": "",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_xh_sample_pressure_converts_inhg_to_kpa_before_range_check():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606021780386015769"}
    form = {
        "WORKINGORDERCODE": "CH2606021780386015769",
        "DEVICEBRAND": "XH",
        "POLLUTANTTYPE": "NOX",
        "CYYLCHECKVALUE": "25.6 In-Hg-A",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_nox_esa_sample_pressure_with_hpa_does_not_compare_against_mv_range():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606011780302457542"}
    form = {
        "WORKINGORDERCODE": "CH2606011780302457542",
        "DEVICEBRAND": "ESA",
        "POLLUTANTTYPE": "NOX",
        "CYYLCHECKVALUE": "978 hPa",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    assert [issue.rule_id for issue in issues] == ["RF_RANGE_UNIT_MISMATCH"]
    assert "单位不一致" in issues[0].message
    assert "无法进行范围比对" in issues[0].message
