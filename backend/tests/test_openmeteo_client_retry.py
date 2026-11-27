from types import SimpleNamespace

import httpx
import pytest

from app.external_apis import openmeteo_client


class FakeAsyncClient:
    responses = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url, params):
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(status_code, body=None, headers=None):
    return SimpleNamespace(
        status_code=status_code,
        headers=headers or {},
        text=str(body or {}),
        json=lambda: body or {},
    )


@pytest.fixture
def client(monkeypatch):
    FakeAsyncClient.responses = []
    sleeps = []
    monkeypatch.setattr(openmeteo_client.httpx, "AsyncClient", FakeAsyncClient)

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(openmeteo_client.asyncio, "sleep", sleep)
    monkeypatch.setattr(openmeteo_client.random, "uniform", lambda _start, _end: 0.0)
    instance = openmeteo_client.OpenMeteoClient()
    return instance, sleeps


@pytest.mark.asyncio
async def test_forecast_retries_timeout_with_exponential_backoff(client):
    instance, sleeps = client
    FakeAsyncClient.responses = [
        httpx.ReadTimeout("first"),
        httpx.ConnectError("second"),
        response(200, {"hourly": {}}),
    ]

    result = await instance.fetch_forecast(34.02, 113.85)

    assert result == {"hourly": {}}
    assert sleeps == [2, 4]


@pytest.mark.asyncio
async def test_current_weather_retries_temporary_http_errors(client):
    instance, sleeps = client
    FakeAsyncClient.responses = [
        response(503),
        response(429, headers={"Retry-After": "3"}),
        response(200, {"current": {}}),
    ]

    result = await instance.fetch_current_weather(34.02, 113.85)

    assert result == {"current": {}}
    assert sleeps == [2, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["fetch_forecast", "fetch_current_weather"])
async def test_client_does_not_retry_bad_requests(client, method_name):
    instance, sleeps = client
    FakeAsyncClient.responses = [response(400, {"error": True})]

    with pytest.raises(Exception, match="API error: 400"):
        await getattr(instance, method_name)(34.02, 113.85)

    assert not FakeAsyncClient.responses
    assert sleeps == []


@pytest.mark.asyncio
async def test_forecast_reports_all_failed_attempts(client):
    instance, sleeps = client
    instance.max_retries = 2
    FakeAsyncClient.responses = [httpx.ReadTimeout("still unavailable")] * 3

    with pytest.raises(Exception, match="after 3 attempts") as exc_info:
        await instance.fetch_forecast(34.02, 113.85)

    assert isinstance(exc_info.value.__cause__, httpx.ReadTimeout)
    assert sleeps == [2, 4]
