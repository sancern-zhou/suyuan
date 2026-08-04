import pytest

from app.agent.resources.normalizer import normalize_tool_resources
from app.tools.utility import publish_session_file_tool
from app.tools.utility.publish_session_file_tool import PublishSessionFileTool
from app.utils import path_config
from app.utils.path_config import PROJECT_ROOT


@pytest.mark.asyncio
async def test_pptx_unified_resource_prefers_pdf_when_both_previews_exist(tmp_path, monkeypatch):
    pptx_path = tmp_path / "deck.pptx"
    pptx_path.write_bytes(b"fake pptx")

    class FakePdfConverter:
        async def convert_to_pdf(self, path):
            preview = tmp_path / "deck.pdf"
            preview.write_bytes(b"pdf")
            return {"pdf_path": str(preview)}

    monkeypatch.setattr(publish_session_file_tool, "pdf_converter", FakePdfConverter())
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(pptx_path))

    assert result["success"] is True
    assert len(result["resources"]) == 2
    assert result["resources"][0]["group_key"].startswith("publish_session_file:file:")
    assert result["resources"][0]["resource_key"] == "primary:pptx"
    assert result["resources"][0]["renderer"] == "file"
    assert result["resources"][1]["renderer"] == "pdf"
    assert result["resources"][1]["relation"] == "preview"


@pytest.mark.asyncio
async def test_unknown_file_is_a_valid_download_only_resource(tmp_path):
    archive = tmp_path / "bundle.custom"
    archive.write_bytes(b"opaque")
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(archive), label="交付包")

    assert result["success"] is True
    assert result["data"]["preview_available"] is False
    assert result["resources"][0]["label"] == "交付包"
    assert result["resources"][0]["renderer"] == "file"
    assert result["resources"][0]["capabilities"] == ["download"]
    declarations, rejected = normalize_tool_resources(result=result)
    assert rejected == []
    assert len(declarations) == 1


@pytest.mark.asyncio
async def test_preview_failure_does_not_block_original_download(tmp_path, monkeypatch):
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


def test_schema_describes_catalog_registration_instead_of_frontend_push():
    schema = PublishSessionFileTool().get_function_schema()

    assert schema["name"] == "publish_session_file"
    assert set(schema["parameters"]["properties"]) == {"file_path", "label"}
    assert "统一会话资源目录" in schema["description"]
    assert "推送到前端" not in schema["description"]


@pytest.mark.asyncio
async def test_relative_path_is_resolved_from_project_root(tmp_path, monkeypatch):
    nested = tmp_path / "outputs"
    nested.mkdir()
    document = nested / "report.pdf"
    document.write_bytes(b"pdf")
    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    tool = PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path]

    result = await tool.execute("outputs/report.pdf")

    assert result["success"] is True
    assert result["data"]["file_path"] == str(document.resolve())
    assert result["resources"][0]["locator"]["path"] == str(document.resolve())
