import json

from app.services.ops_audit.rules.rf_calibration_date_rules import check_rf_calibration_dates
from app.services.ops_work_order_audit_engine import audit_dataset


def test_dynamic_calibrator_previous_date_must_match_actual_previous_flow_check_date():
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

    assert len(issues) == 1
    assert issues[0].rule_id == "RF_CALIBRATION_PREV_DATE_MISMATCH"
    evidence = json.loads(issues[0].evidence)
    assert evidence["previous_order_code"] == "WO-PREVIOUS"
    assert evidence["actual_previous_time"] == "2026-02-20 10:00:00"
    assert evidence["filled_previous_time"] == "2026-02-19 00:00:00"


def test_audit_dataset_uses_device_history_for_dynamic_calibrator_previous_date_check():
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
    assert "RF_CALIBRATION_PREV_DATE_MISMATCH" in record["deterministic_rules"]
