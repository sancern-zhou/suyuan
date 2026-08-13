from app.routers.agent import (
    extract_map_program_from_tool_result_event,
    is_drawio_board_tool_result,
    merge_map_program_into_scene_metadata,
    merge_map_scene_metadata,
)


def test_merge_map_scene_metadata_persists_current_program():
    program = {
        "type": "map_program",
        "program_id": "mapprog_simulated_pollution_sources",
        "state": {
            "layers": [
                {"id": "huadu_normal_buffer_3km"},
                {"id": "simulated_pollution_sources"},
            ]
        },
    }

    metadata = merge_map_scene_metadata(
        {"mode": "query"},
        {
            "type": "map_context",
            "current_program": program,
            "events": [],
        },
    )

    assert metadata["mode"] == "query"
    assert metadata["map_scene"]["current_map_program"] == program
    assert metadata["map_scene"]["updated_at"]


def test_merge_map_scene_metadata_ignores_missing_program():
    metadata = merge_map_scene_metadata({"mode": "query"}, {"events": []})

    assert metadata == {"mode": "query"}


def test_merge_map_scene_metadata_merges_view_without_dropping_layers():
    buffer_program = {
        "type": "map_program",
        "program_id": "mapprog_buffer",
        "state": {
            "view": {"fit_bounds": True},
            "layers": [{"id": "huadu_normal_buffer_3km"}],
        },
        "lineage": {"source_data_ids": ["spatial_polygon_asset:v1:buffer"]},
    }
    set_view_program = {
        "type": "map_program",
        "program_id": "mapprog_set_view_huadu",
        "state": {
            "view": {"center": [113.2146, 23.3917], "zoom": 13},
            "layers": [],
        },
        "lineage": {},
    }

    metadata = merge_map_scene_metadata(
        {"map_scene": {"current_map_program": buffer_program}},
        {"current_program": set_view_program},
    )

    current_program = metadata["map_scene"]["current_map_program"]
    assert current_program["program_id"] == "mapprog_set_view_huadu"
    assert current_program["state"]["view"] == {"center": [113.2146, 23.3917], "zoom": 13}
    assert current_program["state"]["layers"] == [{"id": "huadu_normal_buffer_3km"}]
    assert current_program["lineage"]["source_data_ids"] == ["spatial_polygon_asset:v1:buffer"]


def test_merge_map_program_into_scene_metadata_reads_gisctl_result_data_program():
    program = {
        "type": "map_program",
        "program_id": "mapprog_huadu_normal_station",
        "state": {
            "layers": [{"id": "huadu_normal_station"}],
        },
    }
    event_data = {
        "result": {
            "status": "success",
            "data": {"map_program": program},
        },
    }

    extracted = extract_map_program_from_tool_result_event(event_data)
    metadata = merge_map_program_into_scene_metadata({}, extracted)

    assert extracted == program
    assert metadata["map_scene"]["current_map_program"]["state"]["layers"] == [
        {"id": "huadu_normal_station"}
    ]


def test_drawio_board_detection_ignores_list_data_tool_results():
    result = {
        "status": "success",
        "data": [{"name": "广州"}],
        "metadata": {"tool_name": "query_gd_suncere_city_hour"},
    }

    assert is_drawio_board_tool_result(result) is False


def test_drawio_board_detection_includes_structured_tool_failures():
    result = {
        "success": False,
        "data": {"error_code": "operation_cell_id_required", "retryable": True},
        "metadata": {"tool_name": "create_drawio_board"},
    }

    assert is_drawio_board_tool_result(result) is True
