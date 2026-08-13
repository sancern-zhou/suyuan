import xml.etree.ElementTree as ET

import app.tools.visualization.create_drawio_board.routing as routing_module
from app.tools.visualization.create_drawio_board.routing import (
    route_drawio_candidate,
)
from app.tools.visualization.create_drawio_board.xml_utils import normalize_drawio_xml


def _route(xml_fragment: str):
    return route_drawio_candidate(normalize_drawio_xml(xml_fragment))


def _edge(result_xml: str, edge_id: str = "edge") -> ET.Element:
    root = ET.fromstring(result_xml)
    return next(cell for cell in root.iter("mxCell") if cell.attrib.get("id") == edge_id)


def test_routes_around_nested_child_using_absolute_coordinates():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="120" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="group" value="阶段" vertex="1" parent="1" style="container=1;"><mxGeometry x="160" y="80" width="180" height="140" as="geometry"/></mxCell>
    <mxCell id="blocker" value="嵌套节点" vertex="1" parent="group"><mxGeometry x="40" y="30" width="100" height="60" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="420" y="120" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["rerouted_edge_count"] == 1
    points = _edge(result.xml).findall("mxGeometry/Array[@as='points']/mxPoint")
    assert points
    assert any(float(point.attrib["y"]) < 98 or float(point.attrib["y"]) > 182 for point in points)


def test_routes_around_relative_child_with_text_inside_container():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="120" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="group" value="阶段" vertex="1" parent="1" style="container=1;"><mxGeometry x="160" y="80" width="200" height="160" as="geometry"/></mxCell>
    <mxCell id="blocker" value="相对布局节点" vertex="1" parent="group"><mxGeometry x="0.25" y="0.2" width="100" height="60" relative="1" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="440" y="120" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["rerouted_edge_count"] == 1
    assert _edge(result.xml).find("mxGeometry/Array[@as='points']") is not None


def test_preserves_collision_free_explicit_route():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=segmentEdgeStyle;strokeColor=#123456;"><mxGeometry relative="1" as="geometry"><Array as="points"><mxPoint x="80" y="-40"/><mxPoint x="300" y="-40"/></Array></mxGeometry></mxCell>
    """)

    edge = _edge(result.xml)
    assert result.metrics["routed_edge_count"] == 0
    assert "strokeColor=#123456" in edge.attrib["style"]
    assert "exitX=1" in edge.attrib["style"]
    assert "entryX=0" in edge.attrib["style"]
    assert [
        (point.attrib["x"], point.attrib["y"]) for point in edge.findall("mxGeometry/Array/mxPoint")
    ] == [
        ("80", "-40"),
        ("300", "-40"),
    ]


def test_vertical_swimlane_header_does_not_trigger_a_detour():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="100" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="lane" value="角色" vertex="1" parent="1" style="swimlane;horizontal=0;startSize=20;"><mxGeometry x="160" y="40" width="240" height="200" as="geometry"/></mxCell>
    <mxCell id="upper" value="上方节点" vertex="1" parent="lane"><mxGeometry x="40" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="lane"><mxGeometry x="40" y="60" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="lower" value="下方节点" vertex="1" parent="lane"><mxGeometry x="40" y="120" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["rerouted_edge_count"] == 0
    assert _edge(result.xml).find("mxGeometry/Array[@as='points']") is None


def test_horizontal_swimlane_header_does_not_trigger_a_detour():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="240" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="lane" value="接入层" vertex="1" parent="1" style="swimlane;horizontal=1;startSize=30;"><mxGeometry x="160" y="100" width="240" height="200" as="geometry"/></mxCell>
    <mxCell id="target" value="API 网关" vertex="1" parent="lane"><mxGeometry x="80" y="80" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["rerouted_edge_count"] == 0
    assert _edge(result.xml).find("mxGeometry/Array[@as='points']") is None


def test_layout_background_edge_ignores_nodes_contained_by_its_terminals():
    result = _route("""
    <mxCell id="layer1_bg" value="" vertex="1" parent="1" style="rounded=1;pointerEvents=0;"><mxGeometry x="40" y="40" width="1080" height="120" as="geometry"/></mxCell>
    <mxCell id="near_source_boundary" value="市级生态环境部门" vertex="1" parent="1"><mxGeometry x="460" y="90" width="160" height="60" as="geometry"/></mxCell>
    <mxCell id="layer2_bg" value="" vertex="1" parent="1" style="rounded=1;pointerEvents=0;"><mxGeometry x="40" y="200" width="1080" height="280" as="geometry"/></mxCell>
    <mxCell id="inside_target" value="核心业务" vertex="1" parent="1"><mxGeometry x="460" y="260" width="160" height="60" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="layer1_bg" target="layer2_bg" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    edge = _edge(result.xml)
    assert result.metrics["rerouted_edge_count"] == 0
    assert "exitX=0.5;exitY=1" in edge.attrib["style"]
    assert "entryX=0.5;entryY=0" in edge.attrib["style"]
    assert edge.find("mxGeometry/Array[@as='points']") is None


