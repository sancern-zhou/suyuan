from pathlib import Path


ROUTER_SOURCE = Path(__file__).with_name("agent.py").read_text(encoding="utf-8")


def test_board_route_persists_drawio_board_from_tool_result_or_board_context():
    assert "latest_drawio_board = None" in ROUTER_SOURCE
    assert "metadata.get(\"generator\") == \"create_drawio_board\"" in ROUTER_SOURCE
    assert "data.get(\"artifact_kind\") == \"drawio_board\"" in ROUTER_SOURCE
    assert "result_data = result.get(\"data\") or {}" in ROUTER_SOURCE
    assert "drawio_xml = _drawio_xml_from_result(result)" in ROUTER_SOURCE
    assert "latest_drawio_board = {" in ROUTER_SOURCE
    assert "\"current_xml\": drawio_xml" in ROUTER_SOURCE
    assert "\"xml\": drawio_xml" in ROUTER_SOURCE
    assert "drawio_board=latest_drawio_board or drawio_board_context" in ROUTER_SOURCE


def test_board_route_restores_drawio_board_context_from_session_metadata():
    assert "drawio_board_context = request.board_context if request.mode == \"board\" else None" in ROUTER_SOURCE
    assert "nonlocal actual_session_id, conversation_history, collected_visuals, latest_drawio_board, drawio_board_context, seen_visual_ids" in ROUTER_SOURCE
    assert "stored_drawio_board = preloaded_session.metadata.get(\"drawio_board\")" in ROUTER_SOURCE
    assert "resolve_context_reference(" in ROUTER_SOURCE
    assert "analyze_kwargs[\"board_context\"] = drawio_board_context" in ROUTER_SOURCE
    assert "board_context_restored_from_session_metadata" in ROUTER_SOURCE
    assert "except HTTPException:\n        raise\n    except Exception as e:" in ROUTER_SOURCE
