import json

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.rf_formula_rules import check_rf_formula_values
from app.services.ops_audit.rules.rf_humidity_rules import check_rf_environment_humidity_values
from app.services.ops_audit.rules.rf_multipoint_rules import check_rf_multipoint_values
from app.services.ops_audit.rules.rf_pm_pressure_rules import check_rf_pm_pressure_values
from app.services.ops_audit.rules.rf_range_rules import check_rf_range_values
from app.services.ops_audit.rules.rf_time_rules import check_rf_time_ranges
from app.services.ops_audit.rules.rf_visibility_rules import check_rf_visibility_values
from app.services.ops_audit.rules.lifecycle_rules import check_lifecycle_closure
from app.services.ops_audit.rules.rf_abnormal_remark_rules import check_rf_abnormal_remarks


def _order(code="CH_TEST", station_id="S1"):
    return {
        "WORKINGORDERCODE": code,
        "STATIONID": station_id,
        "CREATETIME": "2026-05-13 10:00:00",
        "FINISHTIME": "2026-05-13 18:00:00",
    }


def _issue_ids(issues: list[Issue]) -> set[str]:
    return {issue.rule_id for issue in issues}


def test_two_week_pm_flow_calibrate_check_time_uses_check_sdt_edt_fields():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778673426846",
        "CHECKDATE": "2026-05-13 19:38:00",
        "CheckSdt": "05 13 2026  1:30PM",
        "CheckEdt": "05 13 2026  1:45PM",
    }

    check_rf_time_ranges(_order("CH2605131778673426846"), [("RF_TW_PmFlowCalibrate", form)], issues)

    assert "RF_CHECK_TIME_OUTSIDE_RANGE" in _issue_ids(issues)


def test_two_week_pm_flow_calibrate_ignores_date_when_check_time_is_inside_time_window():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778673426846",
        "CHECKDATE": "2026-05-13 13:37:00",
        "CheckSdt": "05 16 2026  1:30PM",
        "CheckEdt": "05 16 2026  1:45PM",
    }

    check_rf_time_ranges(_order("CH2605131778673426846"), [("RF_TW_PmFlowCalibrate", form)], issues)

    assert "RF_CHECK_TIME_OUTSIDE_RANGE" not in _issue_ids(issues)


def test_pm_week_sample_tube_temperature_status_yes_is_normal_without_remark():
    issues: list[Issue] = []
    forms = [
        (
            "RF_W_PMCHECK",
            {
                "WORKINGORDERCODE": "CH2605151778820480002",
                "POLLUTANTTYPE": "PM10",
                "AIRTEMPVALUE": "34.45℃",
                "AIRTEMPISNORMAL": "是",
                "REMARK": "",
            },
        ),
        (
            "RF_W_PMCHECK",
            {
                "WORKINGORDERCODE": "CH2605151778820480002",
                "POLLUTANTTYPE": "PM2.5",
                "AIRTEMPVALUE": "38.3℃",
                "AIRTEMPISNORMAL": "是",
                "REMARK": "",
            },
        ),
    ]

    check_rf_abnormal_remarks(_order("CH2605151778820480002", "1723"), forms, issues)

    assert "RF_ABNORMAL_VALUE_NO_REMARK" not in _issue_ids(issues)


def test_week_o3_signal_b_uses_shared_signal_a_handling_record():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2606291782710438026",
        "POLLUTANTTYPE": "O3",
        "DEVICEBRAND": "TH",
        "DEVICEMODEL": "2004H",
        "GYBCHECKVALUE": "0.232V",
        "GYCHECKROW": "仪器显示值",
        "ZWDBCHECKVALUE": "0.235V",
        "ZWDCHECKROW": "仪器显示值",
        "REMARK": "",
    }

    forms = [("RF_W_GASEOUSCHECK_O3", form)]
    check_rf_range_values(_order("CH2606291782710438026", "1543"), forms, issues)
    check_rf_abnormal_remarks(_order("CH2606291782710438026", "1543"), forms, issues)

    matched = [
        issue
        for issue in issues
        if issue.rule_id == "RF_ABNORMAL_VALUE_NO_REMARK"
        and "测量信号B" in issue.message
    ]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert evidence["remark_candidates"]["GYCHECKROW"] == "仪器显示值"
    assert evidence["needs_semantic_review"] is True


