import json

import pytest

from app.services.ops_audit.rules import attachment_ocr_rules
from app.services.ops_audit.rules.rf_time_rules import check_rf_time_ranges
from app.services.ops_work_order_audit_engine import audit_dataset


MULTIPOINT_RULE = "RF_MULTIPOINT_DURATION_TOO_SHORT"
CLEANING_RULE = "ATTACHMENT_TW_CLEANING_PHOTO_TIME_OUTSIDE_MAINTENANCE"


@pytest.mark.parametrize(
    ("end_time", "expected_issue"),
    [
        ("2026-09-20 10:06:59", True),
        ("2026-09-20 10:07:00", False),
        ("2026-09-20 10:08:00", False),
        (None, False),
    ],
)
def test_multipoint_each_point_requires_at_least_seven_minutes(end_time, expected_issue):
    issues = []
    form = {"LINGDIANSDTDATE": "2026-09-20 10:00:00", "LINGDIANEDTDATE": end_time}

    check_rf_time_ranges({"WORKINGORDERCODE": "WO-1"}, [("RF_Q_GASEOUSMULTIPOINT_CO", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == MULTIPOINT_RULE]
    assert bool(matched) is expected_issue
    if matched:
        assert json.loads(matched[0].evidence)["point"] == "零点"


def test_multipoint_checks_each_concentration_without_other_tables():
    issues = []
    form = {
        "MCLSDTDATE40": "2026-09-20 10:00:00",
        "MCLEDTDATE40": "2026-09-20 10:06:00",
        "MCLSDTDATE80": "2026-09-20 10:07:00",
        "MCLEDTDATE80": "2026-09-20 10:14:00",
    }

    check_rf_time_ranges({}, [("RF_Q_GASEOUSMULTIPOINT_O3", form), ("RF_HY_O3VALUEPASS", form)], issues)

    matched = [issue for issue in issues if issue.rule_id == MULTIPOINT_RULE]
    assert len(matched) == 1
    assert json.loads(matched[0].evidence)["point"] == "40%"


def _cleaning_task():
    order = {"WORKINGORDERCODE": "WO-CLEAN", "DDWORKINGORDERTYPE": "Check", "MAINTENANCETYPE": "TwoWeek"}
    forms = [("RF_TW_CleanCuttingHead", {"WORKINGORDERCODE": "WO-CLEAN"})]
    details = [{
        "PROCESSSTEP": "CheckOrder",
        "PROCESSSTARTDATETIME": "2026-09-20 10:00:00",
        "PROCESSENDDATETIME": "2026-09-20 11:00:00",
    }]
    photos = [{
        "TYPECODE": "RF_TW_CleanCuttingHeadPM10",
        "FILENAME": "切割头清洗后.jpg",
        "FILEPATH": "/WebFiles/cleaning.jpg",
    }]
    return order, forms, details, photos


def test_cleaning_photo_tasks_require_matching_form_window_and_photo():
    order, forms, details, photos = _cleaning_task()

    tasks = attachment_ocr_rules.build_two_week_cleaning_photo_tasks(order, forms, details, [], photos)

    assert len(tasks) == 1
    assert tasks[0]["windows"][0][0].isoformat(sep=" ") == "2026-09-20 10:00:00"
    assert not attachment_ocr_rules.build_two_week_cleaning_photo_tasks(
        {**order, "MAINTENANCETYPE": "Month"}, forms, details, [], photos
    )
    assert not attachment_ocr_rules.build_two_week_cleaning_photo_tasks(order, forms, [], [], photos)


@pytest.mark.parametrize(
    ("captured_at", "confidence", "expected_issue"),
    [
        ("2026-09-20 09:59:59", 0.95, True),
        ("2026-09-20 10:00:00", 0.95, False),
        ("2026-09-20 11:00:00", 0.95, False),
        ("2026-09-20 11:00:01", 0.95, True),
        ("2026-09-20 11:00:01", 0.80, False),
        (None, 0.95, False),
    ],
)
def test_cleaning_photo_capture_time_must_be_in_maintenance_window(
    monkeypatch, captured_at, confidence, expected_issue
):
    order, forms, details, photos = _cleaning_task()
    task = attachment_ocr_rules.build_two_week_cleaning_photo_tasks(order, forms, details, [], photos)[0]
    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {
            "status": "success",
            "data": {"watermark_datetime": captured_at, "watermark_confidence": confidence},
        },
    )
    issues = []

    attachment_ocr_rules.run_flow_visual_task(task, issues)

    assert bool([issue for issue in issues if issue.rule_id == CLEANING_RULE]) is expected_issue


def test_multipoint_short_duration_reaches_deterministic_audit_results():
    order = {"WORKINGORDERCODE": "WO-1", "DDWORKINGORDERTYPE": "Check", "MAINTENANCETYPE": "Quarter"}
    dataset = {
        "orders": [order],
        "details": [],
        "rf_forms": {"RF_Q_GASEOUSMULTIPOINT_SO2": [{
            "WORKINGORDERCODE": "WO-1",
            "MCLSDTDATE20": "2026-09-20 10:00:00",
            "MCLEDTDATE20": "2026-09-20 10:06:00",
        }]},
        "attachments": [],
        "wo_commonfile": [],
        "devices": [],
    }

    audit = audit_dataset(dataset, enable_visual=False)

    assert MULTIPOINT_RULE in {issue["rule_id"] for issue in audit["records"][0]["deterministic_issues"]}


def test_cleaning_photo_time_issue_reaches_audit_results(monkeypatch):
    order, forms, details, photos = _cleaning_task()
    monkeypatch.setattr(
        attachment_ocr_rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {
            "status": "success",
            "data": {"watermark_datetime": "2026-09-20 09:30:00", "watermark_confidence": 0.95},
        },
    )
    dataset = {
        "orders": [order],
        "details": [{"WORKINGORDERCODE": "WO-CLEAN", **detail} for detail in details],
        "rf_forms": {forms[0][0]: [forms[0][1]]},
        "attachments": [],
        "wo_commonfile": [{"REFID": "WO-CLEAN", **photo} for photo in photos],
        "devices": [],
    }

    audit = audit_dataset(dataset, enable_visual=True)

    assert CLEANING_RULE in {issue["rule_id"] for issue in audit["records"][0]["candidate_issues"]}