def test_repairs_page_coordinates_used_for_swimlane_children_before_routing():
    result = _route("""
    <mxCell id="enterprise" value="企业端" vertex="1" parent="1" style="swimlane;startSize=20;"><mxGeometry x="50" y="50" width="900" height="600" as="geometry"/></mxCell>
    <mxCell id="platform" value="平台" vertex="1" parent="1" style="swimlane;startSize=20;"><mxGeometry x="50" y="670" width="900" height="300" as="geometry"/></mxCell>
    <mxCell id="source" value="在线解密" vertex="1" parent="enterprise"><mxGeometry x="440" y="470" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="target" value="等待专家评审" vertex="1" parent="enterprise"><mxGeometry x="80" y="620" width="130" height="60" as="geometry"/></mxCell>
    <mxCell id="platform_node" value="平台节点" vertex="1" parent="platform"><mxGeometry x="80" y="720" width="130" height="50" as="geometry"/></mxCell>
    <mxCell id="platform_node_2" value="平台节点2" vertex="1" parent="platform"><mxGeometry x="260" y="820" width="130" height="50" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"><Array as="points"><Object x="500" y="550"/><Object x="145" y="550"/></Array></mxGeometry></mxCell>
    """)

    root = ET.fromstring(result.xml)
    cells = {cell.attrib.get("id"): cell for cell in root.iter("mxCell")}
    assert cells["source"].find("mxGeometry").attrib["x"] == "440"
    assert cells["source"].find("mxGeometry").attrib["y"] == "420"
    assert cells["target"].find("mxGeometry").attrib["y"] == "540"
    assert cells["platform_node"].find("mxGeometry").attrib["y"] == "50"
    assert _edge(result.xml).findall("mxGeometry/Array[@as='points']/mxPoint")
    assert not _edge(result.xml).findall("mxGeometry/Array[@as='points']/Object")
    assert result.metrics["edge_vertex_intersection_count"] == 0


def test_does_not_rebase_normal_local_coordinates_for_minor_container_overflow():
    result = _route("""
    <mxCell id="lane" value="泳道" vertex="1" parent="1" style="swimlane;startSize=20;"><mxGeometry x="0" y="50" width="400" height="200" as="geometry"/></mxCell>
    <mxCell id="normal" value="正常节点" vertex="1" parent="lane"><mxGeometry x="40" y="60" width="100" height="50" as="geometry"/></mxCell>
    <mxCell id="slightly_outside" value="轻微越界" vertex="1" parent="lane"><mxGeometry x="300" y="160" width="100" height="50" as="geometry"/></mxCell>
    """)

    root = ET.fromstring(result.xml)
    cells = {cell.attrib.get("id"): cell for cell in root.iter("mxCell")}
    assert cells["normal"].find("mxGeometry").attrib["x"] == "40"
    assert cells["slightly_outside"].find("mxGeometry").attrib["y"] == "160"


def test_visibility_graph_fallback_weaves_between_alternating_barriers():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="130" width="40" height="40" as="geometry"/></mxCell>
    <mxCell id="upper_wall_1" value="U1" vertex="1" parent="1"><mxGeometry x="80" y="-1000" width="40" height="1120" as="geometry"/></mxCell>
    <mxCell id="lower_wall" value="L" vertex="1" parent="1"><mxGeometry x="180" y="120" width="40" height="1000" as="geometry"/></mxCell>
    <mxCell id="upper_wall_2" value="U2" vertex="1" parent="1"><mxGeometry x="280" y="-1000" width="40" height="1120" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="400" y="130" width="40" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    points = _edge(result.xml).findall("mxGeometry/Array[@as='points']/mxPoint")
    assert len(points) >= 4
    assert result.metrics["edge_vertex_intersection_count"] == 0


def test_rerouted_edge_respects_selected_port_direction():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="100" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="barrier" value="B" vertex="1" parent="1"><mxGeometry x="100" y="80" width="80" height="100" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="240" y="100" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    edge = _edge(result.xml)
    style = edge.attrib["style"]
    points = edge.findall("mxGeometry/Array[@as='points']/mxPoint")
    first = points[0]
    last = points[-1]
    if "exitX=1;" in style:
        assert float(first.attrib["x"]) > 80
    elif "exitX=0;" in style:
        assert float(first.attrib["x"]) < 0
    if "entryX=0;" in style:
        assert float(last.attrib["x"]) < 240
    elif "entryX=1;" in style:
        assert float(last.attrib["x"]) > 320


