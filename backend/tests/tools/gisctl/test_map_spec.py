from app.schemas.gis_map import MapLayerSpec, MapProgram
from app.tools.gisctl.map_spec import create_point_layer_program, create_set_view_program


def test_map_program_accepts_point_layer_with_lifecycle_defaults():
    program = MapProgram(
        program_id="mapprog_turn_12",
        intent="Show high PM2.5 stations",
        state={
            "view": {"fit_bounds": True},
            "layers": [
                MapLayerSpec(
                    id="turn_12_pm25_high",
                    name="PM2.5 high stations",
                    layer_type="point",
                    data={"type": "data_id", "id": "air_quality_station_hour:v1:abc123"},
                    geometry={
                        "type": "point",
                        "longitude_field": "longitude",
                        "latitude_field": "latitude",
                    },
                    style={
                        "type": "classified",
                        "field": "pm25",
                        "breaks": [35, 75, 115],
                        "colors": ["#facc15", "#fb923c", "#ef4444"],
                    },
                )
            ],
        },
        lineage={"source_data_ids": ["air_quality_station_hour:v1:abc123"], "turn_id": "turn_12"},
    )

    payload = program.model_dump()
    layer = payload["state"]["layers"][0]
    assert payload["type"] == "map_program"
    assert payload["version"] == "0.1"
    assert layer["lifecycle"]["scope"] == "turn"
    assert layer["lifecycle"]["visible"] is True
    assert layer["lifecycle"]["replace_policy"] == "append"


def test_map_program_rejects_layer_without_data_reference():
    try:
        MapLayerSpec(
            id="bad_layer",
            name="Bad layer",
            layer_type="point",
            data={"type": "data_id"},
            geometry={"type": "point", "longitude_field": "lon", "latitude_field": "lat"},
        )
    except ValueError as exc:
        assert "data.id is required" in str(exc)
    else:
        raise AssertionError("MapLayerSpec should reject incomplete data reference")


def test_create_point_layer_program_from_data_id():
    program = create_point_layer_program(
        data_id="air_quality_station_hour:v1:abc123",
        layer_id="turn_12_pm25_high",
        name="PM2.5 high stations",
        longitude_field="longitude",
        latitude_field="latitude",
        color_by="pm25",
        breaks=[35, 75, 115],
        colors=["#facc15", "#fb923c", "#ef4444"],
        fit_bounds=True,
        turn_id="turn_12",
    )

    payload = program.model_dump()
    layer = payload["state"]["layers"][0]
    assert payload["type"] == "map_program"
    assert payload["state"]["view"]["fit_bounds"] is True
    assert layer["data"]["id"] == "air_quality_station_hour:v1:abc123"
    assert layer["style"]["field"] == "pm25"
    assert layer["lifecycle"]["replace_policy"] == "append"


def test_create_set_view_program_without_layers():
    program = create_set_view_program(
        center=[113.2644, 23.1291],
        zoom=10,
        name="广州",
        turn_id="turn_13",
    )

    payload = program.model_dump()
    assert payload["type"] == "map_program"
    assert payload["program_id"] == "mapprog_set_view_guang_zhou"
    assert payload["state"]["view"]["center"] == [113.2644, 23.1291]
    assert payload["state"]["view"]["zoom"] == 10
    assert payload["state"]["layers"] == []
    assert payload["lineage"]["turn_id"] == "turn_13"


def test_create_set_view_program_uses_stable_slug_for_other_guangdong_city_name():
    program = create_set_view_program(center=[113.1214, 23.0219], zoom=10, name="佛山")

    assert program.program_id == "mapprog_set_view_city_440600"