def test_abnormal_value_remark_message_distinguishes_present_but_insufficient_note():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "WO-REMARK-CLARITY",
        "POLLUTANTTYPE": "O3",
        "DEVICEBRAND": "ESA",
        "GYCHECKVALUE": "64000.917",
        "GYCHECKROW": "",
        "REMARK": "目前使用赛默飞备机",
    }

    forms = [("RF_W_GASEOUSCHECK_O3", form)]
    check_rf_range_values(_order("WO-REMARK-CLARITY"), forms, issues)
    check_rf_abnormal_remarks(_order("WO-REMARK-CLARITY"), forms, issues)

    abnormal_remark_issue = next(
        issue for issue in issues if issue.rule_id == "RF_ABNORMAL_VALUE_NO_REMARK"
    )
    assert "备注说明不充分" in abnormal_remark_issue.message
    assert "无有效说明" not in abnormal_remark_issue.message
    assert "备注内容：REMARK=目前使用赛默飞备机" in abnormal_remark_issue.message


def test_multipoint_range_does_not_use_fixed_co_range_without_history():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605201779258146034",
        "STATIONID": "1001",
        "POLLUTANTTYPE": "CO",
        "PPB": 500,
    }

    check_rf_multipoint_values(_order("CH2605201779258146034"), [("RF_Q_GASEOUSMULTIPOINT_CO", form)], issues)

    assert "RF_MULTIPOINT_RANGE_INVALID" not in _issue_ids(issues)


def test_multipoint_range_flags_when_same_station_previous_same_form_range_changes():
    issues: list[Issue] = []
    current_order = _order("CH_CURRENT", "1001")
    current_form = {
        "WORKINGORDERCODE": "CH_CURRENT",
        "STATIONID": "1001",
        "CALIBRATIONDATE": "2026-05-20 10:00:00",
        "POLLUTANTTYPE": "CO",
        "PPB": 500,
    }
    previous_order = _order("CH_PREVIOUS", "1001")
    previous_order["CREATETIME"] = "2026-02-20 10:00:00"
    previous_form = {
        "WORKINGORDERCODE": "CH_PREVIOUS",
        "STATIONID": "1001",
        "CALIBRATIONDATE": "2026-02-20 10:00:00",
        "POLLUTANTTYPE": "CO",
        "PPB": 20000,
    }

    check_rf_multipoint_values(
        current_order,
        [("RF_Q_GASEOUSMULTIPOINT_CO", current_form)],
        issues,
        all_orders=[current_order, previous_order],
        forms_by_code={
            "CH_CURRENT": [("RF_Q_GASEOUSMULTIPOINT_CO", current_form)],
            "CH_PREVIOUS": [("RF_Q_GASEOUSMULTIPOINT_CO", previous_form)],
        },
    )

    assert "RF_MULTIPOINT_RANGE_INVALID" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["current_range"] == 500
    assert evidence["previous_range"] == 20000
    assert evidence["previous_order_code"] == "CH_PREVIOUS"


def test_hy_o3_valuepass_isok_range_flags_when_same_station_previous_range_changes():
    issues: list[Issue] = []
    current_order = _order("CH_CURRENT", "1502")
    current_form = {
        "WORKINGORDERCODE": "CH_CURRENT",
        "STATIONID": "1502",
        "CALIBRATIONDATE": "2026-05-17 10:00:00",
        "ISOK": "0 - 500",
    }
    previous_order = _order("CH_PREVIOUS", "1502")
    previous_order["CREATETIME"] = "2026-02-17 10:00:00"
    previous_form = {
        "WORKINGORDERCODE": "CH_PREVIOUS",
        "STATIONID": "1502",
        "CALIBRATIONDATE": "2026-02-17 10:00:00",
        "ISOK": "0 - 300",
    }

    check_rf_multipoint_values(
        current_order,
        [("RF_HY_O3VALUEPASS", current_form)],
        issues,
        all_orders=[current_order, previous_order],
        forms_by_code={
            "CH_CURRENT": [("RF_HY_O3VALUEPASS", current_form)],
            "CH_PREVIOUS": [("RF_HY_O3VALUEPASS", previous_form)],
        },
    )

    assert "RF_MULTIPOINT_RANGE_INVALID" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["current_field"] == "ISOK"
    assert evidence["current_range"] == 500
    assert evidence["previous_range"] == 300


