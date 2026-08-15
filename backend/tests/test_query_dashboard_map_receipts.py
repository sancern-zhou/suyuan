from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import query_dashboard_routes
from app.services.map_program_receipts import map_program_receipt_store


def test_map_program_receipt_can_be_recorded_and_read_back():
    map_program_receipt_store.clear()
    app = FastAPI()
    app.include_router(query_dashboard_routes.router, prefix="/api")
    client = TestClient(app)

    payload = {
        "program_id": "mapprog_buffer",
        "status": "executed",
        "layers": [
            {
                "layer_id": "huadu_station_buffer_3km",
                "layer_type": "polygon",
                "data_id": "spatial_polygon_asset:v1:abc",
                "status": "layer_rendered",
                "visible": True,
                "feature_count": 1,
            }
        ],
        "errors": [],
    }

    post_response = client.post(
        "/api/query-dashboard/map-program-receipts",
        json={"session_id": "query_session_demo", "receipt": payload},
    )

    assert post_response.status_code == 200
    assert post_response.json()["receipt"]["program_id"] == "mapprog_buffer"

    get_response = client.get(
        "/api/query-dashboard/map-program-receipts/query_session_demo/mapprog_buffer"
    )

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["session_id"] == "query_session_demo"
    assert body["receipt"]["status"] == "executed"
    assert body["receipt"]["layers"][0]["feature_count"] == 1


def test_map_program_receipt_updates_pending_program_status():
    map_program_receipt_store.clear()
    map_program_receipt_store.register_pending(
        "query_session_demo",
        {
            "type": "map_program",
            "program_id": "mapprog_buffer",
            "state": {"layers": []},
        },
    )

    app = FastAPI()
    app.include_router(query_dashboard_routes.router, prefix="/api")
    client = TestClient(app)

    pending_response = client.get(
        "/api/query-dashboard/map-program-status/query_session_demo/mapprog_buffer"
    )
    assert pending_response.status_code == 200
    assert pending_response.json()["program"]["status"] == "pending"

    client.post(
        "/api/query-dashboard/map-program-receipts",
        json={
            "session_id": "query_session_demo",
            "receipt": {
                "program_id": "mapprog_buffer",
                "status": "executed",
                "layers": [{"layer_id": "buffer", "status": "layer_rendered", "feature_count": 1}],
                "errors": [],
            },
        },
    )

    status_response = client.get(
        "/api/query-dashboard/map-program-status/query_session_demo/mapprog_buffer"
    )
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["program"]["status"] == "executed"
    assert body["program"]["receipt"]["layers"][0]["feature_count"] == 1
