import xml.etree.ElementTree as ET

from app.tools.visualization.create_diagram_artifact.drawio_writer import build_drawio_xml
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    FreeformCanvas,
    FreeformDiagram,
    FreeformShape,
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


def test_build_drawio_xml_strips_active_html_from_cell_values():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="<IMG SRC=x onError=alert(1)>",
        canvas={},
        shapes=[
            {
                "id": "malicious",
                "type": "rounded_rect",
                "label": "<IMG SRC=x onError=alert(1)>",
                "x": 0,
                "y": 0,
            }
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    cell = root.find(".//mxCell[@id='malicious']")

    assert "<IMG" not in xml_text
    assert cell is not None
    assert "<IMG" not in cell.attrib["value"]
    assert "onError" not in cell.attrib["value"]


def test_drawio_shape_passthrough_strips_mixed_case_url_protocol_and_events():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "native",
                "type": "drawio_shape",
                "label": "Native",
                "x": 0,
                "y": 0,
                "drawio_shape_name": "process",
                "drawio_style": (
                    "whiteSpace=wrap;html=1;Href=JaVaScRiPt:alert(1);"
                    "Image=HTTPS://example.test/a.png;fillColor=#fff;"
                    "label=<IMG SRC=x onError=alert(1)>;onClick=alert(1);"
                    "tooltip=&quot;bad&quot;;strokeColor=#000000;"
                ),
            }
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    cell = root.find(".//mxCell[@id='native']")

    assert cell is not None
    style = cell.attrib["style"]
    assert "whiteSpace=wrap" in style
    assert "fillColor=#fff" in style
    assert "strokeColor=#000000" in style
    assert "Href=" not in style
    assert "Image=" not in style
    assert "javascript:" not in style.lower()
    assert "onClick" not in style
    assert "<IMG" not in style
    assert "onError" not in style
    assert "quot" not in style


def test_grouped_child_geometry_is_relative_to_parent_group():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "child",
                "type": "rounded_rect",
                "label": "Child",
                "x": 130,
                "y": 240,
                "width": 80,
                "height": 40,
                "parent_id": "group_1",
            }
        ],
        connectors=[],
        groups=[
            {
                "id": "group_1",
                "label": "Group",
                "children": ["child"],
                "x": 100,
                "y": 200,
                "width": 300,
                "height": 200,
            }
        ],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    child = root.find(".//mxCell[@id='child']")

    assert child is not None
    assert child.attrib["parent"] == "group_1"
    geometry = child.find("mxGeometry")
    assert geometry is not None
    assert geometry.attrib["x"] == "30"
    assert geometry.attrib["y"] == "40"
    assert geometry.attrib["width"] == "80"
    assert geometry.attrib["height"] == "40"


def test_rectangle_and_stadium_shape_aliases_use_specific_styles():
    diagram = FreeformDiagram(
        artifact_id="demo",
        title="Demo",
        canvas=FreeformCanvas(),
        shapes=[
            FreeformShape(id="rectangle", type="rectangle", label="Rectangle"),
            FreeformShape(id="stadium", type="stadium", label="Stadium", y=100),
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    cells = {cell.attrib.get("id"): cell for cell in root.findall(".//mxCell")}

    assert "rounded=0" in cells["rectangle"].attrib["style"]
    assert "arcSize=10" not in cells["rectangle"].attrib["style"]
    assert "absoluteArcSize=1" in cells["stadium"].attrib["style"]
    assert "arcSize=10" not in cells["stadium"].attrib["style"]


def test_drawio_shape_passthrough_preserves_benign_numeric_and_bracketed_values():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "native",
                "type": "drawio_shape",
                "label": "Native",
                "x": 0,
                "y": 0,
                "drawio_shape_name": "process",
                "drawio_style": (
                    "whiteSpace=wrap;html=1;3d=1;points=[[0,0],[1,0],[1,1]];"
                    "href=javascript:alert(1);onClick=alert(1);"
                ),
            }
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)
    cell = root.find(".//mxCell[@id='native']")

    assert cell is not None
    style = cell.attrib["style"]
    assert "3d=1" in style
    assert "points=[[0,0],[1,0],[1,1]]" in style
    assert "javascript:" not in style.lower()
    assert "onClick" not in style
