from pathlib import Path

import pytest

from app.tools.utility import publish_session_file_tool
from app.tools.utility.publish_session_file_tool import PublishSessionFileTool


@pytest.mark.asyncio
async def test_publish_session_file_spreadsheet_uses_editable_preview_without_pdf(monkeypatch, tmp_path: Path):
    excel_path = tmp_path / "workbook.xlsx"
    excel_path.write_bytes(b"xlsx-bytes")

    async def fail_convert_to_pdf(path: str):
        raise AssertionError("Excel artifacts should not be converted to PDF")

    monkeypatch.setattr(
        publish_session_file_tool.pdf_converter,
        "convert_to_pdf",
        fail_convert_to_pdf,
    )

    result = await PublishSessionFileTool().execute(str(excel_path))

    assert result["success"] is True
    data = result["data"]
    assert data["file_type"] == "spreadsheet"
    assert data["file_path"] == str(excel_path)
    assert "pdf_preview" not in data
    assert result["resources"][0]["renderer"] == "spreadsheet"
    assert set(result["resources"][0]["capabilities"]) == {"preview", "download", "edit"}
    assert data["preview_available"] is True
