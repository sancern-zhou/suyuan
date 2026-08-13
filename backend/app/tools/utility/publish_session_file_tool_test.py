import pytest
import json

import app.tools.utility.publish_session_file_tool as publish_session_file_tool
from app.services.html_artifact_service import HtmlArtifactService
from app.agent.resources.normalizer import normalize_tool_resources
from app.tools.utility.publish_session_file_tool import PublishSessionFileTool
from app.utils.path_config import PROJECT_ROOT


@pytest.mark.asyncio
async def test_publish_drawio_file_as_downloadable_resource(tmp_path):
    drawio_path = tmp_path / "diagram.drawio"
    drawio_path.write_text("<mxfile></mxfile>", encoding="utf-8")

    tool = PublishSessionFileTool()
    tool.allowed_dirs.append(tmp_path.resolve())

    result = await tool.execute(str(drawio_path))

    assert result["success"] is True
    assert result["data"]["file_type"] == "editable_diagram"
    assert result["resources"][0]["format"] == "drawio"
    assert result["resources"][0]["relation"] == "primary"
    assert "download" in result["resources"][0]["capabilities"]


@pytest.mark.asyncio
async def test_publish_session_file_treats_managed_html_index_as_html_artifact(tmp_path, monkeypatch):
    artifact_root = tmp_path / "backend_data_registry" / "html_artifacts"
    artifact_dir = artifact_root / "agent_platform_deck"
    index_path = artifact_dir / "index.html"
    artifact_dir.mkdir(parents=True)
    index_path.write_text("<!doctype html><title>Deck</title>", encoding="utf-8")

    service = HtmlArtifactService(root=artifact_root)
    monkeypatch.setattr(publish_session_file_tool, "html_artifact_service", service)

    tool = publish_session_file_tool.PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(index_path))

    assert result["success"] is True
    assert result["metadata"]["file_type"] == "html_artifact"
    assert result["data"]["file_type"] == "html_artifact"
    assert result["data"]["file_path"] == str(index_path.resolve())
    assert "html_preview" not in result["data"]
    assert result["resources"][0]["group_key"] == "html-artifact:agent_platform_deck"
    assert result["resources"][1]["relation"] == "preview"
    assert result["llm_resume"] == {
        "file_path": str(index_path.resolve()),
        "tool_hint": "The file is available through the unified session resource catalog.",
    }


@pytest.mark.asyncio
async def test_publish_session_file_adds_pdf_preview_resource_for_pptx(tmp_path, monkeypatch):
    pptx_path = tmp_path / "deck.pptx"
    pptx_path.write_bytes(b"fake pptx")

    class FakePdfConverter:
        async def convert_to_pdf(self, path):
            pdf_path = tmp_path / "deck.pdf"
            pdf_path.write_bytes(b"fake pdf")
            return {"pdf_path": str(pdf_path)}

    monkeypatch.setattr(publish_session_file_tool, "pdf_converter", FakePdfConverter())

    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(pptx_path))

    assert result["success"] is True
    assert result["data"]["file_type"] == "presentation"
    assert [item["format"] for item in result["resources"]] == ["pptx", "pdf"]
    assert result["resources"][0]["capabilities"] == ["download"]
    assert result["resources"][1]["relation"] == "preview"
    assert result["data"]["preview_available"] is True


@pytest.mark.asyncio
async def test_publish_session_file_rejects_unfinalized_editable_ppt(tmp_path):
    project = tmp_path / "editable_ppt_projects" / "deck"
    pptx_path = project / "build" / "pptx" / "deck.pptx"
    metadata = project / ".editable-ppt"
    pptx_path.parent.mkdir(parents=True)
    metadata.mkdir(parents=True)
    pptx_path.write_bytes(b"stale-pptx")
    (metadata / "state.json").write_text(json.dumps({
        "project_dir": str(project),
        "revision": 2,
        "dirty_slides": ["cover"],
        "hashes": {"deck.json": "new"},
    }), encoding="utf-8")

    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]
    result = await tool.execute(str(pptx_path))

    assert result["success"] is False
    assert result["data"]["issues"][0]["code"] == "EDITABLE_PPT_NOT_FINALIZED"


@pytest.mark.asyncio
async def test_publish_unknown_file_as_download_only_resource(tmp_path):
    archive = tmp_path / "bundle.custom"
    archive.write_bytes(b"opaque")
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(archive), label="交付包")

    assert result["success"] is True
    assert result["resources"][0]["label"] == "交付包"
    assert result["resources"][0]["renderer"] == "file"
    assert result["resources"][0]["capabilities"] == ["download"]
    assert result["data"]["preview_available"] is False
    declarations, rejected = normalize_tool_resources(result=result)
    assert rejected == []
    assert len(declarations) == 1


@pytest.mark.asyncio
async def test_preview_conversion_failure_keeps_original_downloadable(tmp_path, monkeypatch):
    document = tmp_path / "draft.docx"
    document.write_bytes(b"docx")

    class FailingPdfConverter:
        async def convert_to_pdf(self, path):
            raise RuntimeError("converter unavailable")

    monkeypatch.setattr(publish_session_file_tool, "pdf_converter", FailingPdfConverter())
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(document))

    assert result["success"] is True
    assert result["data"]["preview_available"] is False
    assert result["data"]["preview_error"] == "converter unavailable"
    assert result["resources"][0]["capabilities"] == ["download"]


@pytest.mark.asyncio
async def test_publish_session_file_rejects_paths_outside_allowed_roots(tmp_path):
    document = tmp_path / "private.txt"
    document.write_text("secret", encoding="utf-8")
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [PROJECT_ROOT.resolve()]

    result = await tool.execute(str(document))

    assert result["success"] is False
    assert "超出允许目录范围" in result["error"]
