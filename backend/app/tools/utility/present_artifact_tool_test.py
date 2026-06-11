import pytest

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
