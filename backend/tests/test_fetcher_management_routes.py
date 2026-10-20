"""Management requests from every web process operate on the worker singleton."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.fetcher_worker_routes import get_fetcher_scheduler
from app.core.fetcher_worker_proxy import FetcherWorkerProxyMiddleware
from app.lifecycle.social_worker_api import create_social_worker_api_app


@pytest.fixture
def worker(monkeypatch):
    class Scheduler:
        fetchers = {"consultation_file_fetcher": None, "monthly_consultation_file_fetcher": None}
        running = False
        starts = 0
        stops = 0
        triggered = []
        paused = []
        resumed = []

        def list_fetchers(self):
            return list(self.fetchers)

        def get_status(self):
            return {"scheduler_running": self.running, "fetchers": {}}

        def is_running(self):
            return self.running

        def start(self):
            self.running = True
            self.starts += 1

        def stop(self):
            self.running = False
            self.stops += 1

        async def run_now(self, name):
            self.triggered.append(name)

        def pause(self, name):
            self.paused.append(name)

        def resume(self, name):
            self.resumed.append(name)

    scheduler = Scheduler()
    app = create_social_worker_api_app(SimpleNamespace(channel_manager=None), internal_token="secret")
    app.dependency_overrides[get_fetcher_scheduler] = lambda: scheduler
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.ASGITransport(app=app), **kwargs))
    return scheduler


def web_client(*, enabled=True):
    app = FastAPI()
    app.add_middleware(FetcherWorkerProxyMiddleware, app_role="web",
                       worker_base_url="http://worker", worker_token="secret",
                       fetchers_enabled=enabled)
    return TestClient(app)


def test_multiple_web_processes_manage_the_same_worker_scheduler(worker):
    with web_client() as first, web_client() as second:
        assert first.get("/api/fetchers/list").json()["count"] == 2
        assert first.post("/api/fetchers/start").status_code == 200
        assert second.post("/api/fetchers/start").status_code == 200
        assert second.get("/api/fetchers/status").json()["scheduler_running"]
        assert second.post("/api/fetchers/stop").status_code == 200
        assert first.post("/api/fetchers/stop").status_code == 200
        assert not first.get("/api/fetchers/status").json()["scheduler_running"]
    assert worker.starts == worker.stops == 1


def test_worker_trigger_cascade_and_unknown_fetcher(worker):
    with web_client() as client:
        assert client.post("/api/fetchers/trigger/consultation_file_fetcher").status_code == 200
        assert worker.triggered == ["consultation_file_fetcher", "monthly_consultation_file_fetcher"]
        assert client.post("/api/fetchers/pause/consultation_file_fetcher").status_code == 200
        assert client.post("/api/fetchers/resume/consultation_file_fetcher").status_code == 200
        for operation in ("trigger", "pause", "resume"):
            assert client.post(f"/api/fetchers/{operation}/missing").status_code == 404


def test_disabled_fetchers_do_not_fall_back_to_local_scheduler(worker):
    with web_client(enabled=False) as client:
        assert client.post("/api/fetchers/start").status_code == 404
    assert worker.starts == 0


def test_worker_unavailable_returns_503_without_local_fallback(monkeypatch):
    original_client = httpx.AsyncClient

    async def unavailable(request):
        raise httpx.ConnectError("worker is down", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(unavailable), **kwargs))
    with web_client() as client:
        for path, method in (("list", "get"), ("start", "post"), ("stop", "post")):
            assert getattr(client, method)(f"/api/fetchers/{path}").status_code == 503


@pytest.mark.parametrize("enabled", [True, False])
async def test_real_scheduler_can_stop_and_restart_without_losing_jobs(enabled):
    import asyncio
    from app.fetchers.base.scheduler import FetcherScheduler

    async def run():
        pass

    scheduler = FetcherScheduler()
    fetcher = SimpleNamespace(name="example", description="test", schedule="0 0 1 1 *", run=run, enabled=enabled)
    scheduler.register(fetcher)
    try:
        scheduler.start()
        assert scheduler.scheduler.get_job("example") is not None
        scheduler.stop()
        await asyncio.sleep(0)
        scheduler.start()
        job = scheduler.scheduler.get_job("example")
        assert job is not None
        if not enabled:
            assert job.next_run_time is None
    finally:
        scheduler.stop()
        await asyncio.sleep(0)
