import json

from app.services.ops_audit.rules.rf_calibration_date_rules import check_rf_calibration_dates
from app.services.ops_work_order_audit_engine import audit_dataset


def test_calibration_next_date_allows_interval_within_two_calendar_years():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-05-20 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "SdtTime": "2026-05-20 10:00:00",
        "F_CalibrateDatePrev2": "2025-08-31",
        "F_CalibrateDateNext2": "2027-08-30",
    }

    check_rf_calibration_dates(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_o3_weekly_validity_on_calibration_date_is_still_valid():
    issues = []
    order = {
        "WORKINGORDERCODE": "CH2607161784188194591",
        "STATIONID": "1738",
        "CREATETIME": "2026-07-16 16:05:22",
    }
    form = {
        "WORKINGORDERCODE": "CH2607161784188194591",
        "CALIBRATIONDATE": "2026-07-15 00:00:00",
        "CDDATE": "2026-07-15 00:00:00",
        "YXQDATE": "2026-07-15 00:00:00",
    }

    check_rf_calibration_dates(order, [("RF_W_GASEOUSCHECK_O3", form)], issues)

    assert issues == []


def test_o3_multipoint_without_gas_cylinder_allows_transfer_validity_in_remark():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-O3-NO-CYLINDER-OK",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-06-11 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-O3-NO-CYLINDER-OK",
        "STATIONID": "ST-1",
        "CALIBRATIONDATE": "2026-06-11 10:00:00",
        "PPMCODEDATE": "",
        "REMARKS": "臭氧无标气瓶，臭氧传递浓度有效期至2026-07-05",
    }

    check_rf_calibration_dates(order, [("RF_Q_GASEOUSMULTIPOINT_O3", form)], issues)

    assert issues == []


def test_o3_multipoint_without_gas_cylinder_allows_recent_transfer_date_basis():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-O3-TRANSFER-DATE-OK",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-06-18 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-O3-TRANSFER-DATE-OK",
        "STATIONID": "ST-1",
        "CALIBRATIONDATE": "2026-06-18 10:00:00",
        "PPM": "/",
        "PPMCODE": "/",
        "PPMCODEDATE": "",
        "REMARKS": "校准结果：合格\n臭氧传递日期为：2026年5月10日",
    }

    check_rf_calibration_dates(order, [("RF_Q_GASEOUSMULTIPOINT_O3", form)], issues)

    assert issues == []


def test_o3_multipoint_without_gas_cylinder_allows_empty_validity_without_remark():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-O3-NO-CYLINDER-MISSING",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-06-11 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-O3-NO-CYLINDER-MISSING",
        "STATIONID": "ST-1",
        "CALIBRATIONDATE": "2026-06-11 10:00:00",
        "PPMCODEDATE": "",
        "REMARKS": "臭氧无标气瓶",
    }

    check_rf_calibration_dates(order, [("RF_Q_GASEOUSMULTIPOINT_O3", form)], issues)

    assert issues == []


def test_o3_multipoint_without_gas_cylinder_reports_when_validity_date_is_filled():
    issues = []
    order = {
        "WORKINGORDERCODE": "CH2606111781157359711",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-06-11 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "CH2606111781157359711",
        "STATIONID": "ST-1",
        "CALIBRATIONDATE": "2026-06-11 00:00:00",
        "PPM": "/",
        "PPMCODE": "/",
        "PPMCODEDATE": "2026-06-11 00:00:00",
        "REMARKS": "",
    }

    check_rf_calibration_dates(order, [("RF_Q_GASEOUSMULTIPOINT_O3", form)], issues)

    assert [issue.rule_id for issue in issues] == ["RF_CALIBRATION_DATE_SHOULD_BE_EMPTY"]
    assert "无标气瓶" in issues[0].message
    assert "标气有效期应不填" in issues[0].message