def test_multipoint_step_time_rule_is_disabled():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605181779044294314",
        "CALIBRATIONDATE": "2026-05-18 00:00:00",
        "POLLUTANTTYPE": "SO2",
        "PPB": 500,
        "LINGDIANSDTDATE": "2026-05-18 17:41:00",
        "LINGDIANEDTDATE": "2026-05-18 17:47:00",
        "MCLSDTDATE10": "2026-05-18 17:47:00",
        "MCLEDTDATE10": "2026-05-18 18:10:00",
        "MCLSDTDATE20": "2026-05-18 18:10:00",
        "MCLEDTDATE20": "2026-05-18 18:32:00",
        "MCLSDTDATE40": "2026-05-18 18:32:00",
        "MCLEDTDATE40": "2026-05-23 18:44:00",
    }

    check_rf_multipoint_values(_order("CH2605181779044294314"), [("RF_Q_GASEOUSMULTIPOINT_SO2", form)], issues)

    assert "RF_Q_MULTIPOINT_STEP_TIME_INVALID" not in _issue_ids(issues)


def test_multipoint_step_time_allows_descending_high_to_low_sequence():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605201779258146034",
        "CALIBRATIONDATE": "2026-05-20 00:00:00",
        "POLLUTANTTYPE": "CO",
        "PPB": 20000,
        "MCLSDTDATE80": "2026-05-20 14:24:00",
        "MCLEDTDATE80": "2026-05-20 14:34:00",
        "MCLSDTDATE60": "2026-05-20 14:35:00",
        "MCLEDTDATE60": "2026-05-20 14:44:00",
        "MCLSDTDATE40": "2026-05-20 14:44:00",
        "MCLEDTDATE40": "2026-05-20 14:54:00",
        "MCLSDTDATE20": "2026-05-20 14:54:00",
        "MCLEDTDATE20": "2026-05-20 15:05:00",
        "MCLSDTDATE10": "2026-05-20 15:05:00",
        "MCLEDTDATE10": "2026-05-20 15:17:00",
        "LINGDIANSDTDATE": "2026-05-20 15:17:00",
        "LINGDIANEDTDATE": "2026-05-20 15:30:00",
    }

    check_rf_multipoint_values(_order("CH2605201779258146034"), [("RF_Q_GASEOUSMULTIPOINT_CO", form)], issues)

    assert "RF_Q_MULTIPOINT_STEP_TIME_INVALID" not in _issue_ids(issues)


def test_multipoint_step_time_allows_short_midnight_crossing():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605121778550428075",
        "CALIBRATIONDATE": "2026-05-12 00:00:00",
        "POLLUTANTTYPE": "NO2",
        "PPB": 500,
        "MCLSDTDATE60": "2026-05-12 23:59:00",
        "MCLEDTDATE60": "2026-05-13 00:09:00",
    }

    check_rf_multipoint_values(_order("CH2605121778550428075"), [("RF_Q_GASEOUSMULTIPOINT_NO2", form)], issues)

    assert "RF_Q_MULTIPOINT_STEP_TIME_INVALID" not in _issue_ids(issues)


def test_quarter_gaseous_flow_pressure_true_value_is_recomputed():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605201779247988093",
        "P_MeasuringValue": 755.16,
        "P_As": 0.9989,
        "P_Bs": 1.8459,
        "P_Pa": 760.0,
    }

    check_rf_formula_values(_order("CH2605201779247988093"), [("RF_Q_GaseousFlowCheck", form)], issues)

    assert "RF_Q_GASEOUSFLOWCHECK_PRESSURE_TRUE_VALUE_MISMATCH" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["violations"][0]["actual_field"] == "P_Pa"


