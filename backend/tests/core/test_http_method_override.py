"""Tests for the X-HTTP-Method-Override middleware.

公网防火墙会重置 PUT/PATCH/DELETE 连接，前端把这些变更请求以 POST 加
``X-HTTP-Method-Override`` 头发送；这里验证中间件在路由前还原真实方法。
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.http_method_override import HttpMethodOverrideMiddleware


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(HttpMethodOverrideMiddleware)

    seen = {}

    @app.api_route(
        "/items/{item_id}",
        methods=["PUT", "DELETE", "PATCH", "POST"],
    )
    async def handle(item_id: int, request: Request) -> dict:
        seen["method"] = request.method
        return {"method": request.method, "item_id": item_id}

    @app.post("/plain")
    async def plain_post() -> dict:
        return {"method": "POST"}

    return app


@pytest.fixture()
def client():
    with TestClient(build_app()) as test_client:
        yield test_client


def test_direct_put_without_header_passes_through(client):
    response = client.put("/items/0", json={"label": "x"})
    assert response.status_code == 200
    assert response.json() == {"method": "PUT", "item_id": 0}


def test_post_with_override_put_is_routed_as_put(client):
    response = client.request(
        "POST", "/items/1", headers={"X-HTTP-Method-Override": "PUT"}, json={"label": "x"}
    )
    assert response.status_code == 200
    assert response.json() == {"method": "PUT", "item_id": 1}


def test_post_with_override_delete_is_routed_as_delete(client):
    response = client.request(
        "POST", "/items/2", headers={"X-HTTP-Method-Override": "DELETE"}
    )
    assert response.status_code == 200
    assert response.json() == {"method": "DELETE", "item_id": 2}


def test_post_with_override_patch_is_routed_as_patch(client):
    response = client.request(
        "POST", "/items/3", headers={"X-HTTP-Method-Override": "patch"}
    )
    assert response.status_code == 200
    assert response.json() == {"method": "PATCH", "item_id": 3}


def test_plain_post_stays_post(client):
    response = client.post("/plain")
    assert response.status_code == 200
    assert response.json() == {"method": "POST"}


def test_post_with_unknown_override_stays_post(client):
    # 非白名单方法不改写，请求仍按 POST 处理。
    response = client.request(
        "POST",
        "/items/4",
        headers={"X-HTTP-Method-Override": "TRACE"},
        json={},
    )
    assert response.status_code == 200
    assert response.json() == {"method": "POST", "item_id": 4}
