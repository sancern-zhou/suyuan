from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import query_dashboard_routes
from app.schemas.query_dashboard import DashboardModule, DashboardOverviewResponse


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
