import json
import time

from app.services.ops_audit.rules import attachment_ocr_rules
from app.services.ops_work_order_audit_engine import _run_flow_visual_tasks


def test_flow_visual_rules_run_without_global_ocr_flag(tmp_path, monkeypatch):
    image_path = tmp_path / "flow-photo.jpg"
    image_path.write_bytes(b"fake-image")
    monkeypatch.delenv("OPS_AUDIT_OCR_RULES", raising=False)

    calls = []

    def _fake_extract_attachment_json(source, *, provider=None, task=None, prompt=None):
        calls.append({"source": source, "provider": provider, "task": task, "prompt": prompt})
        return {
            "status": "success",
            "data": {
                "is_flow_calibration_photo": True,
                "before_flow": 16.7,
                "after_flow": None,
                "unit": "L/min",
                "confidence": 0.92,
                "reason": "照片中可见校准前流量读数",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", _fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.check_attachment_ocr_quality(
        {"WORKINGORDERCODE": "WO-1"},
        [("RF_TW_PmFlowCalibrate", {"WORKINGORDERCODE": "WO-1", "Prev_A": "16.0"})],
        [{"FILENAME": "流量校准照片.jpg", "FILEPATH": str(image_path)}],
        [],
        issues,
    )

    assert calls
    assert calls[0]["task"] == "pm_flow_calibration_value"
    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH"
    evidence = json.loads(issues[0].evidence)
    assert evidence["vision_data"]["before_flow"] == 16.7


def test_flow_visual_rules_skip_photo_without_flow_keywords(tmp_path, monkeypatch):
    image_path = tmp_path / "normal-photo.jpg"
    image_path.write_bytes(b"fake-image")

    calls = []

    def _fake_extract_attachment_json(source, *, provider=None, task=None, prompt=None):
        calls.append(source)
        return {"status": "success", "data": {}}

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", _fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.check_attachment_ocr_quality(
        {"WORKINGORDERCODE": "WO-1"},
        [("RF_TW_PmFlowCalibrate", {"WORKINGORDERCODE": "WO-1", "Prev_A": "16.0"})],
        [{"FILENAME": "现场照片.jpg", "FILEPATH": str(image_path)}],
        [],
        issues,
    )

    assert calls == []
    assert issues == []


def test_flow_visual_engine_runs_tasks_concurrently(monkeypatch):
    monkeypatch.setenv("OPS_AUDIT_FLOW_VISUAL_CONCURRENCY", "4")
    monkeypatch.setenv("OPS_AUDIT_FLOW_VISUAL_RPM_LIMIT", "0")

    def _fake_run_flow_visual_task(task, issues):
        time.sleep(0.05)

    monkeypatch.setattr("app.services.ops_work_order_audit_engine.run_flow_visual_task", _fake_run_flow_visual_task)
    tasks = [{"working_order_code": f"WO-{index}", "item": {"filename": f"{index}.jpg"}} for index in range(4)]
    started_at = time.monotonic()

    _run_flow_visual_tasks(tasks, {})

    assert time.monotonic() - started_at < 0.15


def test_pm_temp_pressure_visual_temperature_mismatch_has_no_tolerance(monkeypatch):
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_VISUAL_VALUE_TOLERANCE", raising=False)

    comparisons = attachment_ocr_rules._compare_pm_temp_pressure_value(
        "PM25.temperature_display",
        25.7,
        {"PM25CHECKTEMP1VALUE": "26.7"},
        "PM25CHECKTEMP1VALUE",
    )

    assert comparisons[0]["status"] == "mismatch"
    assert comparisons[0]["difference"] == 1.0


def test_pm_temp_pressure_visual_converts_pressure_mmhg_to_kpa_without_tolerance(monkeypatch):
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)

    comparisons = attachment_ocr_rules._compare_pm_temp_pressure_value(
        "PM10.pressure_display",
        756.1,
        {"PM10CHECKPRES1VALUE": "100.8"},
        "PM10CHECKPRES1VALUE",
    )

    assert comparisons[0]["status"] == "matched"
    assert comparisons[0]["raw_visual_value"] == 756.1
    assert comparisons[0]["visual_unit"] == "mmHg->kPa"
    assert comparisons[0]["visual_value"] == 100.8


