import httpx
import pytest

from app.social.push_service import PushDeviceStore, UnifiedPushService
from config.settings import settings


@pytest.mark.asyncio
async def test_getui_push_registers_and_sends_without_vendor_branching(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "push_provider", "getui")
    monkeypatch.setattr(settings, "push_getui_app_id", "app-id")
    monkeypatch.setattr(settings, "push_getui_app_key", "app-key")
    monkeypatch.setattr(settings, "push_getui_master_secret", "master-secret")
    monkeypatch.setattr(settings, "push_getui_base_url", "https://push.test/v2")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/auth"):
            return httpx.Response(200, json={"code": 0, "data": {"token": "token", "expire_time": 4102444800000}})
        return httpx.Response(200, json={"code": 0, "data": {"task": {"cid": "successed_online"}}})

    transport = httpx.MockTransport(handler)
    factory = lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs)
    store = PushDeviceStore(tmp_path / "devices.json")
    await store.upsert("app:android:demo", provider="getui", device_id="cid-12345678")
    service = UnifiedPushService(device_store=store, client_factory=factory)

    result = await service.send_broadcast(social_user_id="app:android:demo", message="测试广播")

    assert result["sent"] == 1
    assert [request.url.path for request in requests] == ["/v2/app-id/auth", "/v2/app-id/push/single/cid"]
    assert requests[1].headers["token"] == "token"


@pytest.mark.asyncio
async def test_push_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "push_provider", "none")
    service = UnifiedPushService(device_store=PushDeviceStore(tmp_path / "devices.json"))
    assert await service.send_broadcast(social_user_id="app:android:demo", message="x") == {
        "enabled": False,
        "sent": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_cid_moves_when_a_shared_device_switches_account(tmp_path):
    store = PushDeviceStore(tmp_path / "devices.json")
    await store.upsert("app:android:alice", provider="getui", device_id="cid-shared-123")
    await store.upsert("app:android:bob", provider="getui", device_id="cid-shared-123")

    assert await store.list_active("app:android:alice", "getui") == []
    assert [item["device_id"] for item in await store.list_active("app:android:bob", "getui")] == [
        "cid-shared-123"
    ]
