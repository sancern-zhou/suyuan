import json

import pytest

from app.tools import create_global_tool_registry
from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool


def test_only_create_pptx_with_ppt_master_is_registered():
    registry = create_global_tool_registry()

    assert registry.get_tool("create_pptx_with_ppt_master") is not None
    assert registry.get_tool("revise_pptx_with_ppt_master") is None


def test_create_pptx_schema_exposes_operation_enum():
    schema = CreatePptxWithPptMasterTool().get_function_schema()

    operation = schema["parameters"]["properties"]["operation"]
    assert operation["enum"] == ["create", "append", "replace", "patch", "render"]
    assert "operation" not in schema["parameters"].get("required", [])


@pytest.mark.asyncio
async def test_create_pptx_append_operation_inserts_batch_slides(tmp_path, monkeypatch):
    base_plan_path = tmp_path / "slide_plan.v1.json"
    base_plan_path.write_text(
        json.dumps(
            [
                {"slide": 1, "layout": "cover_statement", "title": "Base", "points": []},
                {"slide": 2, "layout": "agent_shape_plan", "title": "Existing", "shapes": []},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "out.pptx"
    project_dir = tmp_path / "project"

    def fake_render_pptx(self, output_path, title, page_plan, palette):
        output_path.write_bytes(b"fake pptx")

    monkeypatch.setattr(CreatePptxWithPptMasterTool, "_render_pptx", fake_render_pptx)

    result = await CreatePptxWithPptMasterTool().execute(
        operation="append",
        base_plan_path=str(base_plan_path),
        batch_slides=[{"title": "Appended", "shapes": []}],
        after_slide=2,
        output_file=str(output_path),
        project_dir=str(project_dir),
        enable_preview=False,
        run_validation=False,
        quality="draft",
    )

    assert result["success"] is True
    assert result["data"]["operation"] == "append"
    assert result["data"]["slide_count"] == 3
    assert [page["title"] for page in result["data"]["page_plan"]] == [
        "Base",
        "Existing",
        "Appended",
    ]
    assert result["data"]["next_revision_base_plan_path"] == result["data"]["slide_plan_path"]


@pytest.mark.asyncio
async def test_create_pptx_render_operation_refreshes_existing_pptx_preview(
    tmp_path, monkeypatch
):
    pptx_path = tmp_path / "existing.pptx"
    pptx_path.write_bytes(b"fake pptx")

    async def fake_pdf_preview(path):
        return {"pdf_url": "/api/file/existing.pdf", "pdf_path": path}

    class FakePdfConverter:
        async def convert_to_pdf(self, path):
            return await fake_pdf_preview(path)

    class FakeValidatePptxTool:
        async def execute(self, path, **kwargs):
            return {
                "success": True,
                "data": {
                    "pptx_path": path,
                    "pages": [{"slide": 1, "png_path": str(tmp_path / "page-001.png")}],
                    "montage_path": str(tmp_path / "montage.png"),
                },
            }

    import app.services.pdf_converter as pdf_converter_module
    import app.tools.office.ppt_master_tool as ppt_master_tool

    monkeypatch.setattr(pdf_converter_module, "pdf_converter", FakePdfConverter())
    monkeypatch.setattr(ppt_master_tool, "ValidatePptxTool", FakeValidatePptxTool, raising=False)

    result = await CreatePptxWithPptMasterTool().execute(
        operation="render",
        file_path=str(pptx_path),
        run_validation=True,
    )

    assert result["success"] is True
    assert result["data"]["operation"] == "render"
    assert result["data"]["file_path"] == str(pptx_path.resolve())
    assert result["data"]["pdf_preview"]["pdf_url"] == "/api/file/existing.pdf"
    assert result["data"]["ppt_preview"]["pages"][0]["slide"] == 1
