"""组分站水印一致性试点单测（阶段 2.3，视觉调用全部 mock）。"""

import json
import os
from unittest.mock import patch

import pytest

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules import sup_watermark_rules
from app.services.ops_audit.rules.sup_watermark_rules import (
    WATERMARK_READ_FAILED_RULE_ID,
    WATERMARK_RULE_ID,
    build_sup_watermark_tasks,
    run_sup_watermark_task,
)


def _order(code="CH_WM_01", checkdate="2026-09-28 00:00:00"):
    return {"WORKINGORDERCODE": code, "CHECKDATE": checkdate}


def _form(**kw):
    form = {
        "WORKINGORDERCODE": "CH_WM_01",
        "RULEITEMTAG": "Sup_RF_Week_NMHCQC",
        "POLLUTANTTYPE": "NMHC",
        "CHECKDATE": "2026-09-28 00:00:00",
    }
    form.update(kw)
    return ("SUP_RF_COMMON", form)


def _photo(typecode="Sup_RF_Week_NMHCQC_NMHC", filename="单点.jpg", source="/WebFiles/x/单点.jpg"):
    return {"TYPECODE": typecode, "FILENAME": filename, "FILEPATH": source}


STATION = {"station_id": "23", "station_name": "博罗石下", "latitude": None, "longitude": None}


def _vision_result(data):
    return {"status": "success", "data": data}


# ---------------------------------------------------------------------------
# 任务构建
# ---------------------------------------------------------------------------


def test_build_tasks_skips_when_watermark_check_disabled():
    with patch.object(sup_watermark_rules, "SUP_FORM_PROFILES", {"form_profiles": {}, "defaults": {}}):
        tasks = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)
    assert tasks == []


def test_build_tasks_triggered_by_prior_issues_bypasses_sampling():
    tasks = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "sup_watermark"
    assert tasks[0]["checkdate"] == "2026-09-28 00:00:00"


def test_sampling_is_deterministic_and_excludable():
    """同工单号抽样判定跨次运行一致；rate=0 全跳过、rate=1 全命中。"""

    code = "CH_WM_SAMPLE"
    first = build_sup_watermark_tasks(_order(code), [_form()], [], [_photo()], STATION, has_prior_issues=False)
    second = build_sup_watermark_tasks(_order(code), [_form()], [], [_photo()], STATION, has_prior_issues=False)
    assert (len(first) > 0) == (len(second) > 0)
    with patch.dict(os.environ, {"OPS_AUDIT_SUP_WATERMARK_SAMPLE_RATE": "0"}):
        assert build_sup_watermark_tasks(_order(code), [_form()], [], [_photo()], STATION, has_prior_issues=False) == []
    with patch.dict(os.environ, {"OPS_AUDIT_SUP_WATERMARK_SAMPLE_RATE": "1"}):
        assert len(build_sup_watermark_tasks(_order(code), [_form()], [], [_photo()], STATION, has_prior_issues=False)) == 1


def test_build_tasks_ignores_non_image_and_other_tag_attachments():
    files = [
        _photo(filename="质控数据.xlsx"),
        _photo(typecode="Sup_RF_Week_NMHCQC_HCHO", filename="别的项目.jpg"),
    ]
    tasks = build_sup_watermark_tasks(_order(), [_form()], [], files, STATION, has_prior_issues=True)
    assert tasks == []


def test_build_tasks_caps_photos_per_order():
    files = [_photo(filename=f"照片{i}.jpg", source=f"/WebFiles/x/{i}.jpg") for i in range(5)]
    tasks = build_sup_watermark_tasks(_order(), [_form()], [], files, STATION, has_prior_issues=True)
    assert len(tasks) == 2


# ---------------------------------------------------------------------------
# 水印比对（runner + mock extract_attachment_json）
# ---------------------------------------------------------------------------


def _run(task) -> list[Issue]:
    issues: list[Issue] = []
    run_sup_watermark_task(task, issues)
    return issues


def test_location_mismatch_raises_manual_review_issue():
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"地点": "河源市源城区·河源中学", "经纬度": "23.72N,114.69E", "时间": "2026-09-25 10:00"}),
    ):
        issues = _run(task)
    matched = [i for i in issues if i.rule_id == WATERMARK_RULE_ID]
    assert len(matched) == 1
    assert matched[0].severity == "中"
    evidence = json.loads(matched[0].evidence)
    assert {"location_mismatch"} <= {m["kind"] for m in evidence["mismatches"]}
    assert evidence["needs_manual_review"] is True


def test_consistent_watermark_passes():
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"地点": "博罗县·石下屯村党群服务中心", "经纬度": None, "时间": "2026-09-23 16:28"}),
    ):
        issues = _run(task)
    assert [i for i in issues if i.rule_id == WATERMARK_RULE_ID] == []


def test_city_matching_watermark_passes():
    """站点名与水印无重合、但城市一致时不算地点不符（东城站照片水印=东莞市大气环保体验馆）。"""

    station = {"station_id": "21", "station_name": "东城", "city_name": "东莞市", "address": None}
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], station, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"地点": "东莞市·东莞市大气环保体验馆", "经纬度": None, "时间": "2026-09-25 16:07"}),
    ):
        issues = _run(task)
    assert [i for i in issues if i.rule_id == WATERMARK_RULE_ID] == []


def test_time_outside_window_flags():
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"地点": "博罗县·石下屯村", "经纬度": None, "时间": "2026-09-10 08:00"}),
    ):
        issues = _run(task)
    matched = [i for i in issues if i.rule_id == WATERMARK_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    assert {m["kind"] for m in evidence["mismatches"]} == {"time_outside_window"}


def test_coordinate_mismatch_flags_when_station_coords_available():
    station = {**STATION, "latitude": 23.214, "longitude": 114.025}
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], station, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"地点": "博罗县·石下屯村", "经纬度": "23.72N,114.69E", "时间": None}),
    ):
        issues = _run(task)
    matched = [i for i in issues if i.rule_id == WATERMARK_RULE_ID]
    assert len(matched) == 1
    evidence = json.loads(matched[0].evidence)
    kinds = {m["kind"] for m in evidence["mismatches"]}
    assert "coordinate_mismatch" in kinds


def test_no_watermark_photo_passes():
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value=_vision_result({"无水印": True}),
    ):
        issues = _run(task)
    assert issues == []


def test_read_failure_emits_technical_diagnostic():
    task = build_sup_watermark_tasks(_order(), [_form()], [], [_photo()], STATION, has_prior_issues=True)[0]
    with patch.object(
        sup_watermark_rules,
        "extract_attachment_json",
        return_value={"status": "error", "error": "OCR 请求失败：超时"},
    ):
        issues = _run(task)
    assert [i.rule_id for i in issues] == [WATERMARK_READ_FAILED_RULE_ID]
    evidence = json.loads(issues[0].evidence)
    assert evidence["report_classification"] == "technical_diagnostic"
