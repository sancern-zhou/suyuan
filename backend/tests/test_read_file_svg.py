import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.read_file_tool import ReadFileTool


@pytest.mark.asyncio
async def test_read_file_svg_treated_as_text(tmp_path, monkeypatch):
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60">
  <text x="10" y="30">SVG content</text>
</svg>
""",
        encoding="utf-8",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("SVG should not be sent to AnalyzeImageTool")

    monkeypatch.setattr(
        "app.tools.utility.analyze_image_tool.AnalyzeImageTool.execute",
        fail_if_called,
    )

    tool = ReadFileTool()
    result = await tool.execute(path=str(svg_path))

    assert result["success"] is True
    assert result["data"]["type"] == "text"
    assert result["data"]["format"] == "svg"
    assert "SVG content" in result["data"]["content"]
