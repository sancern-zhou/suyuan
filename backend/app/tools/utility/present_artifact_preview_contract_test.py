import pytest

from app.tools.utility import present_artifact_tool
from app.tools.utility.present_artifact_tool import PresentArtifactTool


@pytest.mark.asyncio
async def test_pptx_unified_resource_prefers_pdf_when_both_previews_exist(tmp_path, monkeypatch):
    pptx_path = tmp_path / "deck.pptx"
    pptx_path.write_bytes(b"fake pptx")

    class FakePdfConverter:
        async def convert_to_pdf(self, path):
            return {"pdf_url": "/api/file/deck.pdf", "pdf_path": path}

    class FakeValidatePptxTool:
        async def execute(self, path, **kwargs):
            return {
                "success": True,
                "data": {
                    "pptx_path": path,
                    "pages": [{"slide": 1, "png_path": str(tmp_path / "page-001.png")}],
                    "montage_path": str(tmp_path / "montage.png"),
                    "report_path": str(tmp_path / "report.json"),
                },
            }

    monkeypatch.setattr(present_artifact_tool, "pdf_converter", FakePdfConverter())
    monkeypatch.setattr(present_artifact_tool, "ValidatePptxTool", FakeValidatePptxTool, raising=False)
    tool = PresentArtifactTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(pptx_path))

    assert result["success"] is True
    assert result["data"]["ppt_preview"]["pages"][0]["slide"] == 1
    assert result["resources"][0]["group_key"].startswith("presentation:")
    assert result["resources"][0]["resource_key"] == "pptx"
    assert result["resources"][0]["renderer"] == "presentation"
