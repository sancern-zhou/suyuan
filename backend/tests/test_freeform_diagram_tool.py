from pathlib import Path

import pytest

from app.tools.visualization.create_diagram_artifact.tool import CreateDiagramArtifactTool


@pytest.mark.asyncio
async def test_create_diagram_artifact_freeform_returns_editable_files():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="test_freeform_canvas",
        title="自由画布测试",
        diagram_mode="freeform",
        diagram_intent="process",
        canvas={"width": 900, "height": 500},
        shapes=[
            {"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 100},
            {
                "id": "judge",
                "type": "diamond",
                "label": "判断",
                "x": 320,
                "y": 90,
                "width": 120,
                "height": 100,
            },
        ],
        connectors=[{"id": "edge_start_judge", "from": "start", "to": "judge", "label": "进入"}],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    assert Path(data["drawio_path"]).exists()
    assert Path(data["source_json_path"]).exists()
    assert Path(data["static_image_path"]).exists()
    assert data["metadata"]["diagram_mode"] == "freeform"
    formats = {artifact["format"] for artifact in data["artifacts"]}
    assert {"drawio", "png"}.issubset(formats)
