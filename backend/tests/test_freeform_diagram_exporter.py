import json

import app.tools.visualization.create_diagram_artifact.freeform_exporter as freeform_exporter
from app.tools.visualization.create_diagram_artifact.freeform_exporter import (
    export_freeform_diagram,
)
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    normalize_freeform_diagram,
)


def test_export_freeform_diagram_writes_drawio_source_and_preview(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert result.drawio_path.exists()
    assert result.drawio_path.parent.name == "assets"
    assert result.source_json_path.exists()
    assert result.preview_png_path.exists()
    assert result.preview_svg_path.exists()
    source = json.loads(result.source_json_path.read_text(encoding="utf-8"))
    assert source["diagram_mode"] == "freeform"
    assert source["shapes"][0]["id"] == "a"
    assert result.preview_png_path.stat().st_size > 0


def test_export_freeform_diagram_always_writes_png_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: None)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert result.preview_png_path.exists()
    assert result.preview_png_path.parent.name == "assets"
    assert result.preview_png_path.name == "diagram.png"
    assert result.preview_png_path.stat().st_size > 0


def test_export_freeform_diagram_records_warning_when_exporter_unavailable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: None)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert "exporter_unavailable" in result.warnings


def test_fallback_svg_contains_group_and_shape_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: None)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[
            {
                "id": "shape",
                "type": "rounded_rect",
                "label": "Shape Label",
                "x": 20,
                "y": 30,
            }
        ],
        connectors=[],
        groups=[
            {
                "id": "group",
                "label": "Group Label",
                "children": ["shape"],
                "x": 10,
                "y": 10,
                "width": 200,
                "height": 120,
            }
        ],
        output_formats=["drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    fallback_svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert "Group Label" in fallback_svg
    assert "Shape Label" in fallback_svg
