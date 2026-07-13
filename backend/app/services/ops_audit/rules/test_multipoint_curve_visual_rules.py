import json

from app.services.ops_audit.rules import multipoint_curve_visual_rules as rules
from app.services import ops_work_order_audit_engine as audit_engine
from app.services.ops_audit.rules.multipoint_curve_visual_rules import (
    build_multipoint_curve_visual_tasks,
    run_multipoint_curve_visual_task,
)


def _form(**overrides):
    form = {
        "WORKINGORDERCODE": "CH1",
        "POLLUTANTTYPE": "O3",
        "MCLBZ10": "90",
        "MCLBZ20": "160",
        "MCLBZ40": "240",
        "MCLBZ60": "320",
        "MCLBZ80": "410",
    }
    form.update(overrides)
    return form


def _attachment(filename, *, typecode="RF_Q_GaseousMultipoint_O3"):
    return {
        "refid": "CH1",
        "typecode": typecode,
        "filename": filename,
        "filepath": f"/WebFiles/{filename}",
        "file_url": f"http://example.test/{filename}",
    }


def test_build_tasks_uses_valid_form_concentrations(tmp_path):
    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1", "STATIONID": "1001"},
        [
            (
                "RF_Q_GASEOUSMULTIPOINT_O3",
                _form(MCLBZ20="/", MCLBZ40="无", MCLBZ60="invalid"),
            )
        ],
        [],
        [],
        evidence_dir=tmp_path,
    )

    assert len(tasks) == 1
    assert tasks[0]["form_concentrations"] == [90.0, 410.0]
    assert tasks[0]["pollutant"] == "O3"
    assert tasks[0]["unit"] == "ppb"
    assert tasks[0]["evidence_dir"] == str(tmp_path.resolve())


def test_build_tasks_ignores_non_multipoint_forms(tmp_path):
    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1"},
        [("RF_W_GASEOUSCHECK_O3", _form())],
        [],
        [],
        evidence_dir=tmp_path,
    )

    assert tasks == []


def test_build_tasks_selects_curves_and_excludes_point_and_record_photos(tmp_path):
    attachments = [
        _attachment("梯度图.jpg"),
        _attachment("O3多点曲线.png"),
        _attachment("SO2多点记录表.jpg"),
        _attachment("O3多点90.jpg"),
        _attachment("现场照片.jpg"),
    ]

    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1"},
        [("RF_Q_GASEOUSMULTIPOINT_O3", _form())],
        attachments,
        [],
        evidence_dir=tmp_path,
    )

    assert [item["filename"] for item in tasks[0]["candidate_items"]] == [
        "梯度图.jpg",
        "O3多点曲线.png",
    ]
    assert tasks[0]["candidate_items"][0]["original_path"] == "/WebFiles/梯度图.jpg"


class _Response:
    content = b"image-bytes"

    def raise_for_status(self):
        return None


def _task(tmp_path, candidates):
    return build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1", "STATIONID": "1001"},
        [("RF_Q_GASEOUSMULTIPOINT_O3", _form())],
        candidates,
        [],
        evidence_dir=tmp_path,
    )[0]


def test_issue_review_persists_image_and_emits_report_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(rules.requests, "get", lambda *args, **kwargs: _Response())

    def fake_extract(source, *, provider, task, prompt):
        assert provider == "flow_visual"
        assert task == "multipoint_curve_gradient_review"
        assert "90、160、240、320、410 ppb" in prompt
        assert "升序或降序" in prompt
        assert "不要输出置信度" in prompt
        assert source.startswith(str(tmp_path.resolve()))
        return {
            "status": "success",
            "text": "raw model output",
            "data": {
                "result": "ISSUE_REVIEW",
                "reason_code": "POINT_COUNT_MISMATCH",
                "reason": "表单有5个浓度点，但曲线仅显示3个平台。",
                "observed_summary": "约3个稳定平台。",
            },
        }

    monkeypatch.setattr(rules, "extract_attachment_json", fake_extract)
    issues = []
    run_multipoint_curve_visual_task(_task(tmp_path, [_attachment("O3多点曲线.jpg")]), issues)

    assert len(issues) == 1
    evidence = json.loads(issues[0].evidence)
    assert evidence["report_classification"] == "疑似问题待人工复核"
    assert evidence["needs_manual_review"] is True
    assert evidence["attachment_filename"] == "O3多点曲线.jpg"
    assert evidence["attachment_original_path"] == "/WebFiles/O3多点曲线.jpg"
    assert evidence["attachment_url"] == "http://example.test/O3多点曲线.jpg"
    assert evidence["attachment_local_path"].startswith(str(tmp_path.resolve()))
    assert rules.Path(evidence["attachment_local_path"]).read_bytes() == b"image-bytes"