def test_monthly_gaseous_flow_error_uses_display_minus_measured_percent():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605191779157293812",
        "DISPLAYVALUESO2": "622",
        "MEASUREDVALUESO2": "666",
        "MEASUREDERRORSO2": "-6.80%",
    }

    check_rf_formula_values(_order("CH2605191779157293812"), [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    assert "RF_VALUE_FORMULA_MISMATCH" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["violations"][0]["expected"] == -6.61


def test_monthly_gaseous_flow_error_over_ten_percent_is_flagged():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH_TEST",
        "DISPLAYVALUECO": "767",
        "MEASUREDVALUECO": "680",
        "MEASUREDERRORCO": "12.79%",
    }

    check_rf_formula_values(_order("CH_TEST"), [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    assert "RF_M_GASEOUSFLOWCHECK_ERROR_OUT_OF_RANGE" in _issue_ids(issues)


def test_pm_membrane_error_is_recomputed_from_original_minus_check():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605251779692955875",
        "PM25CHECKTEMP1VALUE": "0.806",
        "PM25CHECKTEMP2VALUE": "0.804",
        "PM25CHECKTEMP3VALUE": "-0.2",
    }

    check_rf_formula_values(_order("CH2605251779692955875"), [("RF_Q_PM25RUNSTATUSCHECK", form)], issues)

    assert "RF_PM_MEMBRANE_ERROR_MISMATCH" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["violations"][0]["expected_error"] == 0.2


def test_pm_membrane_error_over_two_percent_is_flagged():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH_TEST",
        "PM10CHECKTEMP1VALUE": "0.806",
        "PM10CHECKTEMP2VALUE": "0.830",
        "PM10CHECKTEMP3VALUE": "-3.0",
    }

    check_rf_formula_values(_order("CH_TEST"), [("RF_Q_PM10RUNSTATUSCHECK", form)], issues)

    assert "RF_PM_MEMBRANE_ERROR_OUT_OF_RANGE" in _issue_ids(issues)


def test_monthly_gaseous_flow_values_use_percent_range_text():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605191779157293812",
        "FLOWRANGSO2": "650±10% ml/min",
        "DISPLAYVALUESO2": "622",
        "MEASUREDVALUESO2": "716",
    }

    check_rf_range_values(_order("CH2605191779157293812"), [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    assert "RF_RANGE_OUT_OF_SPEC" in _issue_ids(issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["out_of_spec_values"][0]["field"] == "MEASUREDVALUESO2"
    assert evidence["out_of_spec_values"][0]["min"] == 585
    assert evidence["out_of_spec_values"][0]["max"] == 715


def test_monthly_gaseous_flow_values_allow_real_sample_inside_percent_range():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605191779157293812",
        "FLOWRANGSO2": "650±10% ml/min",
        "DISPLAYVALUESO2": "622",
        "MEASUREDVALUESO2": "666",
        "FLOWRANGCO": "800±10% ml/min",
        "DISPLAYVALUECO": "767",
        "MEASUREDVALUECO": "772",
    }

    check_rf_range_values(_order("CH2605191779157293812"), [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    assert "RF_RANGE_OUT_OF_SPEC" not in _issue_ids(issues)


def test_monthly_gaseous_flow_values_use_dash_range_text():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605181779071108109",
        "FLOWRANGSO2": "0.350～0.750 L/min",
        "DISPLAYVALUESO2": "0.505",
        "MEASUREDVALUESO2": "0.751",
    }

    check_rf_range_values(_order("CH2605181779071108109"), [("RF_M_GASEOUSFLOWCHECK", form)], issues)

    assert "RF_RANGE_OUT_OF_SPEC" in _issue_ids(issues)


def test_visibility_no_device_remark_conflicts_with_49i_device_fields():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605121778595368870",
        "REMARK": "无能见度设备",
        "DEVICEMODEL": "49i",
        "DEVICECODE": "CM12529095",
    }

    check_rf_visibility_values(_order("CH2605121778595368870"), [("RF_HY_VISIBILITYCALI", form)], issues)

    assert "RF_VISIBILITY_NO_DEVICE_FIELD_CONFLICT" in _issue_ids(issues)


def test_environment_humidity_flags_missing_sensor_reading_without_exemption():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605211779367142773",
        "pollutantType": "PM10",
        "StandardReadNum": "57.9%",
        "CailbPrevReadNum": "",
        "CailbNextReadNum": "",
        "REMARK": "",
    }

    check_rf_environment_humidity_values(
        _order("CH2605211779367142773"),
        [("RF_HY_EnvironmentHumidity", form)],
        issues,
    )

    assert "RF_HY_ENV_HUMIDITY_SENSOR_VALUE_MISSING" in _issue_ids(issues)


def test_environment_humidity_missing_sensor_reading_with_remark_needs_semantic_review():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605121778595368870",
        "pollutantType": "PM10",
        "StandardReadNum": "55.5%",
        "CailbPrevReadNum": "/",
        "CailbNextReadNum": "/",
        "REMARK": "C14机型无湿度功能",
    }

    check_rf_environment_humidity_values(
        _order("CH2605121778595368870"),
        [("RF_HY_EnvironmentHumidity", form)],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "RF_HY_ENV_HUMIDITY_SENSOR_VALUE_MISSING"]
    assert len(matched) == 1
    assert '"needs_semantic_review": true' in matched[0].evidence


def test_environment_humidity_flags_unchanged_before_after_values_without_remark():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605121778595345763",
        "pollutantType": "PM10",
        "StandardReadNum": "57.9",
        "CailbPrevReadNum": "58",
        "CailbNextReadNum": "58",
        "REMARK": "",
    }

    check_rf_environment_humidity_values(
        _order("CH2605121778595345763"),
        [("RF_HY_EnvironmentHumidity", form)],
        issues,
    )

    assert "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT" in _issue_ids(issues)


