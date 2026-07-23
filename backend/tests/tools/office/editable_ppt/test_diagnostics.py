import json

import pytest

from app.tools.office.editable_ppt.diagnostics import PptDiagnosticBuilder


@pytest.fixture
def project_dir(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    (project / "deck.json").write_text(
        json.dumps(
            {
                "slides": [
                    {"id": "cover", "source": "slides/slide-001.js"},
                    {"id": "air-chart", "source": "slides/slide-002.js"},
                    {"id": "station-chart", "source": "slides/slide-003.js"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return project


def two_issue_result(reverse=False, duration=100):
    issues = [
        {
            "code": "ELEMENT_OVERFLOW",
            "page": 2,
            "slideId": "air-chart",
            "sourceId": "pollutant-bar-chart",
            "message": "outside viewport",
            "box": {"x": 200, "y": 280, "width": 1240, "height": 600},
        },
        {
            "code": "ELEMENT_OVERFLOW",
            "page": 3,
            "slideId": "station-chart",
            "sourceId": "station-bar-chart",
            "message": "outside viewport",
            "box": {"x": 200, "y": 280, "width": 1240, "height": 600},
        },
    ]
    if reverse:
        issues.reverse()
    return {
        "success": False,
        "error": "SLIDE_MEASUREMENT_GATE_FAILED",
        "report": {"slideCount": 3, "durationMs": duration, "issues": issues},
    }


def one_issue(element_id):
    return {
        "success": False,
        "issues": [
            {
                "code": "ELEMENT_OVERFLOW",
                "page": 2,
                "slideId": "air-chart",
                "sourceId": element_id,
                "message": "outside viewport",
            }
        ],
    }


def test_build_keeps_every_issue_and_maps_sources(project_dir):
    diagnostic = PptDiagnosticBuilder(project_dir).build(
        operation="compile",
        raw=two_issue_result(),
        report_ref=".editable-ppt/reports/r.json",
        previous=None,
    )

    assert diagnostic["issue_count"] == 2
    assert [item["source_path"] for item in diagnostic["issues"]] == [
        "slides/slide-002.js",
        "slides/slide-003.js",
    ]
    assert diagnostic["groups"] == [
        {
            "code": "ELEMENT_OVERFLOW",
            "count": 2,
            "pages": [2, 3],
            "likely_cause": "嵌套绝对定位或元素尺寸造成页面越界",
        }
    ]
    assert diagnostic["issues"][0]["measured_box"]["y"] == 280
    assert diagnostic["issues"][0]["evidence_ref"]["report_ref"].endswith("r.json")


def test_unknown_issue_shape_is_preserved_as_generic_diagnostic(project_dir):
    raw_issue = {
        "kind": "new_compiler_problem",
        "details": {"path": "x.y"},
        "message": "new",
    }
    diagnostic = PptDiagnosticBuilder(project_dir).build(
        operation="render",
        raw={"success": False, "issues": [raw_issue]},
        report_ref=".editable-ppt/reports/r.json",
        previous=None,
    )

    assert diagnostic["issue_count"] == 1
    assert diagnostic["issues"][0]["raw_issue"] == raw_issue
    assert diagnostic["issues"][0]["code"] == "new_compiler_problem"
    assert diagnostic["issues"][0]["source_path"] is None


def test_issue_without_any_code_is_not_silently_dropped(project_dir):
    raw_issue = {"details": {"path": "x.y"}, "message": "new"}
    diagnostic = PptDiagnosticBuilder(project_dir).build(
        "render", {"issues": [raw_issue]}, ".editable-ppt/reports/r.json", None
    )

    assert diagnostic["issues"][0]["code"] == "UNKNOWN_PPT_ISSUE"
    assert diagnostic["issues"][0]["raw_issue"] == raw_issue


def test_fingerprint_ignores_order_report_ref_timing_and_revision(project_dir):
    builder = PptDiagnosticBuilder(project_dir)
    first = builder.build(
        "compile",
        two_issue_result(reverse=False, duration=100),
        ".editable-ppt/reports/one.json",
        previous=None,
    )
    second = builder.build(
        "compile",
        two_issue_result(reverse=True, duration=900),
        ".editable-ppt/reports/two.json",
        previous=first,
    )

    assert first["fingerprint"] == second["fingerprint"]
    assert second["status"] == "unchanged"


def test_status_transitions_cover_new_changed_unchanged_and_resolved(project_dir):
    builder = PptDiagnosticBuilder(project_dir)
    first = builder.build("compile", one_issue("a"), "r1.json", previous=None)
    changed = builder.build("compile", one_issue("b"), "r2.json", previous=first)
    unchanged = builder.build("compile", one_issue("b"), "r3.json", previous=changed)
    resolved = builder.build(
        "compile",
        {"success": True, "report": {"issues": []}},
        "r4.json",
        previous=unchanged,
    )

    assert [
        first["status"],
        changed["status"],
        unchanged["status"],
        resolved["status"],
    ] == ["new", "changed", "unchanged", "resolved"]


def test_recommended_action_lists_each_source_once(project_dir):
    builder = PptDiagnosticBuilder(project_dir)
    diagnostic = builder.build(
        "compile", two_issue_result(), ".editable-ppt/reports/r.json", previous=None
    )

    assert builder.recommended_action(diagnostic) == {
        "action": "read_sources",
        "source_paths": ["slides/slide-002.js", "slides/slide-003.js"],
    }


def test_project_level_page_count_issue_maps_to_deck(project_dir):
    diagnostic = PptDiagnosticBuilder(project_dir).build(
        "compile",
        {
            "success": False,
            "issues": [
                {
                    "code": "REQUESTED_PAGE_COUNT_MISMATCH",
                    "message": "要求 10 页，当前 9 页",
                    "sourcePath": "deck.json",
                    "expected": 10,
                    "actual": 9,
                }
            ],
        },
        ".editable-ppt/reports/r.json",
        previous=None,
    )

    issue = diagnostic["issues"][0]
    assert issue["source_path"] == "deck.json"
    assert issue["expected"] == 10
    assert issue["actual"] == 9
