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


def test_export_freeform_diagram_removes_stale_svg_when_not_requested(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: None)
    diagram_with_svg = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio_svg"],
        diagram_intent="custom",
    )
    export_freeform_diagram(diagram_with_svg, tmp_path)
    stale_svg = tmp_path / "assets" / "diagram.drawio.svg"
    assert stale_svg.exists()

    diagram_without_svg = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png"],
        diagram_intent="custom",
    )
    result = export_freeform_diagram(diagram_without_svg, tmp_path)

    assert not result.preview_svg_path.exists()
    assert result.preview_png_path.exists()


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


def test_failed_cli_zero_byte_outputs_are_overwritten_by_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: "drawio")

    def failed_export(_exporter, _drawio_path, output_path, _output_format):
        output_path.write_bytes(b"")
        return False

    monkeypatch.setattr(freeform_exporter, "_run_drawio_export", failed_export)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio", "drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert "exporter_unavailable" in result.warnings
    assert result.preview_png_path.stat().st_size > 0
    assert result.preview_svg_path.stat().st_size > 0


def test_failed_cli_non_empty_outputs_are_overwritten_by_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: "drawio")
    bogus_png = b"not a png"
    bogus_svg = "<svg>bogus partial output</svg>"

    def failed_export(_exporter, _drawio_path, output_path, output_format):
        if output_format == "png":
            output_path.write_bytes(bogus_png)
        else:
            output_path.write_text(bogus_svg, encoding="utf-8")
        return False

    monkeypatch.setattr(freeform_exporter, "_run_drawio_export", failed_export)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[
            {
                "id": "shape",
                "type": "rounded_rect",
                "label": "Fallback Shape",
                "x": 20,
                "y": 30,
            }
        ],
        connectors=[],
        groups=[
            {
                "id": "group",
                "label": "Fallback Group",
                "children": ["shape"],
                "x": 10,
                "y": 10,
                "width": 200,
                "height": 120,
            }
        ],
        output_formats=["drawio", "drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert "exporter_unavailable" in result.warnings
    assert result.preview_png_path.read_bytes() != bogus_png
    fallback_svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert "bogus partial output" not in fallback_svg
    assert "Fallback Shape" in fallback_svg
    assert "Fallback Group" in fallback_svg


def test_fallback_svg_renders_connector_from_group_to_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(freeform_exporter, "_find_drawio_exporter", lambda: None)
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[
            {
                "id": "shape",
                "type": "rounded_rect",
                "label": "Shape",
                "x": 300,
                "y": 80,
            }
        ],
        connectors=[
            {
                "id": "edge_group_shape",
                "from": "group",
                "to": "shape",
                "label": "Group to shape",
            }
        ],
        groups=[
            {
                "id": "group",
                "label": "Group",
                "children": ["shape"],
                "x": 20,
                "y": 30,
                "width": 180,
                "height": 120,
            }
        ],
        output_formats=["drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    fallback_svg = result.preview_svg_path.read_text(encoding="utf-8")
    assert result.preview_svg_path.stat().st_size > 0
    assert 'data-connector-id="edge_group_shape"' in fallback_svg


def test_drawio_export_discards_subprocess_output(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(freeform_exporter.subprocess, "run", fake_run)

    freeform_exporter._run_drawio_export(
        "drawio",
        tmp_path / "diagram.drawio",
        tmp_path / "diagram.png",
        "png",
    )

    assert calls[0][1]["stdout"] == freeform_exporter.subprocess.DEVNULL
    assert calls[0][1]["stderr"] == freeform_exporter.subprocess.DEVNULL
