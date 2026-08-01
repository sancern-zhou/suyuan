import pytest

from app.agent.resources.actions import attach_rendered_file
from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService
from app.api import office_routes
from app.tools.resource_declarations import primary_file


@pytest.mark.asyncio
async def test_report_render_attaches_derivative_and_returns_only_receipt(tmp_path):
    service = SessionResourceService.in_memory()
    qmd = tmp_path / "report.qmd"
    html = tmp_path / "report.html"
    qmd.write_text("# Report")
    html.write_text("<h1>Report</h1>")
    declaration = ResourceDeclaration.model_validate(
        primary_file(
            qmd,
            group_key="report:air",
            tool_name="create_report_package",
            role="report",
            renderer="markdown",
            capabilities=("preview", "download", "edit"),
        )
    )
    published = await service.publish_group(
        "session-1", "create", "report:air", [declaration]
    )

    receipt = await attach_rendered_file(
        service,
        session_id="session-1",
        run_id="render",
        group_key="report:air",
        parent_resource_id=published.resources[0].resource_id,
        path=html,
        relation="preview",
        renderer="html",
        tool_name="render_report_html",
    )

    assert set(receipt) == {"success", "resource_version", "changed_resource_ids"}
    assert receipt["resource_version"] == 2
    derivative = await service.get_resource(
        "session-1", receipt["changed_resource_ids"][0]
    )
    assert derivative.parent_resource_id == published.resources[0].resource_id
    assert derivative.relation == "preview"


@pytest.mark.asyncio
async def test_office_edit_publishes_new_group_and_returns_no_preview_url(
    tmp_path, monkeypatch
):
    service = SessionResourceService.in_memory()
    source = tmp_path / "source.docx"
    edited = tmp_path / "edited.docx"
    preview = tmp_path / "edited.pdf"
    source.write_bytes(b"source")
    edited.write_bytes(b"edited")
    preview.write_bytes(b"pdf")
    monkeypatch.setattr(
        office_routes.SessionResourceService,
        "database",
        classmethod(lambda _cls: service),
    )

    publication = await office_routes._publish_office_product(
        session_id="session-1",
        source_path=source,
        output_path=edited,
        tool_name="docx_online_editor",
        renderer="file",
        preview_path=preview,
    )
    receipt = {
        "success": True,
        "resource_version": publication.catalog_version,
        "changed_resource_ids": [
            resource.resource_id for resource in publication.resources
        ],
    }

    assert set(receipt) == {"success", "resource_version", "changed_resource_ids"}
    assert len(receipt["changed_resource_ids"]) == 2
    assert "url" not in str(receipt).lower()
    page = await service.list_resources("session-1")
    assert {resource.relation for resource in page.resources} == {
        "primary",
        "preview",
    }