def test_calibration_next_date_must_be_within_two_calendar_years_after_previous_date():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-05-20 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "SdtTime": "2026-05-20 10:00:00",
        "D_CalibrateDatePrev": "2026-05-21",
        "D_CalibrateDateNext": "2028-05-22",
    }

    check_rf_calibration_dates(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_CALIBRATION_INTERVAL_TOO_LONG"
    evidence = json.loads(issues[0].evidence)
    violation = evidence["violations"][0]
    assert violation["label"] == "动态校准仪校准有效期"
    assert violation["prev_time"] == "2026-05-21 00:00:00"
    assert violation["next_time"] == "2028-05-22 00:00:00"
    assert violation["max_next_time"] == "2028-05-21 00:00:00"
    assert violation["reason"] == "interval_over_two_years"


def test_calibration_next_date_allows_two_calendar_year_interval():
    issues = []
    order = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-05-20 09:00:00",
    }
    form = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "SdtTime": "2026-05-20 10:00:00",
        "D_CalibrateDatePrev": "2026-05-21",
        "D_CalibrateDateNext": "2028-05-21",
    }

    check_rf_calibration_dates(order, [("RF_Q_GaseousFlowCheck", form)], issues)

    assert [issue.rule_id for issue in issues] == []


def test_dynamic_calibrator_previous_date_does_not_compare_actual_previous_flow_check_date():
    issues = []
    current_order = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-05-20 09:00:00",
    }
    current_form = {
        "WORKINGORDERCODE": "WO-CURRENT",
        "STATIONID": "ST-1",
        "SdtTime": "2026-05-20 10:00:00",
        "D_CalibrateDatePrev": "2026-02-19",
        "D_CalibrateDateNext": "2026-08-20",
    }
    previous_order = {
        "WORKINGORDERCODE": "WO-PREVIOUS",
        "STATIONID": "ST-1",
        "CREATETIME": "2026-02-20 09:00:00",
    }
    previous_form = {
        "WORKINGORDERCODE": "WO-PREVIOUS",
        "STATIONID": "ST-1",
        "SdtTime": "2026-02-20 10:00:00",
    }

    check_rf_calibration_dates(
        current_order,
        [("RF_Q_GaseousFlowCheck", current_form)],
        issues,
        all_orders=[current_order, previous_order],
        forms_by_code={
            "WO-CURRENT": [("RF_Q_GaseousFlowCheck", current_form)],
            "WO-PREVIOUS": [("RF_Q_GaseousFlowCheck", previous_form)],
        },
    )

    assert [issue.rule_id for issue in issues] == []


def test_audit_dataset_does_not_use_device_history_for_dynamic_calibrator_previous_date_check():
    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-CURRENT",
                "STATIONID": "ST-1",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "CREATETIME": "2026-05-20 09:00:00",
                "FINISHTIME": "2026-05-20 12:00:00",
                "MAINTENANCETYPE": "Quarter",
            }
        ],
        "details": [],
        "attachments": [],
        "wo_commonfile": [],
        "devices": [],
        "stations": [],
        "rf_forms": {
            "RF_Q_GaseousFlowCheck": [
                {
                    "WORKINGORDERCODE": "WO-CURRENT",
                    "STATIONID": "ST-1",
                    "SdtTime": "2026-05-20 10:00:00",
                    "D_CalibrateDatePrev": "2026-02-19",
                    "D_CalibrateDateNext": "2026-08-20",
                }
            ]
        },
        "device_history": {
            "orders": [
                {
                    "WORKINGORDERCODE": "WO-PREVIOUS",
                    "STATIONID": "ST-1",
                    "DDWORKINGORDERTYPE": "Check",
                    "DDWORKINGORDERSTATUS": "Finish",
                    "CREATETIME": "2026-02-20 09:00:00",
                    "MAINTENANCETYPE": "Quarter",
                }
            ],
            "rf_forms": {
                "RF_Q_GaseousFlowCheck": [
                    {
                        "WORKINGORDERCODE": "WO-PREVIOUS",
                        "STATIONID": "ST-1",
                        "SdtTime": "2026-02-20 10:00:00",
                    }
                ]
            },
        },
    }

    result = audit_dataset(dataset)

    record = result["records"][0]
    assert "RF_CALIBRATION_PREV_DATE_MISMATCH" not in record["deterministic_rules"]
