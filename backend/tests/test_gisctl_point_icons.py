from app.tools.gisctl.map_spec import create_point_layer_program


def test_point_layer_program_carries_controlled_icon_style():
    program = create_point_layer_program(
        data_id="pollution_source:v1:test",
        layer_id="pollution_sources",
        name="污染源",
        longitude_field="longitude",
        latitude_field="latitude",
        icon="factory",
        icon_by="source_type",
        icon_map={"工业源": "factory", "扬尘源": "dust", "站点": "station"},
        default_icon="pollution_source",
    )

    style = program.state.layers[0].style

    assert style["icon"] == "factory"
    assert style["icon_by"] == "source_type"
    assert style["icon_map"] == {"工业源": "factory", "扬尘源": "dust", "站点": "station"}
    assert style["default_icon"] == "pollution_source"