def test_pass_and_insufficient_evidence_do_not_emit_issue(monkeypatch, tmp_path):
    monkeypatch.setattr(rules.requests, "get", lambda *args, **kwargs: _Response())
    results = iter(
        [
            {
                "status": "success",
                "data": {
                    "result": "PASS",
                    "reason_code": "NONE",
                    "reason": "梯度一致。",
                    "observed_summary": "5个平台。",
                },
            },
            {"status": "error", "error": "图片无法读取"},
        ]
    )
    monkeypatch.setattr(rules, "extract_attachment_json", lambda *args, **kwargs: next(results))

    issues = []
    run_multipoint_curve_visual_task(
        _task(tmp_path, [_attachment("O3多点曲线.jpg"), _attachment("梯度图.jpg")]),
        issues,
    )

    assert issues == []


def test_issue_review_takes_precedence_over_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(rules.requests, "get", lambda *args, **kwargs: _Response())
    results = iter(
        [
            {
                "status": "success",
                "data": {
                    "result": "PASS",
                    "reason_code": "NONE",
                    "reason": "梯度一致。",
                    "observed_summary": "5个平台。",
                },
            },
            {
                "status": "success",
                "data": {
                    "result": "ISSUE_REVIEW",
                    "reason_code": "GRADIENT_MISMATCH",
                    "reason": "平台相对量级与表单不一致。",
                    "observed_summary": "最高平台不足表单量程的一半。",
                },
            },
        ]
    )
    monkeypatch.setattr(rules, "extract_attachment_json", lambda *args, **kwargs: next(results))

    issues = []
    run_multipoint_curve_visual_task(
        _task(tmp_path, [_attachment("O3多点曲线.jpg"), _attachment("梯度图.jpg")]),
        issues,
    )

    assert len(issues) == 1
    assert json.loads(issues[0].evidence)["reason_code"] == "GRADIENT_MISMATCH"


def test_no_curve_and_invalid_model_output_are_insufficient_evidence(monkeypatch, tmp_path):
    issues = []
    run_multipoint_curve_visual_task(_task(tmp_path, []), issues)
    evidence = json.loads(issues[0].evidence)
    assert evidence["report_classification"] == "资料不足待人工复核"
    assert evidence["reason_code"] == "NOT_MULTIPOINT_CURVE"

    monkeypatch.setattr(rules.requests, "get", lambda *args, **kwargs: _Response())
    monkeypatch.setattr(
        rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {"status": "success", "data": {"result": "MAYBE"}},
    )
    invalid_issues = []
    run_multipoint_curve_visual_task(
        _task(tmp_path, [_attachment("O3多点曲线.jpg")]),
        invalid_issues,
    )
    invalid_evidence = json.loads(invalid_issues[0].evidence)
    assert invalid_evidence["report_classification"] == "资料不足待人工复核"
    assert invalid_evidence["reason_code"] == "IMAGE_UNREADABLE"


def _dataset_with_curve():
    return {
        "orders": [
            {
                "WORKINGORDERCODE": "CH1",
                "STATIONID": "1001",
                "DDWORKINGORDERTYPE": "Check",
                "MAINTENANCETYPE": "Quarter",
                "ORDERSTATUS": "Finish",
            }
        ],
        "details": [],
        "attachments": [_attachment("O3多点曲线.jpg")],
        "wo_commonfile": [],
        "stations": [],
        "devices": [],
        "device_history": {},
        "rf_forms": {"RF_Q_GASEOUSMULTIPOINT_O3": [_form()]},
    }


def test_audit_dataset_schedules_multipoint_review_only_when_visual_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(rules.requests, "get", lambda *args, **kwargs: _Response())
    monkeypatch.setattr(
        rules,
        "extract_attachment_json",
        lambda *args, **kwargs: {
            "status": "success",
            "data": {
                "result": "ISSUE_REVIEW",
                "reason_code": "NO_CLEAR_GRADIENT",
                "reason": "没有明显多点梯度。",
                "observed_summary": "曲线接近单一水平。",
            },
        },
    )

    enabled = audit_engine.audit_dataset(
        _dataset_with_curve(),
        enable_visual=True,
        visual_evidence_dir=tmp_path,
    )
    disabled = audit_engine.audit_dataset(
        _dataset_with_curve(),
        enable_visual=False,
        visual_evidence_dir=tmp_path,
    )

    enabled_rules = {issue["rule_id"] for issue in enabled["records"][0]["issues"]}
    disabled_rules = {issue["rule_id"] for issue in disabled["records"][0]["issues"]}
    assert rules.RULE_ID in enabled_rules
    assert rules.RULE_ID not in disabled_rules