def test_pm_temp_pressure_visual_pressure_mismatch_has_no_tolerance(monkeypatch):
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)

    comparisons = attachment_ocr_rules._compare_pm_temp_pressure_value(
        "PM25.pressure_display",
        756.4,
        {"PM25CHECKPRES1VALUE": "100.9"},
        "PM25CHECKPRES1VALUE",
    )

    assert comparisons[0]["status"] == "mismatch"
    assert comparisons[0]["raw_visual_value"] == 756.4
    assert comparisons[0]["visual_unit"] == "mmHg->kPa"
    assert comparisons[0]["visual_value"] == 100.8


def test_pm_temp_pressure_visual_flags_instrument_photo_when_values_differ(tmp_path, monkeypatch):
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    image_path = tmp_path / "PM2.5温压仪器.jpg"
    image_path.write_bytes(b"fake-image")

    def _fake_extract_attachment_json(source, *, provider=None, task=None, prompt=None):
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM25": {
                        "temperature_display": 25.7,
                        "temperature_standard": None,
                        "pressure_display": 756.4,
                        "pressure_standard": None,
                    }
                },
                "confidence": 0.95,
                "reason": "照片中可见PM2.5温压仪器读数",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", _fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.check_attachment_ocr_quality(
        {"WORKINGORDERCODE": "CH2605191779166465941"},
        [
            (
                "RF_Q_PMPRESSURE",
                {
                    "WORKINGORDERCODE": "CH2605191779166465941",
                    "PM25CHECKTEMP1VALUE": "26.7",
                    "PM25CHECKPRES1VALUE": "100.9",
                },
            )
        ],
        [{"FILENAME": "PM2.5温压仪器.jpg", "FILEPATH": str(image_path)}],
        [],
        issues,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH"


def test_pm_temp_pressure_visual_ignores_matched_pm10_instrument_photo(tmp_path, monkeypatch):
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_TEMP_VISUAL_VALUE_TOLERANCE", raising=False)
    monkeypatch.delenv("OPS_AUDIT_PM_PRESSURE_VISUAL_VALUE_TOLERANCE", raising=False)
    image_path = tmp_path / "PM10温压仪器.jpg"
    image_path.write_bytes(b"fake-image")

    def _fake_extract_attachment_json(source, *, provider=None, task=None, prompt=None):
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": True,
                "values": {
                    "PM10": {
                        "temperature_display": 25.8,
                        "temperature_standard": None,
                        "pressure_display": 756.1,
                        "pressure_standard": None,
                    }
                },
                "confidence": 0.95,
                "reason": "照片中AT为25.8C，BP为756.1mmHg",
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", _fake_extract_attachment_json)

    issues = []
    attachment_ocr_rules.check_attachment_ocr_quality(
        {"WORKINGORDERCODE": "CH2605191779166465941"},
        [
            (
                "RF_Q_PMPRESSURE",
                {
                    "WORKINGORDERCODE": "CH2605191779166465941",
                    "PM10CHECKTEMP1VALUE": "25.8",
                    "PM10CHECKPRES1VALUE": "100.8",
                },
            )
        ],
        [{"FILENAME": "PM10温压仪器.jpg", "FILEPATH": str(image_path)}],
        [],
        issues,
    )

    assert issues == []


def test_pm_temp_pressure_visual_prompt_prefers_at_and_excludes_delta(tmp_path, monkeypatch):
    image_path = tmp_path / "PM10温压仪器.jpg"
    image_path.write_bytes(b"fake-image")
    calls = []

    def _fake_extract_attachment_json(source, *, provider=None, task=None, prompt=None):
        calls.append({"prompt": prompt})
        return {
            "status": "success",
            "data": {
                "is_pm_temp_pressure_photo": False,
            },
        }

    monkeypatch.setattr(attachment_ocr_rules, "extract_attachment_json", _fake_extract_attachment_json)

    attachment_ocr_rules.check_attachment_ocr_quality(
        {"WORKINGORDERCODE": "CH2605191779166465941"},
        [("RF_Q_PMPRESSURE", {"WORKINGORDERCODE": "CH2605191779166465941"})],
        [{"FILENAME": "PM10温压仪器.jpg", "FILEPATH": str(image_path)}],
        [],
        [],
    )

    assert calls
    prompt = calls[0]["prompt"]
    assert "AT" in prompt
    assert "优先" in prompt
    assert "Delta" in prompt
    assert "不要" in prompt
