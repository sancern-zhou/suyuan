from app.tools.visualization.create_drawio_board.xml_utils import (
    DrawioXmlError,
    apply_drawio_operations,
    normalize_drawio_xml,
)


def test_normalize_wraps_mxcell_fragment_into_mxfile():
    xml = '<mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>'

    result = normalize_drawio_xml(xml)

    assert result.startswith("<mxfile")
    assert "<mxGraphModel" in result
    assert '<mxCell id="0"' in result
    assert '<mxCell id="1" parent="0"' in result
    assert 'id="2"' in result


def test_normalize_preserves_cells_from_full_mxfile():
    xml = """
    <mxfile host="draw.io">
      <diagram id="page-1" name="Page-1">
        <mxGraphModel>
          <root>
            <mxCell id="0"/>
            <mxCell id="1" parent="0"/>
            <mxCell id="2" value="API" vertex="1" parent="1">
              <mxGeometry x="0" y="0" width="80" height="40" as="geometry"/>
            </mxCell>
          </root>
        </mxGraphModel>
      </diagram>
    </mxfile>
    """

    result = normalize_drawio_xml(xml)

    assert result.startswith("<mxfile")
    assert result.count('id="0"') == 1
    assert result.count('id="1"') == 1
    assert 'id="2"' in result


def test_normalize_rejects_duplicate_ids():
    xml = """
    <mxCell id="2" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="2" value="B" vertex="1" parent="1"><mxGeometry x="120" y="0" width="80" height="40" as="geometry"/></mxCell>
    """

    try:
        normalize_drawio_xml(xml)
    except DrawioXmlError as exc:
        assert "duplicate id" in str(exc).lower()
    else:
        raise AssertionError("Expected duplicate id validation failure")


def test_normalize_rejects_unknown_edge_endpoint():
    xml = """
    <mxCell id="2" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
    <mxCell id="e1" edge="1" parent="1" source="2" target="missing"><mxGeometry relative="1" as="geometry"/></mxCell>
    """

    try:
        normalize_drawio_xml(xml)
    except DrawioXmlError as exc:
        assert "unknown target" in str(exc).lower()
    else:
        raise AssertionError("Expected unknown target validation failure")


def test_apply_operations_add_update_delete_and_cascade_edges():
    base = normalize_drawio_xml("""
    <mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="3" value="DB" vertex="1" parent="1"><mxGeometry x="240" y="40" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="e1" edge="1" parent="1" source="2" target="3"><mxGeometry relative="1" as="geometry"/></mxCell>
    """)

    updated = apply_drawio_operations(base, [
        {
            "operation": "update",
            "cell_id": "2",
            "new_xml": '<mxCell id="2" value="Auth API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="140" height="60" as="geometry"/></mxCell>',
        },
        {
            "operation": "add",
            "cell_id": "4",
            "new_xml": '<mxCell id="4" value="Cache" vertex="1" parent="1"><mxGeometry x="440" y="40" width="120" height="60" as="geometry"/></mxCell>',
        },
        {"operation": "delete", "cell_id": "3"},
    ])

    assert "Auth API" in updated
    assert 'id="4"' in updated
    assert 'id="3"' not in updated
    assert 'id="e1"' not in updated


def test_delete_cascades_to_child_cells():
    base = normalize_drawio_xml("""
    <mxCell id="2" value="Group" vertex="1" parent="1"><mxGeometry x="40" y="40" width="200" height="120" as="geometry"/></mxCell>
    <mxCell id="3" value="Child" vertex="1" parent="2"><mxGeometry x="60" y="60" width="80" height="40" as="geometry"/></mxCell>
    """)

    updated = apply_drawio_operations(base, [{"operation": "delete", "cell_id": "2"}])

    assert 'id="2"' not in updated
    assert 'id="3"' not in updated


def test_structured_operations_update_selected_cell_without_new_xml():
    base = normalize_drawio_xml("""
    <mxCell id="2" value="API" style="rounded=1;fillColor=#dae8fc;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="3" value="DB" vertex="1" parent="1"><mxGeometry x="240" y="40" width="120" height="60" as="geometry"/></mxCell>
    """)

    updated = apply_drawio_operations(
        base,
        [
            {"operation": "update_label", "target": "selected", "label": "认证服务"},
            {"operation": "update_style", "target": "selected", "style_patch": {"fillColor": "#f8cecc", "strokeColor": "#b85450"}},
            {"operation": "move_resize", "target": "selected", "geometry": {"x": 80, "y": 90, "width": 180}},
        ],
        selected_cells=[{"id": "2"}],
    )

    assert 'id="2"' in updated
    assert 'value="认证服务"' in updated
    assert "fillColor=#f8cecc" in updated
    assert "strokeColor=#b85450" in updated
    assert 'x="80"' in updated
    assert 'y="90"' in updated
    assert 'width="180"' in updated
    assert 'height="60"' in updated
    assert 'id="3"' in updated


def test_connect_and_delete_with_edges_structured_operations():
    base = normalize_drawio_xml("""
    <mxCell id="2" value="API" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="3" value="DB" vertex="1" parent="1"><mxGeometry x="240" y="40" width="120" height="60" as="geometry"/></mxCell>
    """)

    connected = apply_drawio_operations(
        base,
        [
            {
                "operation": "connect",
                "cell_id": "edge_api_db",
                "source_cell_id": "selected",
                "target_cell_id": "3",
                "label": "写入",
            }
        ],
        selected_cells=[{"id": "2"}],
    )

    assert 'id="edge_api_db"' in connected
    assert 'edge="1"' in connected
    assert 'source="2"' in connected
    assert 'target="3"' in connected
    assert 'value="写入"' in connected

    deleted = apply_drawio_operations(
        connected,
        [{"operation": "delete_with_edges", "target": "selected"}],
        selected_cells=[{"id": "2"}],
    )

    assert 'id="2"' not in deleted
    assert 'id="edge_api_db"' not in deleted
    assert 'id="3"' in deleted
