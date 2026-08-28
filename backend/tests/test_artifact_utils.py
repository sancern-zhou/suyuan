import app.services.report_preview_refresh as report_preview_refresh
from app.tools.artifact_utils import (
    attach_document_resources,
    attach_rendered_qmd_report_resources,
    build_artifact_resume_context,
)


def test_attach_document_resources_adds_unified_resources(tmp_path):
    report_path = tmp_path / "report.qmd"
    result_data = {"html_preview": {"html_url": "/api/reports/demo/html"}}

    attach_document_resources(
        result_data,
        report_path,
        kind="report",
        format="qmd",
        title="Demo Report",
        generator="create_report_package",
    )

    primary = result_data["resources"][0]
    assert primary["relation"] == "primary"
    assert primary["format"] == "qmd"
    assert set(primary["capabilities"]) == {"preview", "download", "render"}
    assert "llm_resume" not in result_data

    resume_context = build_artifact_resume_context(result_data, report_path)
    assert resume_context == {
        "resources": result_data["resources"],
        "llm_resume": {
            "artifact_path": str(report_path),
            "artifact_format": "qmd",
            "tool_hint": "Artifact preview and download resources are published automatically.",
        },
    }


def test_build_artifact_resume_context_keeps_extra_resume_fields(tmp_path):
    pptx_path = tmp_path / "deck.pptx"
    result_data = {}

    attach_document_resources(result_data, pptx_path, format="pptx", kind="office")

    context = build_artifact_resume_context(
        result_data,
        pptx_path,
        extra_resume={"project_dir": str(tmp_path / "project")},
    )

    assert context["llm_resume"] == {
        "artifact_path": str(pptx_path),
        "artifact_format": "pptx",
        "tool_hint": "Artifact preview and download resources are published automatically.",
        "project_dir": str(tmp_path / "project"),
    }


def test_attach_rendered_qmd_report_resources_publishes_report_package(tmp_path, monkeypatch):
    source = tmp_path / "运维工单审核报告.qmd"
    source.write_text("# Report", encoding="utf-8")
    report_dir = tmp_path / "reports" / "source_qmd_demo"
    package_qmd = report_dir / "report.qmd"
    package_html = report_dir / "report.html"
    package_qmd.parent.mkdir(parents=True)
    package_qmd.write_text("# Report", encoding="utf-8")
    package_html.write_text("<h1>Report</h1>", encoding="utf-8")

    monkeypatch.setattr(
        report_preview_refresh, "refresh_report_preview_for_qmd_path", lambda _path: None
    )
    monkeypatch.setattr(
        report_preview_refresh,
        "create_report_preview_for_source_qmd_path",
        lambda _path: {
            "report_id": "source_qmd_demo",
            "html_preview": {"html_path": str(package_html)},
        },
    )
    data = {}

    attached = attach_rendered_qmd_report_resources(
        data, source, generator="execute_python"
    )

    assert attached is True
    assert data["report_id"] == "source_qmd_demo"
    primary, preview = data["resources"]
    assert primary["resource_key"] == "qmd"
    assert primary["relation"] == "primary"
    assert primary["group_key"] == "report:source_qmd_demo"
    assert "render" in primary["capabilities"]
    assert primary["label"] == source.name
    assert preview["resource_key"] == "html"
    assert preview["relation"] == "preview"
    assert preview["renderer"] == "html"
    assert preview["parent_key"] == "qmd"


def test_attach_rendered_qmd_report_resources_keeps_fallback_on_render_error(
    tmp_path, monkeypatch
):
    source = tmp_path / "draft.qmd"
    source.write_text("# Report", encoding="utf-8")

    monkeypatch.setattr(
        report_preview_refresh, "refresh_report_preview_for_qmd_path", lambda _path: None
    )
    monkeypatch.setattr(
        report_preview_refresh,
        "create_report_preview_for_source_qmd_path",
        lambda _path: {"render_error": "quarto unavailable"},
    )
    data = {}

    attached = attach_rendered_qmd_report_resources(
        data, source, generator="execute_python"
    )

    assert attached is False
    assert data["preview_error"] == "quarto unavailable"
    assert "resources" not in data


def test_attach_rendered_qmd_report_resources_survives_refresh_exception(
    tmp_path, monkeypatch
):
    source = tmp_path / "draft.qmd"
    source.write_text("# Report", encoding="utf-8")

    def _raise(_path):
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(
        report_preview_refresh, "refresh_report_preview_for_qmd_path", _raise
    )
    data = {}

    attached = attach_rendered_qmd_report_resources(
        data, source, generator="execute_python"
    )

    assert attached is False
    assert data["preview_error"] == "renderer crashed"
    assert "resources" not in data
