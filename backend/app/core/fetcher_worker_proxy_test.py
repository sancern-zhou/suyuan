from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_fetcher_proxy_matches_only_fetcher_management_routes():
    from app.core.fetcher_worker_proxy import (
        build_worker_fetchers_url,
        should_proxy_fetchers_request,
    )

    assert should_proxy_fetchers_request("/api/fetchers/status", "web")
    assert should_proxy_fetchers_request("/api/fetchers/trigger/example", "web")
    assert should_proxy_fetchers_request("/api/fetchers/pause/example", "web")
    assert should_proxy_fetchers_request("/api/fetchers/resume/example", "web")

    assert not should_proxy_fetchers_request("/api/fetchers/era5/historical", "web")
    assert not should_proxy_fetchers_request("/api/system/status", "web")
    assert not should_proxy_fetchers_request("/api/fetchers/status", "worker")
    assert not should_proxy_fetchers_request(
        "/api/fetchers/status", "web", fetchers_enabled=False
    )

    assert (
        build_worker_fetchers_url(
            "http://127.0.0.1:8011/",
            "/api/fetchers/status",
            "verbose=1",
        )
        == "http://127.0.0.1:8011/api/fetchers/status?verbose=1"
    )


def test_worker_internal_api_exposes_lifecycle_fetcher_status(monkeypatch):
    from app.lifecycle.social_worker_api import create_social_worker_api_app
    from app.services import lifecycle_manager

    class FakeScheduler:
        def get_status(self):
            return {
                "scheduler_running": True,
                "fetchers": {
                    "consultation_file_fetcher": {
                        "name": "consultation_file_fetcher",
                        "description": "consultation",
                        "schedule": "0 7 * * *",
                        "enabled": True,
                        "status": "idle",
                        "version": "1.0.0",
                    }
                },
            }

    monkeypatch.setattr(lifecycle_manager, "get_fetcher_scheduler", lambda: FakeScheduler())

    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    client = TestClient(app)

    forbidden = client.get("/api/fetchers/status")
    assert forbidden.status_code == 403

    response = client.get("/api/fetchers/status", headers={"x-social-worker-token": "secret"})
    assert response.status_code == 200
    assert response.json()["scheduler_running"] is True
    assert "consultation_file_fetcher" in response.json()["fetchers"]