def test_lifecycle_does_not_treat_generic_remarks_as_effective_closure():
    issues: list[Issue] = []
    order = {
        "WORKINGORDERCODE": "WO-LIFECYCLE-REMARK",
        "CREATETIME": "2026-05-20 10:00:00",
        "FINISHTIME": "2026-05-20 10:20:00",
        "PLANFINISHTIME": "2026-05-20 10:30:00",
        "DDWORKINGORDERTYPE": "Check",
        "MAINTENANCETYPE": "Week",
    }
    workflows = [
        {"WORKINGORDERCODE": "WO-LIFECYCLE-REMARK", "PROCESSSTEP": "CreateOrder"},
        {"WORKINGORDERCODE": "WO-LIFECYCLE-REMARK", "PROCESSSTEP": "CheckOrder", "SUBMITREMARK": "已处理"},
    ]
    forms = [
        ("RF_W_PMCHECK", {"WORKINGORDERCODE": "WO-LIFECYCLE-REMARK", "REMARK": "已处理"})
    ]

    check_lifecycle_closure(order, workflows, forms, issues)

    assert "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE" in _issue_ids(issues)


def test_pm_pressure_recomputes_pressure_error_fields():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKPRES1VALUE": "993",
        "PM10CHECKPRES2VALUE": "996",
        "PM10CHECKPRES3VALUE": "-1.0",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_PRESSURE_ERROR_MISMATCH" in _issue_ids(issues)


def test_pm_pressure_flags_invalid_pressure_unit_scale():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKPRES1VALUE": "9.93",
        "PM10CHECKPRES2VALUE": "9.96",
        "PM10CHECKPRES3VALUE": "-0.03",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_PRESSURE_UNIT_MISMATCH" in _issue_ids(issues)


def test_pm_pressure_accepts_user_sample_temperature_and_pressure_values():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKTEMP1VALUE": "32.11",
        "PM10CHECKTEMP2VALUE": "33.2",
        "PM10CHECKTEMP3VALUE": "-1.1",
        "PM10CHECKPRES1VALUE": "993",
        "PM10CHECKPRES2VALUE": "996",
        "PM10CHECKPRES3VALUE": "-3.0",
        "PM25CHECKTEMP1VALUE": "31.9",
        "PM25CHECKTEMP2VALUE": "33.2",
        "PM25CHECKTEMP3VALUE": "-1.3",
        "PM25CHECKPRES1VALUE": "995.1",
        "PM25CHECKPRES2VALUE": "996",
        "PM25CHECKPRES3VALUE": "-0.9",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_TEMP_ERROR_MISMATCH" not in _issue_ids(issues)
    assert "RF_PM_PRESSURE_ERROR_MISMATCH" not in _issue_ids(issues)
    assert "RF_PM_TEMP_ERROR_OUT_OF_RANGE" not in _issue_ids(issues)
    assert "RF_PM_PRESSURE_ERROR_OUT_OF_RANGE" not in _issue_ids(issues)


def test_pm_pressure_recomputes_temperature_error_fields():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKTEMP1VALUE": "32.11",
        "PM10CHECKTEMP2VALUE": "33.2",
        "PM10CHECKTEMP3VALUE": "1.1",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_TEMP_ERROR_MISMATCH" in _issue_ids(issues)


def test_pm_pressure_flags_temperature_and_pressure_error_out_of_range():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKTEMP1VALUE": "35.5",
        "PM10CHECKTEMP2VALUE": "33.2",
        "PM10CHECKTEMP3VALUE": "2.3",
        "PM10CHECKPRES1VALUE": "980",
        "PM10CHECKPRES2VALUE": "996",
        "PM10CHECKPRES3VALUE": "-16.0",
        "PM25CHECKPRES1VALUE": "99.3",
        "PM25CHECKPRES2VALUE": "100.8",
        "PM25CHECKPRES3VALUE": "-1.5",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_TEMP_ERROR_OUT_OF_RANGE" in _issue_ids(issues)
    assert "RF_PM_PRESSURE_ERROR_OUT_OF_RANGE" in _issue_ids(issues)


def test_pm_pressure_flags_unrecalculable_temperature_or_pressure_error():
    issues: list[Issue] = []
    form = {
        "WORKINGORDERCODE": "CH2605131778663451989",
        "PM10CHECKTEMP1VALUE": "32.1",
        "PM10CHECKTEMP2VALUE": "",
        "PM10CHECKTEMP3VALUE": "-1.1",
    }

    check_rf_pm_pressure_values(_order("CH2605131778663451989"), [("RF_Q_PMPRESSURE", form)], issues)

    assert "RF_PM_TEMP_PRESSURE_ERROR_UNRECALCULABLE" in _issue_ids(issues)