def test_unroutable_issue_identifies_trapped_terminal_and_repair_action():
    result = _route("""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="right_wall" value="R" vertex="1" parent="1"><mxGeometry x="85" y="-200" width="100" height="440" as="geometry"/></mxCell>
        <mxCell id="left_wall" value="L" vertex="1" parent="1"><mxGeometry x="-105" y="-200" width="100" height="440" as="geometry"/></mxCell>
        <mxCell id="top_wall" value="U" vertex="1" parent="1"><mxGeometry x="-200" y="-105" width="480" height="100" as="geometry"/></mxCell>
        <mxCell id="bottom_wall" value="D" vertex="1" parent="1"><mxGeometry x="-200" y="45" width="480" height="100" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    issue = result.issues[0]
    assert result.status == "partial"
    assert issue["cause"] == "source_terminal_trapped"
    assert set(issue["blocking_node_ids"]) == {
        "right_wall",
        "left_wall",
        "top_wall",
        "bottom_wall",
    }
    assert issue["repair_actions"] == [
        {
            "action": "relayout_terminal",
            "cell_id": "source",
            "avoid_cell_ids": ["bottom_wall", "left_wall", "right_wall", "top_wall"],
        }
    ]
    assert issue["retry_strategy"] == "move_terminal_then_regenerate_edges"
    assert issue["blocking"] is False
    assert issue["retry_required"] is False
    assert "已保留原始连线并继续生成画板" in issue["message"]


def test_preserves_unroutable_edge_and_routes_later_edges():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="right_wall" value="R" vertex="1" parent="1"><mxGeometry x="85" y="-200" width="100" height="440" as="geometry"/></mxCell>
    <mxCell id="left_wall" value="L" vertex="1" parent="1"><mxGeometry x="-105" y="-200" width="100" height="440" as="geometry"/></mxCell>
    <mxCell id="top_wall" value="U" vertex="1" parent="1"><mxGeometry x="-200" y="-105" width="480" height="100" as="geometry"/></mxCell>
    <mxCell id="bottom_wall" value="D" vertex="1" parent="1"><mxGeometry x="-200" y="45" width="480" height="100" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="blocked_edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;strokeColor=#123456;"><mxGeometry relative="1" as="geometry"/></mxCell>
    <mxCell id="later_source" value="LS" vertex="1" parent="1"><mxGeometry x="0" y="240" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="240" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_target" value="LT" vertex="1" parent="1"><mxGeometry x="300" y="240" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_edge" edge="1" parent="1" source="later_source" target="later_target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    root = ET.fromstring(result.xml)
    edges = {cell.attrib["id"]: cell for cell in root.iter("mxCell") if cell.attrib.get("edge") == "1"}
    blocked = edges["blocked_edge"]
    later = edges["later_edge"]

    assert result.status == "partial"
    assert result.issues[0]["edge_id"] == "blocked_edge"
    assert result.issues[0]["preserved_original_edge"] is True
    assert blocked.attrib["style"] == "edgeStyle=orthogonalEdgeStyle;strokeColor=#123456;"
    assert blocked.find("mxGeometry/Array[@as='points']") is None
    assert "edgeStyle=segmentEdgeStyle" in later.attrib["style"]
    assert later.find("mxGeometry/Array[@as='points']") is not None
    assert result.metrics["degraded_edge_count"] == 1
    assert result.metrics["rerouted_edge_count"] == 1


def test_ignores_decorative_backgrounds_and_transparent_titles():
    result = _route("""
    <mxCell id="module_bg" value="" vertex="1" parent="1" style="rounded=1;fillColor=#eeeeee;"><mxGeometry x="-40" y="-40" width="460" height="180" as="geometry"/></mxCell>
    <mxCell id="module_title" value="模块标题" vertex="1" parent="1" style="text;strokeColor=none;fillColor=none;"><mxGeometry x="0" y="-20" width="380" height="30" as="geometry"/></mxCell>
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="40" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="40" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="40" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.status == "applied"
    assert result.issues == ()
    assert result.metrics["rerouted_edge_count"] == 1
    assert _edge(result.xml).find("mxGeometry/Array[@as='points']") is not None


def test_recent_incident_shape_routes_all_23_edges_inside_module_background():
    cells = [
        '<mxCell id="alert_module_bg" value="" vertex="1" parent="1" '
        'style="rounded=1;fillColor=#eeeeee;"><mxGeometry x="-40" y="-40" '
        'width="460" height="2340" as="geometry"/></mxCell>',
        '<mxCell id="alert_module_title" value="模块标题" vertex="1" parent="1" '
        'style="text;strokeColor=none;fillColor=none;"><mxGeometry x="0" y="-20" '
        'width="380" height="30" as="geometry"/></mxCell>',
    ]
    for index in range(23):
        y = 40 + index * 95
        source_id = "start" if index == 0 else f"source_{index}"
        target_id = "query_data" if index == 0 else f"target_{index}"
        edge_id = "edge_start_query" if index == 0 else f"edge_{index}"
        cells.extend(
            [
                f'<mxCell id="{source_id}" value="S{index}" vertex="1" parent="1">'
                f'<mxGeometry x="0" y="{y}" width="80" height="40" as="geometry"/>'
                '</mxCell>',
                f'<mxCell id="{target_id}" value="T{index}" vertex="1" parent="1">'
                f'<mxGeometry x="300" y="{y}" width="80" height="40" as="geometry"/>'
                '</mxCell>',
                f'<mxCell id="{edge_id}" edge="1" parent="1" source="{source_id}" '
                f'target="{target_id}" style="edgeStyle=orthogonalEdgeStyle;">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>',
            ]
        )

    result = _route("".join(cells))

    assert result.status == "applied"
    assert result.metrics["edge_count"] == 23
    assert result.metrics["safe_edge_count"] == 23
    assert result.metrics["degraded_edge_count"] == 0
    assert result.issues == ()


def test_preserves_edge_after_unexpected_edge_error_and_continues(monkeypatch):
    original_find_route = routing_module._find_route
    calls = 0

    def fail_first_route(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("unexpected edge failure")
        return original_find_route(*args, **kwargs)

    monkeypatch.setattr(routing_module, "_find_route", fail_first_route)
    result = _route("""
    <mxCell id="first_source" value="FS" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="first_target" value="FT" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="first_edge" edge="1" parent="1" source="first_source" target="first_target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    <mxCell id="later_source" value="LS" vertex="1" parent="1"><mxGeometry x="0" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_target" value="LT" vertex="1" parent="1"><mxGeometry x="300" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="later_edge" edge="1" parent="1" source="later_source" target="later_target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    root = ET.fromstring(result.xml)
    edges = {cell.attrib["id"]: cell for cell in root.iter("mxCell") if cell.attrib.get("edge") == "1"}
    assert result.status == "partial"
    assert result.issues[0]["edge_id"] == "first_edge"
    assert result.issues[0]["cause"] == "edge_router_internal_error"
    assert edges["first_edge"].find("mxGeometry/Array[@as='points']") is None
    assert edges["later_edge"].find("mxGeometry/Array[@as='points']") is not None


def test_post_route_intersection_rolls_back_only_affected_edge(monkeypatch):
    validation_calls = 0

    def intersections(routes, terminals, obstacles, **_context):
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            return [
                ("first_edge", "first_blocker"),
                ("first_edge", "second_blocker"),
            ]
        return []

    monkeypatch.setattr(
        routing_module,
        "_route_map_intersections",
        intersections,
    )
    result = _route("""
    <mxCell id="first_source" value="FS" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="first_blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="first_target" value="FT" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="first_edge" edge="1" parent="1" source="first_source" target="first_target" style="edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;"><mxGeometry relative="1" as="geometry"/></mxCell>
    <mxCell id="second_source" value="SS" vertex="1" parent="1"><mxGeometry x="0" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="second_blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="second_target" value="ST" vertex="1" parent="1"><mxGeometry x="300" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="second_edge" edge="1" parent="1" source="second_source" target="second_target" style="edgeStyle=orthogonalEdgeStyle;strokeColor=#222222;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    root = ET.fromstring(result.xml)
    edges = {cell.attrib["id"]: cell for cell in root.iter("mxCell") if cell.attrib.get("edge") == "1"}
    assert result.status == "partial"
    assert edges["first_edge"].attrib["style"] == "edgeStyle=orthogonalEdgeStyle;strokeColor=#111111;"
    assert edges["first_edge"].find("mxGeometry/Array[@as='points']") is None
    assert "edgeStyle=segmentEdgeStyle" in edges["second_edge"].attrib["style"]
    assert edges["second_edge"].find("mxGeometry/Array[@as='points']") is not None
    assert result.issues[0]["blocking_node_ids"] == ["first_blocker", "second_blocker"]
    assert result.metrics["remaining_intersection_count"] == 0
    assert result.metrics["edge_vertex_intersection_count"] == 0


def test_reports_straight_edge_that_crosses_a_node():
    result = _route("""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=none;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    issue = result.issues[0]
    assert issue["code"] == "unsupported_colliding_edge_style"
    assert issue["edge_id"] == "edge"
    assert issue["cause"] == "unsupported_edge_style"
    assert issue["retry_strategy"] == "regenerate_edge_only"
    assert issue["repair_actions"][0]["action"] == "convert_edge_to_orthogonal"


def test_reports_edge_crossings_without_failing_candidate():
    result = _route("""
    <mxCell id="left" value="L" vertex="1" parent="1"><mxGeometry x="0" y="80" width="60" height="40" as="geometry"/></mxCell>
    <mxCell id="right" value="R" vertex="1" parent="1"><mxGeometry x="320" y="80" width="60" height="40" as="geometry"/></mxCell>
    <mxCell id="top" value="T" vertex="1" parent="1"><mxGeometry x="160" y="0" width="60" height="40" as="geometry"/></mxCell>
    <mxCell id="bottom" value="B" vertex="1" parent="1"><mxGeometry x="160" y="160" width="60" height="40" as="geometry"/></mxCell>
    <mxCell id="horizontal" edge="1" parent="1" source="left" target="right" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    <mxCell id="vertical" edge="1" parent="1" source="top" target="bottom" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["edge_vertex_intersection_count"] == 0
    assert result.metrics["edge_edge_crossing_count"] == 1


def test_reports_diagonal_straight_edge_that_crosses_a_node():
    result = _route("""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="150" y="90" width="60" height="60" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="200" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=none;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.issues[0]["code"] == "unsupported_colliding_edge_style"


def test_allows_diagonal_straight_edge_when_node_is_clear():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="clear" value="B" vertex="1" parent="1"><mxGeometry x="150" y="180" width="60" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="200" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=none;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["edge_vertex_intersection_count"] == 0
    assert _edge(result.xml).attrib["style"] == "edgeStyle=none;"


def test_normalizes_curved_orthogonal_edge_to_explicit_safe_segments():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;curved=1;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    edge = _edge(result.xml)
    assert "edgeStyle=segmentEdgeStyle" in edge.attrib["style"]
    assert "curved=1" not in edge.attrib["style"]
    assert edge.find("mxGeometry/Array[@as='points']") is not None


def test_normalizes_missing_edge_style_to_explicit_safe_segments():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    edge = _edge(result.xml)
    assert "edgeStyle=segmentEdgeStyle" in edge.attrib["style"]
    assert edge.find("mxGeometry/Array[@as='points']") is not None


def test_parent_shape_with_child_badge_remains_an_obstacle():
    result = _route("""
    <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="60" as="geometry"/></mxCell>
    <mxCell id="parent_node" value="父节点" vertex="1" parent="1"><mxGeometry x="140" y="0" width="100" height="60" as="geometry"/></mxCell>
    <mxCell id="badge" value="1" vertex="1" parent="parent_node" style="ellipse;"><mxGeometry x="1" y="0" width="4" height="4" relative="1" as="geometry"><mxPoint x="-2" y="-2" as="offset"/></mxGeometry></mxCell>
    <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="60" as="geometry"/></mxCell>
    <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=orthogonalEdgeStyle;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.metrics["rerouted_edge_count"] == 1
    assert _edge(result.xml).find("mxGeometry/Array[@as='points']") is not None


def test_reports_non_orthogonal_edge_with_explicit_points_through_node():
    result = _route("""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="90" width="80" height="60" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="40" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=none;"><mxGeometry relative="1" as="geometry"><Array as="points"><mxPoint x="80" y="120"/><mxPoint x="300" y="120"/></Array></mxGeometry></mxCell>
    """)

    assert result.issues[0]["code"] == "unsupported_colliding_edge_style"
    assert result.issues[0]["blocking_node_ids"] == ["blocker"]


def test_reports_non_orthogonal_edge_whose_fixed_ports_cross_node():
    result = _route("""
        <mxCell id="source" value="S" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="60" as="geometry"/></mxCell>
        <mxCell id="blocker" value="B" vertex="1" parent="1"><mxGeometry x="140" y="45" width="80" height="30" as="geometry"/></mxCell>
        <mxCell id="target" value="T" vertex="1" parent="1"><mxGeometry x="300" y="0" width="80" height="60" as="geometry"/></mxCell>
        <mxCell id="edge" edge="1" parent="1" source="source" target="target" style="edgeStyle=none;exitX=1;exitY=1;entryX=0;entryY=1;"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    assert result.issues[0]["code"] == "unsupported_colliding_edge_style"
