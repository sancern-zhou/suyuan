import json

import pytest

from app.tools.office.editable_ppt.report_store import PptReportStore, ReportRefError


def sample_report():
    return {
        "success": False,
        "report": {
            "slideCount": 4,
            "issues": [
                {
                    "code": "ELEMENT_OVERFLOW",
                    "page": 3,
                    "elementId": "chart-a",
                    "message": "overflow",
                    "evidence": {"bottom": 880},
                },
                {
                    "code": "DUPLICATE_ID",
                    "page": 4,
                    "elementId": "title",
                    "message": "duplicate",
                },
            ],
            "measurement": {"screenshots": ["a.png", "b.png"]},
        },
    }


def test_persist_keeps_complete_payload_and_returns_project_relative_ref(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)

    report_ref = store.persist("compile", revision=7, payload=sample_report())

    assert report_ref.startswith(".editable-ppt/reports/compile-rev-7-")
    assert report_ref.endswith(".json")
    assert store.read(report_ref) == sample_report()
    assert json.loads((project / report_ref).read_text(encoding="utf-8")) == sample_report()


def test_persist_is_content_addressed_and_does_not_overwrite_other_payload(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)

    first = store.persist("render", 2, {"pages": [{"page": 1}]})
    second = store.persist("render", 2, {"pages": [{"page": 2}]})

    assert first != second
    assert store.read(first)["pages"][0]["page"] == 1
    assert store.read(second)["pages"][0]["page"] == 2


def test_read_filters_issue_nodes_without_losing_matched_raw_fields(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()
    store = PptReportStore(project)
    ref = store.persist("compile", 7, sample_report())

    filtered = store.read(
        ref,
        pages=[3],
        codes=["ELEMENT_OVERFLOW"],
        element_ids=["chart-a"],
    )

    assert filtered["report_ref"] == ref
    assert filtered["matched_issues"] == [sample_report()["report"]["issues"][0]]
    assert filtered["report_metadata"]["success"] is False
    assert filtered["report_metadata"]["slideCount"] == 4


@pytest.mark.parametrize(
    "report_ref",
    [
        "../secret.json",
        ".editable-ppt/reports/../../secret.json",
        "/tmp/secret.json",
        ".editable-ppt/last_compile.json",
    ],
)
def test_read_rejects_refs_outside_reports_directory(tmp_path, report_ref):
    project = tmp_path / "deck"
    project.mkdir()

    with pytest.raises(ReportRefError, match="reports directory"):
        PptReportStore(project).read(report_ref)


def test_read_rejects_missing_report_inside_reports_directory(tmp_path):
    project = tmp_path / "deck"
    project.mkdir()

    with pytest.raises(ReportRefError, match="does not exist"):
        PptReportStore(project).read(".editable-ppt/reports/missing.json")
