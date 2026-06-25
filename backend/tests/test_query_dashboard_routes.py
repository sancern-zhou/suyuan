from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import query_dashboard_routes
from app.schemas.query_dashboard import DashboardModule, DashboardOverviewResponse
from app.services.data_registry import data_registry


class StubService:
    def __init__(self):
        self.include = None

    def build_guangdong_overview(self, include=None):
        self.include = include
        return DashboardOverviewResponse(
            generated_at="2026-06-22T10:00:00+08:00",
            modules={
                "realtime": DashboardModule(
                    status="success",
                    summary={"record_count": 1},
                    cities=[{"city": "广州", "AQI": 42}],
                )
            },
        )


def test_get_guangdong_overview_returns_dashboard_contract():
    service = StubService()
    app = FastAPI()
    app.dependency_overrides[query_dashboard_routes.get_query_dashboard_service] = lambda: service
    app.include_router(query_dashboard_routes.router, prefix="/api")

    response = TestClient(app).get("/api/query-dashboard/guangdong-overview?include=realtime,layers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["modules"]["realtime"]["cities"][0]["city"] == "广州"
    assert service.include == ["realtime", "layers"]


def test_get_map_data_accepts_geojson_geometry_without_lon_lat():
    data_registry.register_dataset(
        "spatial_polygon_asset",
        "v1",
        [
            {
                "name": "花都师范 3km 缓冲区",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [113.2, 23.1],
                        [113.3, 23.1],
                        [113.3, 23.2],
                        [113.2, 23.1],
                    ]],
                },
            }
        ],
        data_id="spatial_polygon_asset:v1:route_test_buffer",
    )
    app = FastAPI()
    app.include_router(query_dashboard_routes.router, prefix="/api")

    response = TestClient(app).get(
        "/api/query-dashboard/map-data/spatial_polygon_asset%3Av1%3Aroute_test_buffer"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["features"][0]["geometry"]["type"] == "Polygon"
    assert payload["features"][0]["properties"]["name"] == "花都师范 3km 缓冲区"
