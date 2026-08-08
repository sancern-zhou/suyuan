from app.tools.artifact_utils import attach_document_resources, build_artifact_resume_context


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
