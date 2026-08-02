from app.agent.resources.contracts import ResourceDeclaration
from app.tools.artifact_utils import attach_document_artifact
from app.tools.office.validate_pptx_tool import validation_output_resources


def validate(resources):
    return [ResourceDeclaration.model_validate(resource) for resource in resources]


def test_presentation_qa_outputs_are_one_bound_group(tmp_path):
    pptx = tmp_path / "deck.pptx"
    pdf = tmp_path / "deck.pdf"
    montage = tmp_path / "montage.png"
    page = tmp_path / "page-001.png"
    report = tmp_path / "report.json"
    for path in (pptx, pdf, montage, page, report):
        path.write_bytes(b"content")

    resources = validate(
        validation_output_resources(pptx, [pdf, montage, page, report])
    )
    by_key = {resource.resource_key: resource for resource in resources}

    assert by_key["pptx"].relation.value == "primary"
    assert by_key["pdf"].relation.value == "preview"
    assert by_key["montage"].relation.value == "preview"
    assert by_key["page-001"].relation.value == "attachment"
    assert all(
        resource.parent_key == "pptx"
        for resource in resources
        if resource.resource_key != "pptx"
    )
    assert len({resource.group_key for resource in resources}) == 1


def test_report_source_and_html_preview_share_a_group(tmp_path):
    qmd = tmp_path / "report.qmd"
    html = tmp_path / "report.html"
    qmd.write_text("# Report")
    html.write_text("<h1>Report</h1>")
    data = {}

    attach_document_artifact(
        data,
        qmd,
        kind="report",
        format="qmd",
        title="air",
        generator="create_report_package",
        metadata={"report_id": "air"},
    )
    resources = validate(data["resources"])

    assert [resource.resource_key for resource in resources] == ["qmd", "html"]
    assert resources[0].relation.value == "primary"
    assert resources[1].relation.value == "preview"
    assert resources[1].parent_key == "qmd"
    assert {resource.group_key for resource in resources} == {"report:air"}


def test_html_artifact_has_downloadable_primary_and_directory_preview(tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    index = artifact_dir / "index.html"
    index.write_text("<h1>Artifact</h1>")
    data = {}

    attach_document_artifact(
        data,
        index,
        kind="html_artifact",
        format="html",
        title="demo",
        generator="create_html_artifact",
        metadata={"artifact_id": "demo"},
    )
    primary, preview = validate(data["resources"])

    assert primary.kind.value == "file"
    assert primary.group_key == "html-artifact:demo"
    assert primary.locator.path == str(index.resolve())
    assert {item.value for item in primary.capabilities} == {"preview", "download"}
    assert preview.kind.value == "artifact"
    assert preview.locator.path == str(artifact_dir.resolve())
    assert preview.renderer.value == "html"
    assert preview.metadata == {"entrypoint": "index.html"}
    assert preview.relation.value == "preview"
    assert {item.value for item in preview.capabilities} == {"preview"}


def test_spreadsheet_primary_uses_spreadsheet_renderer(tmp_path):
    workbook = tmp_path / "data.xlsx"
    workbook.write_bytes(b"xlsx")
    data = {}
    attach_document_artifact(
        data,
        workbook,
        kind="office",
        format="xlsx",
        title="data",
        generator="write_file",
    )
    resource = validate(data["resources"])[0]
    assert resource.resource_key == "xlsx"
    assert resource.renderer.value == "spreadsheet"
    assert "edit" in {capability.value for capability in resource.capabilities}
