import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import admin, agent, fetchers, routes, skills_routes
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser


NON_ADMIN = CurrentUser(id="viewer", username="viewer", display_name="Viewer", is_admin=False)
ADMIN = CurrentUser(id="admin", username="admin", display_name="Admin", is_admin=True)


def make_client(router, user=NON_ADMIN):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: user
    return TestClient(app)


def request(client: TestClient, method: str, path: str, json_body=None):
    kwargs = {}
    if json_body is not None:
        kwargs["json"] = json_body
    return client.request(method, path, **kwargs)


def test_public_health_remains_available():
    app = FastAPI()
    app.include_router(routes.router)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_admin_workflow_requires_admin():
    response = make_client(admin.router).get("/api/admin/workflow")

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_admin_workflow_allows_admin():
    response = make_client(admin.router, ADMIN).get("/api/admin/workflow")

    assert response.status_code == 200
    assert response.json()["workflow_name"] == "大气环境智能分析与决策支持工作流"


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("POST", "/fetchers/era5/historical", {"date": "2026-08-01"}),
        ("POST", "/fetchers/jining_era5/fetch", {"date": "2026-08-01"}),
        ("GET", "/fetchers/jining_era5/stations", None),
        ("GET", "/tools", None),
        ("GET", "/tools/example", None),
        ("PATCH", "/tools/example", {"enabled": True}),
        ("GET", "/tools/categories", None),
    ],
)
def test_management_routes_require_admin(method, path, json_body):
    response = request(make_client(routes.router), method, path, json_body)

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/fetchers/status", None),
        ("POST", "/api/fetchers/trigger/example", None),
        ("POST", "/api/fetchers/pause/example", None),
        ("POST", "/api/fetchers/resume/example", None),
        ("GET", "/api/fetchers/list", None),
        ("POST", "/api/fetchers/start", None),
        ("POST", "/api/fetchers/stop", None),
    ],
)
def test_fetchers_router_requires_admin(method, path, json_body):
    response = request(make_client(fetchers.router), method, path, json_body)

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/agent/tools/example", None),
        ("GET", "/api/agent/tools/categories", None),
        ("PATCH", "/api/agent/tools/example", {"enabled": False}),
    ],
)
def test_agent_tool_management_requires_admin(method, path, json_body):
    response = request(make_client(agent.router), method, path, json_body)

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_agent_tool_list_stays_available_for_authenticated_users(monkeypatch):
    monkeypatch.setattr(
        agent.global_tool_registry,
        "get_tools_info",
        lambda: [{"name": "mock-tool", "category": "utility"}],
    )

    response = make_client(agent.router).get("/api/agent/tools")

    assert response.status_code == 200
    assert response.json() == {
        "tools": [{"name": "mock-tool", "category": "utility"}],
        "count": 1,
    }


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/skills/drafts", None),
        ("GET", "/api/skills/drafts/example", None),
        ("GET", "/api/skills/example", None),
        ("PUT", "/api/skills/drafts/example", {"content": "# draft"}),
        ("PUT", "/api/skills/example", {"content": "# skill"}),
        ("POST", "/api/skills/refresh-index", None),
    ],
)
def test_skill_management_routes_require_admin(method, path, json_body):
    response = request(make_client(skills_routes.router), method, path, json_body)

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_skill_list_stays_available_for_authenticated_users(monkeypatch):
    async def fake_execute(self, keyword=None):
        return {
            "success": True,
            "data": {
                "skills": [
                    {
                        "file": "backend/docs/skills/example.md",
                        "name": "Example",
                    }
                ],
            },
            "summary": "ok",
        }

    monkeypatch.setattr(
        "app.tools.utility.skill_management.list_skills_tool.ListSkillsTool.execute",
        fake_execute,
    )

    response = make_client(skills_routes.router).get("/api/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["skills"][0]["id"] == "example"
