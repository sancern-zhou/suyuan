import pytest

from app.tools.visualization.create_diagram_artifact.freeform_models import (
    FreeformValidationError,
    normalize_freeform_diagram,
)


def test_normalize_freeform_diagram_accepts_basic_canvas():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo Diagram",
        canvas={"width": 1200, "height": 800, "grid": 20, "background": "#ffffff"},
        shapes=[
            {"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 80, "width": 140, "height": 60},
            {"id": "decision", "type": "diamond", "label": "是否通过", "x": 320, "y": 70, "width": 120, "height": 90},
        ],
        connectors=[
            {"id": "edge_start_decision", "from": "start", "to": "decision", "label": "提交", "type": "orthogonal"}
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="process",
    )

    assert diagram.artifact_id == "demo"
    assert diagram.canvas.width == 1200
    assert [shape.id for shape in diagram.shapes] == ["start", "decision"]
    assert diagram.shapes[1].type == "diamond"
    assert diagram.connectors[0].source_id == "start"
    assert diagram.output_formats == ["drawio", "png", "drawio_svg"]
    assert diagram.diagram_intent == "process"


def test_duplicate_shape_ids_fail():
    with pytest.raises(FreeformValidationError, match="Duplicate shape id"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[
                {"id": "node", "label": "A", "x": 0, "y": 0},
                {"id": "node", "label": "B", "x": 100, "y": 0},
            ],
            connectors=[],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_connector_missing_endpoint_fails():
    with pytest.raises(FreeformValidationError, match="unknown target id missing"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
            connectors=[{"id": "edge", "from": "node", "to": "missing"}],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_drawio_shape_passthrough_is_preserved():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "aws_lambda",
                "type": "drawio_shape",
                "label": "函数",
                "x": 10,
                "y": 20,
                "width": 80,
                "height": 80,
                "drawio_shape_name": "mxgraph.aws4.lambda_function",
                "drawio_style": "sketch=0;aspect=fixed;",
            }
        ],
        connectors=[],
        groups=[],
        output_formats=[],
        diagram_intent="architecture",
    )

    shape = diagram.shapes[0]
    assert shape.type == "drawio_shape"
    assert shape.drawio_shape_name == "mxgraph.aws4.lambda_function"
    assert "aspect=fixed" in shape.drawio_style


def test_duplicate_connector_ids_fail():
    with pytest.raises(FreeformValidationError, match="Duplicate connector id"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[
                {"id": "source", "label": "A", "x": 0, "y": 0},
                {"id": "target", "label": "B", "x": 100, "y": 0},
            ],
            connectors=[
                {"id": "edge", "from": "source", "to": "target"},
                {"id": "edge", "from": "target", "to": "source"},
            ],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_connector_id_colliding_with_shape_id_fails():
    with pytest.raises(FreeformValidationError, match="Duplicate connector id node"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[
                {"id": "node", "label": "A", "x": 0, "y": 0},
                {"id": "target", "label": "B", "x": 100, "y": 0},
            ],
            connectors=[{"id": "node", "from": "node", "to": "target"}],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_non_finite_numeric_geometry_fails():
    with pytest.raises(FreeformValidationError, match="canvas.width must be finite"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={"width": "nan"},
            shapes=[],
            connectors=[],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


@pytest.mark.parametrize("dimension", ["width", "height"])
@pytest.mark.parametrize("value", [0, -1])
def test_zero_or_negative_shape_dimensions_fail(dimension, value):
    shape = {"id": "node", "label": "A", "x": 0, "y": 0, "width": 100, "height": 60}
    shape[dimension] = value

    with pytest.raises(FreeformValidationError, match=f"shape.{dimension} must be positive"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[shape],
            connectors=[],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )
