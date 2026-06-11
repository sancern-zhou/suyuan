import json

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


def test_output_format_aliases_are_normalized():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo Diagram",
        canvas={},
        shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
        connectors=[],
        groups=[],
        output_formats=["drawio", ".drawio.svg", "svg", "png"],
        diagram_intent=None,
    )

    assert diagram.output_formats == ["drawio", "drawio_svg", "png"]


def test_common_agent_field_aliases_are_normalized():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo Diagram",
        canvas={},
        shapes=[
            {"id": "a", "type": "rectangle", "text": "Client", "x": 0, "y": 0},
            {"id": "b", "type": "cylinder", "name": "Store", "x": 200, "y": 0},
        ],
        connectors=[
            {
                "id": "edge",
                "source": "a",
                "target": "b",
                "text": "query",
                "style": "orthogonal",
            }
        ],
        groups=[],
        output_formats=[],
        diagram_intent=None,
    )

    assert diagram.shapes[0].label == "Client"
    assert diagram.shapes[1].label == "Store"
    assert diagram.connectors[0].source_id == "a"
    assert diagram.connectors[0].target_id == "b"
    assert diagram.connectors[0].label == "query"
    assert diagram.connectors[0].type == "orthogonal"


def test_empty_shapes_fail():
    with pytest.raises(FreeformValidationError, match="freeform diagram requires at least one shape"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[],
            connectors=[],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


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


def test_source_dict_includes_diagram_mode():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
        connectors=[],
        groups=[],
        output_formats=[],
        diagram_intent=None,
    )

    assert diagram.to_source_dict()["diagram_mode"] == "freeform"


def test_output_formats_are_normalized_with_first_seen_order():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
        connectors=[],
        groups=[],
        output_formats=["drawio", "drawio.svg", "drawio_svg", "png"],
        diagram_intent=None,
    )

    assert diagram.output_formats == ["drawio", "drawio_svg", "png"]


@pytest.mark.parametrize("output_formats", [None, []])
def test_empty_output_formats_default_to_drawio_and_png(output_formats):
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
        connectors=[],
        groups=[],
        output_formats=output_formats,
        diagram_intent=None,
    )

    assert diagram.output_formats == ["drawio", "png"]


def test_unknown_shape_type_normalizes_to_rounded_rect():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[{"id": "node", "type": "unknown_widget", "label": "A", "x": 0, "y": 0}],
        connectors=[],
        groups=[],
        output_formats=[],
        diagram_intent=None,
    )

    assert diagram.shapes[0].type == "rounded_rect"


def test_all_known_shape_types_are_accepted():
    known_shape_types = [
        "rect",
        "rectangle",
        "rounded_rect",
        "stadium",
        "text",
        "container",
        "swimlane",
        "database",
        "cloud",
        "queue",
        "document",
        "circle",
        "ellipse",
        "hexagon",
        "diamond",
        "triangle",
        "parallelogram",
        "cylinder",
        "actor",
        "note",
        "callout",
        "brace",
        "bracket",
        "line",
        "arrow",
        "image",
        "drawio_shape",
    ]
    shapes = [
        {"id": f"shape_{index}", "type": shape_type, "label": shape_type, "x": index * 10, "y": 0}
        for index, shape_type in enumerate(known_shape_types)
    ]

    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=shapes,
        connectors=[],
        groups=[],
        output_formats=[],
        diagram_intent=None,
    )

    assert [shape.type for shape in diagram.shapes] == known_shape_types


def test_to_source_dict_is_strict_json_serializable():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 1200, "height": 800, "grid": 20, "background": "#ffffff"},
        shapes=[
            {"id": "source", "label": "A", "x": 0, "y": 0},
            {"id": "target", "label": "B", "x": 160, "y": 0},
        ],
        connectors=[{"id": "edge", "from": "source", "to": "target"}],
        groups=[{"id": "group", "label": "Group", "children": ["source", "target"]}],
        output_formats=["drawio"],
        diagram_intent="process",
    )
    source = diagram.to_source_dict()

    json.dumps(source, allow_nan=False)


def test_connector_endpoints_may_reference_group_ids():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {"id": "source", "label": "A", "x": 0, "y": 0},
            {"id": "target", "label": "B", "x": 160, "y": 0},
        ],
        connectors=[
            {"id": "edge_from_group", "from": "group", "to": "target"},
            {"id": "edge_to_group", "from": "source", "to": "group"},
        ],
        groups=[{"id": "group", "label": "Group", "children": ["source"]}],
        output_formats=[],
        diagram_intent=None,
    )

    assert diagram.connectors[0].source_id == "group"
    assert diagram.connectors[1].target_id == "group"


def test_group_children_must_reference_known_shape_or_group_ids():
    with pytest.raises(
        FreeformValidationError, match="Group group references unknown child id missing"
    ):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
            connectors=[],
            groups=[{"id": "group", "label": "Group", "children": ["missing"]}],
            output_formats=[],
            diagram_intent=None,
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("canvas", "bad", "canvas must be an object"),
        ("shapes", ["bad"], "shape must be an object"),
        ("shapes", 123, "shapes must be a list"),
        ("connectors", ["bad"], "connector must be an object"),
        ("connectors", 123, "connectors must be a list"),
        ("groups", ["bad"], "group must be an object"),
        ("groups", 123, "groups must be a list"),
    ],
)
def test_malformed_json_source_sections_raise_validation_error(field, value, match):
    payload = {
        "artifact_id": "demo",
        "title": "Demo",
        "canvas": {},
        "shapes": [{"id": "node", "label": "A", "x": 0, "y": 0}],
        "connectors": [],
        "groups": [],
        "output_formats": [],
        "diagram_intent": None,
    }
    payload[field] = value

    with pytest.raises(FreeformValidationError, match=match):
        normalize_freeform_diagram(**payload)


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
