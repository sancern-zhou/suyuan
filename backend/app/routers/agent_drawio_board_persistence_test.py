from pathlib import Path


ROUTER_SOURCE = Path(__file__).with_name("agent.py").read_text(encoding="utf-8")


def test_chart_route_persists_drawio_board_from_tool_result_or_board_context():
    assert "latest_drawio_board = None" in ROUTER_SOURCE
    assert "(result.get(\"metadata\") or {}).get(\"generator\") == \"create_drawio_board\"" in ROUTER_SOURCE
    assert "(result.get(\"data\") or {}).get(\"artifact_kind\") == \"drawio_board\"" in ROUTER_SOURCE
    assert "latest_drawio_board = result.get(\"data\") or {}" in ROUTER_SOURCE
    assert "drawio_board=latest_drawio_board or drawio_board_context" in ROUTER_SOURCE
