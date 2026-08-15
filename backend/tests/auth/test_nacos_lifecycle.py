from types import SimpleNamespace
import json

import pytest

from app.lifecycle.nacos import NacosLifecycle
from config.settings import Settings


class FakeNamingClient:
    def __init__(self, *, register_error=None):
        self.register_error = register_error
        self.registered = []
        self.deregistered = []
        self.shutdown_called = False

    async def register_instance(self, request):
        if self.register_error:
            raise self.register_error
        self.registered.append(request)
        return True

    async def deregister_instance(self, request):
        self.deregistered.append(request)
        return True

    async def shutdown(self):
        self.shutdown_called = True


def _settings(**overrides):
    values = {
        "_env_file": None,
        "auth_mode": "company",
        "nacos_server_addresses": "http://10.10.204.80:8848",
        "nacos_namespace": "normcraft-ai",
        "nacos_group": "DEFAULT_GROUP",
        "nacos_service_name": "suyuan-agent",
        "nacos_cluster_name": "DEFAULT",
        "nacos_instance_ip": "10.10.204.81",
        "nacos_instance_port": 8000,
        "nacos_register_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_registers_expected_ephemeral_suyuan_instance():
    app = SimpleNamespace(state=SimpleNamespace())
    client = FakeNamingClient()

    async def factory(config):
        return client

    lifecycle = NacosLifecycle(_settings(), naming_factory=factory)
    await lifecycle.start(app)

    assert app.state.nacos_ready is True
    request = client.registered[0]
    assert request.service_name == "suyuan-agent"
    assert request.group_name == "DEFAULT_GROUP"
    assert request.cluster_name == "DEFAULT"
    assert (request.ip, request.port, request.ephemeral) == ("10.10.204.81", 8000, True)
    assert request.metadata == {
        "system": "Suyuan",
        "service": "suyuan-agent",
        "sysCode": "SUYUAN",
    }


@pytest.mark.asyncio
async def test_shutdown_deregisters_and_closes_client():
    app = SimpleNamespace(state=SimpleNamespace())
    client = FakeNamingClient()

    async def factory(config):
        return client

    lifecycle = NacosLifecycle(_settings(), naming_factory=factory)
    await lifecycle.start(app)
    await lifecycle.stop(app)

    assert len(client.deregistered) == 1
    assert client.deregistered[0].service_name == "suyuan-agent"
    assert client.shutdown_called is True
    assert app.state.nacos_ready is False


@pytest.mark.asyncio
async def test_shutdown_error_does_not_abort_application_cleanup():
    app = SimpleNamespace(state=SimpleNamespace())
    client = FakeNamingClient()

    async def broken_shutdown():
        client.shutdown_called = True
        raise TypeError("internal stop returned a non-awaitable value")

    client.shutdown = broken_shutdown

    async def factory(config):
        return client

    lifecycle = NacosLifecycle(_settings(), naming_factory=factory)
    await lifecycle.start(app)
    await lifecycle.stop(app)

    assert client.shutdown_called is True
    assert lifecycle._client is None
    assert app.state.nacos_ready is False


@pytest.mark.asyncio
async def test_production_registration_failure_aborts_startup():
    app = SimpleNamespace(state=SimpleNamespace())

    async def factory(config):
        raise RuntimeError("nacos unavailable")

    lifecycle = NacosLifecycle(
        _settings(
            environment="production",
            auth_service_url="http://auth",
            share_signing_secret="secret",
        ),
        naming_factory=factory,
    )

    with pytest.raises(RuntimeError, match="nacos unavailable"):
        await lifecycle.start(app)
    assert app.state.nacos_ready is False


@pytest.mark.asyncio
async def test_nonproduction_registration_failure_is_reported_without_aborting():
    app = SimpleNamespace(state=SimpleNamespace())

    async def factory(config):
        raise RuntimeError("nacos unavailable")

    lifecycle = NacosLifecycle(_settings(), naming_factory=factory)
    await lifecycle.start(app)

    assert app.state.nacos_ready is False
    assert app.state.nacos_status["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_production_readiness_requires_auth_configuration_and_nacos(monkeypatch):
    from app.api import system

    monkeypatch.setattr(system.settings, "environment", "production")
    monkeypatch.setattr(system.settings, "auth_mode", "company")
    monkeypatch.setattr(system.settings, "auth_service_url", "http://auth")
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(nacos_ready=False))
    )

    unavailable = await system.readiness_check(request)
    request.app.state.nacos_ready = True
    available = await system.readiness_check(request)

    assert unavailable.status_code == 503
    assert json.loads(unavailable.body)["components"]["nacos"] == "not_ready"
    assert available.status_code == 200
    assert json.loads(available.body)["status"] == "ready"
