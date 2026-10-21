"""The public and Agent tool URLs share response, routing and authorization rules."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.tool_routes import get_registry
from app.auth.models import CurrentUser


@pytest.fixture
def client():
    from app.api.routes import router as public_router
    from app.api.agent import router as agent_router
    app = FastAPI()
    app.include_router(public_router, prefix="/api")
    app.include_router(agent_router)
    state = SimpleNamespace(user=None, enabled=True)

    @app.middleware("http")
    async def identity(request, call_next):
        if state.user is not None:
            request.state.current_user = state.user
        return await call_next(request)

    class Registry:
        def get_tool_info(self, name):
            if name != "example":
                return None
            return {"name": name, "status": "enabled" if state.enabled else "disabled"}

        def get_tools_info(self):
            return [self.get_tool_info("example")]

        def get_categories(self):
            return ["query"]

        def set_tool_enabled(self, name, enabled):
            state.enabled = enabled
            return True

    app.dependency_overrides[get_registry] = lambda: Registry()
    with TestClient(app) as test_client:
        yield test_client, state


def login(state, *, admin=False):
    state.user = CurrentUser(id="u1", username="user", display_name="User", is_admin=admin)


@pytest.mark.parametrize("prefix", ["/api/tools", "/api/agent/tools"])
def test_tool_routes_require_identity(client, prefix):
    http, _ = client
    for suffix in ("", "/categories", "/example"):
        assert http.get(prefix + suffix).status_code == 401
    assert http.patch(prefix + "/example", json={"enabled": False}).status_code == 401


@pytest.mark.parametrize("suffix", ["", "/categories", "/example"])
def test_both_urls_return_the_same_response(client, suffix):
    http, state = client
    login(state)
    canonical = http.get("/api/tools" + suffix)
    alias = http.get("/api/agent/tools" + suffix)
    assert canonical.status_code == alias.status_code == 200
    assert canonical.json() == alias.json()
    if suffix == "/categories":
        assert canonical.json()["categories"] == ["query"]


@pytest.mark.parametrize("prefix", ["/api/tools", "/api/agent/tools"])
def test_status_updates_require_admin_and_are_visible_on_both_urls(client, prefix):
    http, state = client
    login(state)
    assert http.patch(prefix + "/example", json={"enabled": False}).status_code == 403
    assert state.enabled
    login(state, admin=True)
    assert http.patch(prefix + "/example", json={"enabled": False}).json()["enabled"] is False
    for url in ("/api/tools", "/api/agent/tools"):
        assert http.get(url + "/example").json()["tool"]["status"] == "disabled"
    assert http.patch(prefix + "/example", json={}).status_code == 422
    assert http.get(prefix + "/missing").status_code == 404
    assert http.patch(prefix + "/missing", json={"enabled": True}).status_code == 404
