import xml.etree.ElementTree as ET

from app.tools.visualization.create_diagram_artifact.drawio_writer import build_drawio_xml
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    normalize_freeform_diagram,
)


def test_build_drawio_xml_contains_shapes_and_edges():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 1000, "height": 700},
        shapes=[
            {
                "id": "a",
                "type": "rounded_rect",
                "label": "A",
                "x": 10,
                "y": 20,
                "width": 120,
                "height": 60,
            },
            {
                "id": "b",
                "type": "database",
                "label": "数据库",
                "x": 260,
                "y": 20,
                "width": 120,
                "height": 80,
            },
        ],
        connectors=[{"id": "edge_a_b", "from": "a", "to": "b", "label": "写入"}],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="architecture",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)

    cells = {cell.attrib.get("id"): cell for cell in root.findall(".//mxCell")}
    assert "a" in cells
    assert "b" in cells
    assert "edge_a_b" in cells
    assert cells["edge_a_b"].attrib["source"] == "a"
    assert cells["edge_a_b"].attrib["target"] == "b"
    assert "shape=cylinder" in cells["b"].attrib["style"]


def test_drawio_shape_passthrough_style_is_used():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "native",
                "type": "drawio_shape",
                "label": "原生",
                "x": 0,
                "y": 0,
                "drawio_shape_name": "process",
                "drawio_style": "whiteSpace=wrap;html=1;",
            }
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    assert "shape=process" in xml_text
    assert "whiteSpace=wrap;html=1;" in xml_text


def test_build_drawio_xml_emits_groups_and_filters_unsafe_style_text():
    diagram = normalize_freeform_diagram(
        artifact_id='demo" onclick="bad',
        title="Demo <unsafe>",
        canvas={"background": 'white";bad=1;'},
        shapes=[
            {
                "id": "native",
                "type": "drawio_shape",
                "label": "<b>raw</b>",
                "x": 15,
                "y": 25,
                "width": 90,
                "height": 45,
                "drawio_shape_name": "process<script>",
                "drawio_style": 'whiteSpace=wrap;html=1;image=data:text/html,<script>bad</script>;bad"=1;',
            }
        ],
        connectors=[],
        groups=[
            {
                "id": "group_1",
                "label": "Group",
                "children": ["native"],
                "x": 0,
                "y": 0,
                "width": 180,
                "height": 120,
            }
        ],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    cells = {cell.attrib.get("id"): cell for cell in root.findall(".//mxCell")}

    assert cells["group_1"].attrib["vertex"] == "1"
    assert cells["native"].attrib["parent"] == "group_1"
    assert "<script>" not in xml_text
    assert "onclick" not in xml_text
    assert "image=data" not in xml_text
