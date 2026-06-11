import pytest

import app.tools.utility.present_artifact_tool as present_artifact_tool
from app.services.html_artifact_service import HtmlArtifactService
from app.tools.utility.present_artifact_tool import PresentArtifactTool


@pytest.mark.asyncio
async def test_present_drawio_file_as_downloadable_artifact(tmp_path):
    drawio_path = tmp_path / "diagram.drawio"
    drawio_path.write_text("<mxfile></mxfile>", encoding="utf-8")

    tool = PresentArtifactTool()
    tool.allowed_dirs.append(tmp_path.resolve())

    result = await tool.execute(str(drawio_path))

    assert result["success"] is True
    assert result["data"]["file_type"] == "editable_diagram"
    assert result["artifact"]["format"] == "drawio"
    assert result["artifact"]["kind"] == "editable_diagram"
    assert result["artifact"]["preview_panel"] is False


@pytest.mark.asyncio
async def test_present_artifact_treats_managed_html_index_as_html_artifact(tmp_path, monkeypatch):
    artifact_root = tmp_path / "backend_data_registry" / "html_artifacts"
    artifact_dir = artifact_root / "agent_platform_deck"
    index_path = artifact_dir / "index.html"
    artifact_dir.mkdir(parents=True)
    index_path.write_text("<!doctype html><title>Deck</title>", encoding="utf-8")

    service = HtmlArtifactService(root=artifact_root)
    monkeypatch.setattr(present_artifact_tool, "html_artifact_service", service)

    tool = present_artifact_tool.PresentArtifactTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(index_path), artifact_type="html")

    assert result["success"] is True
    assert result["metadata"]["file_type"] == "html_artifact"
    assert result["data"]["file_type"] == "html_artifact"
    assert result["data"]["file_path"] == str(index_path.resolve())
    assert result["data"]["html_preview"]["html_id"] == "agent_platform_deck"
    assert result["data"]["html_preview"]["html_url"] == "/api/html-artifacts/agent_platform_deck/html"
    assert result["data"]["html_preview"]["file_type"] == "html_artifact"
    assert result["data"]["refs"]["files"] == [
        {
            "path": str(index_path.resolve()),
            "type": "document",
            "format": "html",
            "usage": "artifact",
        }
    ]
    assert result["data"]["refs"]["artifacts"] == [
        {
            "type": "document",
            "kind": "html_artifact",
            "format": "html",
            "file_path": str(index_path.resolve()),
            "file_name": "index.html",
            "title": "agent_platform_deck",
            "preview": {
                "html_url": "/api/html-artifacts/agent_platform_deck/html",
                "file_type": "html_artifact",
                "schema_version": "html_artifact.v1",
            },
        }
    ]
    assert result["refs"] == result["data"]["refs"]
    assert result["llm_resume"] == {
        "file_path": str(index_path.resolve()),
        "tool_hint": f"Use present_artifact(file_path='{index_path.resolve()}') to preview this artifact.",
    }
