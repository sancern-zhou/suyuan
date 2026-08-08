from app.agent.context.context_builder import SimplifiedContextBuilder


def test_query_map_context_summary_includes_map_program_receipt():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.current_mode = "query"
    builder.map_context = {
        "type": "map_context",
        "session_id": "query_session_demo",
        "current_program": {"program_id": "mapprog_buffer"},
        "events": [
            {
                "type": "map_event",
                "event": "map_program_executed",
                "receipt": {
                    "program_id": "mapprog_buffer",
                    "status": "executed",
                    "layers": [
                        {
                            "layer_id": "huadu_station_buffer",
                            "status": "layer_rendered",
                            "feature_count": 1,
                        }
                    ],
                    "errors": [],
                },
                "active_layers": ["huadu_station_buffer"],
            }
        ],
    }

    summary = builder._build_map_context_user_summary()

    assert "event=map_program_executed" in summary
    assert "receipt_program=mapprog_buffer" in summary
    assert "receipt_status=executed" in summary
    assert "huadu_station_buffer:layer_rendered:1" in summary


def test_query_map_context_summary_includes_all_receipt_layers_and_data_ids():
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    builder.current_mode = "query"
    builder.map_context = {
        "type": "map_context",
        "session_id": "query_session_demo",
        "current_program": {"program_id": "mapprog_sanshui_pollution_sources_3km"},
        "events": [
            {
                "type": "map_event",
                "event": "map_program_executed",
                "receipt": {
                    "program_id": "mapprog_sanshui_pollution_sources_3km",
                    "status": "executed",
                    "layers": [
                        {"layer_id": "pm25_high_stations", "status": "layer_rendered", "feature_count": 5},
                        {"layer_id": "sanshui_3km_buffer", "status": "layer_rendered", "feature_count": 1},
                        {"layer_id": "sanshui_pollution_sources", "status": "layer_rendered", "feature_count": 51},
                        {"layer_id": "sanshui_pollution_sources_v2", "status": "layer_rendered", "feature_count": 51},
                        {"layer_id": "sanshui_pollution_sources_final", "status": "layer_rendered", "feature_count": 51},
                        {
                            "layer_id": "sanshui_pollution_sources_3km",
                            "status": "layer_rendered",
                            "feature_count": 51,
                            "data_id": "spatial_point_asset:v1:15c312211d3c496bb356f9af9d725605",
                        },
                    ],
                    "errors": [],
                },
                "active_layers": ["pm25_high_stations", "sanshui_3km_buffer"],
            }
        ],
    }

    summary = builder._build_map_context_user_summary()

    assert "sanshui_pollution_sources_3km:layer_rendered:51" in summary
    assert "data_id=spatial_point_asset:v1:15c312211d3c496bb356f9af9d725605" in summary
