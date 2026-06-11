import json

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
