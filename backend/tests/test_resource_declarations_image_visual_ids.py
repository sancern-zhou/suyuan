import json
from pathlib import Path

from app.tools.resource_declarations import (
    allocate_image_visual_ids,
    generated_file_products,
    generated_image_visuals,
)


def test_image_products_carry_visual_identity(tmp_path: Path):
    png = tmp_path / "forecast_aqi_range.png"
    png.write_bytes(b"png")
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"docx")

    visual_ids = allocate_image_visual_ids([png, docx])
    assert set(visual_ids) == {str(png.resolve())}

    resources = generated_file_products(
        [png, docx], tool_name="execute_python", image_visual_ids=visual_ids
    )
    png_primary = next(r for r in resources if r["label"] == "forecast_aqi_range.png")
    assert png_primary["renderer"] == "image"
    assert png_primary["metadata"]["visual_id"] == visual_ids[str(png.resolve())]
    docx_primary = next(r for r in resources if r["label"] == "report.docx")
    assert "visual_id" not in docx_primary["metadata"]


def test_generated_image_visuals_dedup_against_save_chart_paths(tmp_path: Path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"png")
    visual_ids = allocate_image_visual_ids([png])
    existing = [{
        "id": "matplotlib_exists",
        "type": "image",
        "data": {"source_file_path": str(png.resolve())},
    }]
    assert generated_image_visuals([png], visual_ids, existing_visuals=existing) == []

    other = tmp_path / "other.png"
    other.write_bytes(b"png")
    other_ids = allocate_image_visual_ids([other])
    visuals = generated_image_visuals([other], other_ids, existing_visuals=existing)
    assert len(visuals) == 1
    assert visuals[0]["id"] == other_ids[str(other.resolve())]
    assert visuals[0]["type"] == "image"
    assert visuals[0]["data"]["source_file_path"] == str(other.resolve())
