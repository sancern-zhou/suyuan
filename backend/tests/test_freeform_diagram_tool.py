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


@pytest.mark.asyncio
async def test_create_diagram_artifact_defaults_to_freeform_for_canvas_payload():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="test_freeform_default_mode",
        title="默认自由画布测试",
        canvas={"width": 900, "height": 500},
        shapes=[
            {"id": "client", "type": "rounded rectangle", "text": "Client", "x": 80, "y": 100},
            {"id": "api", "type": "box", "text": "API", "x": 320, "y": 100},
        ],
        connectors=[{"id": "edge", "source": "client", "target": "api", "text": "HTTPS"}],
        output_formats=["drawio", "png"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["metadata"]["diagram_mode"] == "freeform"
    assert Path(data["drawio_path"]).exists()


@pytest.mark.asyncio
async def test_create_diagram_artifact_keeps_legacy_template_payload_compatible():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="test_template_compat_without_mode",
        title="模板兼容测试",
        diagram_type="layered_architecture",
        layers=[
            {
                "id": "layer",
                "label": "业务层",
                "items": [
                    {"id": "module", "label": "模块", "shape": "rectangle"},
                ],
            }
        ],
        output_formats=["html"],
    )

    assert result["success"] is True
    data = result["data"]
    assert result["metadata"]["layout_engine"] != "freeform_drawio"
    assert "drawio_path" not in data


@pytest.mark.asyncio
async def test_create_diagram_artifact_freeform_validation_failure_is_structured():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="test_freeform_failure",
        title="自由画布失败",
        diagram_mode="freeform",
        shapes=[],
    )

    assert result["success"] is False
    assert result["data"] is None
    assert result["metadata"]["diagram_mode"] == "freeform"
    assert "validation_error" in result["metadata"]
    assert "artifact" not in result
    assert "artifacts" not in result
    assert "visuals" not in result


@pytest.mark.asyncio
async def test_create_diagram_artifact_freeform_uses_sanitized_artifact_id_in_urls_and_html():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="foo/bar canvas",
        title="自由画布路径测试",
        diagram_mode="freeform",
        shapes=[{"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 100}],
        output_formats=["drawio", "png"],
    )

    assert result["success"] is True
    data = result["data"]
    assert data["artifact_id"] == "foo_bar_canvas"
    assert data["drawio_url"] == "/api/html-artifacts/foo_bar_canvas/assets/diagram.drawio"
    assert data["static_image_url"] == "/api/html-artifacts/foo_bar_canvas/assets/diagram.png"

    html = Path(data["file_path"]).read_text(encoding="utf-8")
    assert "/api/html-artifacts/foo_bar_canvas/assets/diagram.drawio" in html
    assert "/api/html-artifacts/foo_bar_canvas/assets/diagram.png" in html
    assert "/api/html-artifacts/foo/bar canvas/assets" not in html


@pytest.mark.asyncio
async def test_create_diagram_artifact_freeform_does_not_return_stale_svg_for_reused_id():
    tool = CreateDiagramArtifactTool()
    artifact_id = "test_freeform_reused_svg_contract"

    first = await tool.execute(
        artifact_id=artifact_id,
        title="自由画布 SVG",
        diagram_mode="freeform",
        shapes=[{"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 100}],
        output_formats=["drawio", "png", "drawio_svg"],
    )
    assert first["success"] is True
    assert "preview_svg_path" in first["data"]
    assert Path(first["data"]["preview_svg_path"]).exists()

    second = await tool.execute(
        artifact_id=artifact_id,
        title="自由画布 无 SVG",
        diagram_mode="freeform",
        shapes=[{"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 100}],
        output_formats=["drawio", "png"],
    )

    assert second["success"] is True
    data = second["data"]
    assert "preview_svg_path" not in data
    assert "preview_svg_url" not in data
    assert not Path(data["artifact_dir"], "assets", "diagram.drawio.svg").exists()
    assert "drawio_svg" not in {artifact["format"] for artifact in data["artifacts"]}
