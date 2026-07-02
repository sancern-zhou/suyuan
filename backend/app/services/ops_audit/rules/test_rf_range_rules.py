from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values


def test_monthly_gaseous_flow_range_missing_adds_specific_issue():
    issues = []
    order = {"WORKINGORDERCODE": "WO-RANGE-MISSING"}
    form = {
        "WORKINGORDERCODE": "WO-RANGE-MISSING",
        "FLOWRANGSO2": "",
        "FLOWRANGNO2": "/",
        "FLOWRANGCO": "500-600 ml/min",
        "FLOWRANGO3": "-",
    }

    check_rf_range_values(order, [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    matching = [issue for issue in issues if issue.rule_id == "RF_M_GASEOUS_FLOW_RANGE_MISSING"]
    assert len(matching) == 1
    assert "SO2" in matching[0].message
    assert "NO2" in matching[0].message
    assert "O3" in matching[0].message
    assert "CO" not in matching[0].message


def test_monthly_gaseous_flow_normalizes_l_min_decimals_against_ml_min_range():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606231782210180137"}
    form = {
        "WORKINGORDERCODE": "CH2606231782210180137",
        "FLOWRANGSO2": "650±10%ml/min",
        "DISPLAYVALUESO2": "0.604",
        "MEASUREDVALUESO2": "0.61",
        "FLOWRANGNO2": "500±10%ml/min",
        "DISPLAYVALUENO2": "0.507",
        "MEASUREDVALUENO2": "0.52",
        "FLOWRANGCO": "800±10%ml/min",
        "DISPLAYVALUECO": "0.77",
        "MEASUREDVALUECO": "0.76",
        "FLOWRANGO3": "800±10%ml/min",
        "DISPLAYVALUEO3": "0.811",
        "MEASUREDVALUEO3": "0.85",
    }

    check_rf_range_values(order, [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_thermo_nox_ozone_flow_accepts_exact_50_threshold():
    issues = []
    order = {"WORKINGORDERCODE": "WO-NOX-OZONE-FLOW-50"}
    form = {
        "WORKINGORDERCODE": "WO-NOX-OZONE-FLOW-50",
        "DEVICEBRAND": "TE",
        "DEVICEMODEL": "42i",
        "POLLUTANTTYPE": "NOX",
        "CYLLIANGCHECKVALUE": "50",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_thermo_nox_ozone_flow_accepts_actual_fullwidth_bracket_greater_value():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606231782181762407"}
    form = {
        "WORKINGORDERCODE": "CH2606231782181762407",
        "DEVICEBRAND": "TE",
        "DEVICEMODEL": "42i",
        "POLLUTANTTYPE": "NOX",
        "CYLLIANGCHECKVALUE": "〉50",
        "REMARK": "零跨质控合格",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_thermo_nox_ozone_flow_infers_l_min_decimal_for_ml_min_spec():
    issues = []
    order = {"WORKINGORDERCODE": "WO-NOX-OZONE-FLOW-DECIMAL"}
    form = {
        "WORKINGORDERCODE": "WO-NOX-OZONE-FLOW-DECIMAL",
        "DEVICEBRAND": "TE",
        "DEVICEMODEL": "42i",
        "POLLUTANTTYPE": "NOX",
        "CYLLIANGCHECKVALUE": "0.050",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_xh_nox_sample_pressure_infers_inhg_when_unit_omitted():
    issues = []
    order = {"WORKINGORDERCODE": "WO-XH-NOX-PRESSURE-INHG"}
    form = {
        "WORKINGORDERCODE": "WO-XH-NOX-PRESSURE-INHG",
        "DEVICEBRAND": "XH",
        "DEVICEMODEL": "XH-42",
        "POLLUTANTTYPE": "NOX",
        "CYYLCHECKVALUE": "28.125",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_esa_nox_high_voltage_uses_v_unit_not_mv():
    issues = []
    order = {"WORKINGORDERCODE": "WO-ESA-NOX-HIGH-VOLTAGE"}
    form = {
        "WORKINGORDERCODE": "WO-ESA-NOX-HIGH-VOLTAGE",
        "DEVICEBRAND": "ESA",
        "DEVICEMODEL": "ESA",
        "POLLUTANTTYPE": "NOX",
        "GYCHECKVALUE": "650.52V",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id in {"RF_RANGE_OUT_OF_SPEC", "RF_RANGE_UNIT_MISMATCH"}]
    assert matched == []


def test_esa_nox_pressure_accepts_hpa_range_from_remark():
    issues = []
    order = {"WORKINGORDERCODE": "WO-ESA-NOX-PRESSURE-HPA-REMARK"}
    form = {
        "WORKINGORDERCODE": "WO-ESA-NOX-PRESSURE-HPA-REMARK",
        "DEVICEBRAND": "ESA",
        "DEVICEMODEL": "ESA",
        "POLLUTANTTYPE": "NOX",
        "FYSHICHECKVALUE": "205hpa",
        "CYYLCHECKVALUE": "988hpa",
        "REMARK": "反应室压力正常范围为133-433 hPa；采样压力正常范围为900-1100 hPa。",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id in {"RF_RANGE_OUT_OF_SPEC", "RF_RANGE_UNIT_MISMATCH"}]
    assert matched == []


def test_esa_nox_pressure_hpa_without_inline_range_does_not_report_unit_mismatch():
    issues = []
    order = {"WORKINGORDERCODE": "WO-ESA-NOX-PRESSURE-HPA"}
    form = {
        "WORKINGORDERCODE": "WO-ESA-NOX-PRESSURE-HPA",
        "DEVICEBRAND": "ESA",
        "DEVICEMODEL": "ESA",
        "POLLUTANTTYPE": "NOX",
        "FYSHICHECKVALUE": "205hpa",
        "CYYLCHECKVALUE": "988hpa",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_NOX", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_UNIT_MISMATCH"]
    assert matched == []


def test_xh_so2_slope_allows_near_one_values():
    issues = []
    order = {"WORKINGORDERCODE": "WO-XH-SO2-SLOPE"}
    form = {
        "WORKINGORDERCODE": "WO-XH-SO2-SLOPE",
        "DEVICEBRAND": "XH",
        "DEVICEMODEL": "XH",
        "POLLUTANTTYPE": "SO2",
        "YLCHECKVALUE": "0.979",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_SO2", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_sharp5030_pm_air_temperature_allows_sixty_degrees():
    issues = []
    order = {"WORKINGORDERCODE": "WO-SHARP5030-AIR-TEMP"}
    form = {
        "WORKINGORDERCODE": "WO-SHARP5030-AIR-TEMP",
        "DEVICEBRAND": "THERMO",
        "DEVICEMODEL": "SHARP5030",
        "POLLUTANTTYPE": "PM2.5",
        "AIRTEMPVALUE": "60",
    }

    check_rf_range_values(order, [("RF_W_PMCHECK", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert matched == []


def test_esa_so2_uv_intensity_accepts_lowercase_mv_unit_conversion():
    issues = []
    order = {"WORKINGORDERCODE": "WO-ESA-SO2-UV-MV"}
    form = {
        "WORKINGORDERCODE": "WO-ESA-SO2-UV-MV",
        "DEVICEBRAND": "ESA",
        "DEVICEMODEL": "ESA",
        "POLLUTANTTYPE": "SO2",
        "ZWDCHECKVALUE": "2150mv",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_SO2", form)], issues)

    matched = [issue for issue in issues if issue.rule_id in {"RF_RANGE_OUT_OF_SPEC", "RF_RANGE_UNIT_MISMATCH"}]
    assert matched == []


def test_ld_co_offset_out_of_spec_is_reported():
    issues = []
    order = {"WORKINGORDERCODE": "CH2606151781491794789"}
    form = {
        "WORKINGORDERCODE": "CH2606151781491794789",
        "DEVICEBRAND": "LD",
        "DEVICEMODEL": "LGH-230",
        "POLLUTANTTYPE": "CO",
        "JGCHECKVALUE": "-8.94 mV",
    }

    check_rf_range_values(order, [("RF_W_GASEOUSCHECK_CO", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == "RF_RANGE_OUT_OF_SPEC"]
    assert len(matched) == 1
    assert "CO周检截距检查值(-8.94 mV)超出LD品牌正常范围" in matched[0].message
