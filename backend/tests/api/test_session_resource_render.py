import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService
from app.api import session_resource_routes
from app.tools.resource_declarations import primary_file


class WritableCatalog:
    async def require_write(self, session_id, user):
        return object()


@pytest.mark.asyncio
async def test_qmd_render_action_attaches_downloadable_docx(monkeypatch, tmp_path):
    report_dir = tmp_path / "reports" / "air-quality"
    report_dir.mkdir(parents=True)
    qmd = report_dir / "report.qmd"
    qmd.write_text("# Report", encoding="utf-8")
    docx = report_dir / "report.docx"
    docx.write_bytes(b"docx")

    service = SessionResourceService.in_memory()
    published = await service.publish_group(
        "session-1",
        "create",
        "report:air-quality",
        [
            ResourceDeclaration.model_validate(
                primary_file(
                    qmd,
                    group_key="report:air-quality",
                    tool_name="create_report_package",
                    role="report",
                    renderer="markdown",
                    capabilities=("preview", "download", "render"),
                )
            )
        ],
    )
    primary = published.resources[0]
    monkeypatch.setattr(
        session_resource_routes.SessionResourceService,
        "database",
        classmethod(lambda cls: service),
    )
    monkeypatch.setattr(
        session_resource_routes.quarto_report_renderer,
        "report_root",
        tmp_path / "reports",
    )
    monkeypatch.setattr(
        session_resource_routes.quarto_report_renderer,
        "render_docx",
        lambda report_id: docx,
    )

    receipt = await session_resource_routes.render_session_resource(
        "session-1",
        primary.resource_id,
        session_resource_routes.RenderResourceRequest(format="docx"),
        user=object(),
        catalog=WritableCatalog(),
    )

    rendition = await service.get_resource(
        "session-1", receipt["changed_resource_ids"][0]
    )
    assert rendition.relation == "rendition"
    assert rendition.parent_resource_id == primary.resource_id
    assert rendition.format == "docx"
    assert rendition.capabilities == ["download"]
    assert rendition.label == "report.docx"


@pytest.mark.asyncio
async def test_qmd_primary_dto_exposes_render_action(tmp_path):
    qmd = tmp_path / "report.qmd"
    qmd.write_text("# Report", encoding="utf-8")
    service = SessionResourceService.in_memory()
    published = await service.publish_group(
        "session-1",
        "create",
        "report:test",
        [
            ResourceDeclaration.model_validate(
                primary_file(
                    qmd,
                    group_key="report:test",
                    tool_name="create_report_package",
                    role="report",
                    renderer="markdown",
                    capabilities=("preview", "download", "render"),
                )
            )
        ],
    )
    dto = session_resource_routes.resource_dto("session-1", published.resources[0])
    assert dto["actions"]["render"].endswith(
        f"/resources/{published.resources[0].resource_id}/render"
    )
