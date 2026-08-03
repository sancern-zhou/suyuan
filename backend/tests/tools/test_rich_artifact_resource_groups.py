import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.tools.artifact_utils import (
    attach_document_resources,
    attach_report_package_resources,
)
from app.tools.office.validate_pptx_tool import validation_output_resources
from app.tools.report.report_package import tool as report_package_tool
from app.tools.report.report_package.tool import RenderReportPackageTool
from app.tools.utility import edit_file_tool_v2 as edit_file_tool_module
from app.tools.utility import write_file_tool as write_file_tool_module
from app.tools.utility.edit_file_tool_v2 import EditFileToolV2
from app.tools.utility.write_file_tool import WriteFileTool


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

    attach_document_resources(
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


def test_report_renditions_remain_children_of_qmd_primary(tmp_path):
    qmd = tmp_path / "report.qmd"
    html = tmp_path / "report.html"
    docx = tmp_path / "report.docx"
    share_html = tmp_path / "report.export.html"
    qmd.write_text("# Report", encoding="utf-8")
    html.write_text("<h1>Preview</h1>", encoding="utf-8")
    docx.write_bytes(b"docx")
    share_html.write_text("<h1>Export</h1>", encoding="utf-8")
    data = {}

    attach_report_package_resources(
        data,
        qmd,
        report_id="air",
        html_path=html,
        docx_path=docx,
        share_html_path=share_html,
        generator="render_report_package",
    )
    resources = validate(data["resources"])
    by_key = {resource.resource_key: resource for resource in resources}

    assert list(by_key) == ["qmd", "html", "docx", "share_html"]
    assert by_key["qmd"].relation.value == "primary"
    assert by_key["qmd"].format == "qmd"
    assert {item.value for item in by_key["qmd"].capabilities} == {
        "preview",
        "download",
        "render",
    }
    assert by_key["html"].kind.value == "artifact"
    assert by_key["html"].relation.value == "preview"
    assert by_key["html"].metadata == {"entrypoint": "report.html"}
    assert by_key["docx"].relation.value == "rendition"
    assert by_key["docx"].parent_key == "qmd"
    assert by_key["share_html"].relation.value == "rendition"
    assert by_key["share_html"].parent_key == "qmd"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output_format", "expected_keys"),
    [
        ("html", ["qmd", "html"]),
        ("docx", ["qmd", "html", "docx"]),
        ("share_html", ["qmd", "html", "share_html"]),
    ],
)
async def test_render_report_package_keeps_qmd_as_primary(
    tmp_path, monkeypatch, output_format, expected_keys
):
    report_dir = tmp_path / "air"
    report_dir.mkdir()
    qmd = report_dir / "report.qmd"
    html = report_dir / "report.html"
    docx = report_dir / "report.docx"
    share_html = report_dir / "report.export.html"
    qmd.write_text("# Report", encoding="utf-8")
    html.write_text("<h1>Preview</h1>", encoding="utf-8")
    docx.write_bytes(b"docx")
    share_html.write_text("<h1>Export</h1>", encoding="utf-8")

    renderer = report_package_tool.quarto_report_renderer
    monkeypatch.setattr(renderer, "get_report_dir", lambda _report_id: report_dir)
    monkeypatch.setattr(renderer, "render_preview_html", lambda _report_id: html)
    monkeypatch.setattr(renderer, "render_docx", lambda _report_id: docx)
    monkeypatch.setattr(renderer, "render_share_html", lambda _report_id: share_html)
    monkeypatch.setattr(
        report_package_tool,
        "record_report_update",
        lambda *_args, **_kwargs: {"version": 2},
    )

    result = await RenderReportPackageTool().execute("air", output_format)
    resources = result["resources"]

    assert result["success"] is True
    assert [resource["resource_key"] for resource in resources] == expected_keys
    assert resources[0]["relation"] == "primary"
    assert resources[0]["format"] == "qmd"
    assert all(resource["parent_key"] == "qmd" for resource in resources[1:])


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["edit", "write"])
async def test_qmd_file_mutation_publishes_refreshed_report_group(
    tmp_path, monkeypatch, operation
):
    qmd = tmp_path / "report.qmd"
    html = tmp_path / "report.html"
    qmd.write_text("# Original", encoding="utf-8")
    html.write_text("<h1>Preview</h1>", encoding="utf-8")
    refresh_result = {
        "report_id": "air",
        "report_preview_refresh": {
            "success": True,
            "html_path": str(html),
        },
    }

    if operation == "edit":
        monkeypatch.setattr(
            edit_file_tool_module,
            "refresh_preview_for_managed_document_path",
            lambda _path: refresh_result,
        )
        tool = EditFileToolV2()
        tool.read_state.set(
            str(qmd.resolve()),
            content="# Original",
            file_size=len("# Original"),
            encoding="utf-8",
        )
        result = await tool.execute(
            path=str(qmd), old_string="# Original", new_string="# Updated"
        )
    else:
        monkeypatch.setattr(
            write_file_tool_module,
            "refresh_preview_for_managed_document_path",
            lambda _path: refresh_result,
        )
        tool = WriteFileTool()
        tool.read_state.set(
            str(qmd.resolve()),
            content="# Original",
            file_size=len("# Original"),
            encoding="utf-8",
        )
        result = await tool.execute(path=str(qmd), content="# Updated")

    assert result["success"] is True
    assert [item["resource_key"] for item in result["resources"]] == ["qmd", "html"]
    assert result["resources"][0]["relation"] == "primary"
    assert result["resources"][1]["relation"] == "preview"


def test_html_artifact_has_downloadable_primary_and_directory_preview(tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    index = artifact_dir / "index.html"
    index.write_text("<h1>Artifact</h1>")
    data = {}

    attach_document_resources(
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
    attach_document_resources(
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
