"""微信公众号客户端：stable_token 缓存/失效刷新、bizsend 聚合、二维码。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.social.wechat_mp.bindings import (
    WechatMpBindingStore,
    normalize_account,
)
from app.social.wechat_mp.client import WechatMpClient
from config.settings import settings


def _enable_mp(monkeypatch):
    monkeypatch.setattr(settings, "wechat_mp_enabled", True)
    monkeypatch.setattr(settings, "wechat_mp_app_id", "wx-app")
    monkeypatch.setattr(settings, "wechat_mp_app_secret", "secret")
    monkeypatch.setattr(settings, "wechat_mp_timeout_seconds", 5.0)


def _factory(handler):
    transport = httpx.MockTransport(handler)
    return lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs)


@pytest.mark.asyncio
async def test_disabled_when_config_missing(monkeypatch):
    monkeypatch.setattr(settings, "wechat_mp_enabled", False)
    client = WechatMpClient()
    assert client.enabled is False


@pytest.mark.asyncio
async def test_token_cached_across_batch(monkeypatch):
    _enable_mp(monkeypatch)
    token_calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            token_calls.append(dict(json.loads(request.content)))
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = WechatMpClient(client_factory=_factory(handler))
    assert client.enabled is True

    results = await client.send_subscribe_batch(
        template_id="tpl-1",
        recipients=[("o-A", {"thing1": "月度特征分析"}), ("o-B", {"thing1": "周报"})],
    )

    assert [row["errcode"] for row in results] == [0, 0]
    # One stable_token call serves the whole batch; force_refresh kept off.
    assert len(token_calls) == 1
    assert token_calls[0]["force_refresh"] is False
    assert token_calls[0]["grant_type"] == "client_credential"


@pytest.mark.asyncio
async def test_stale_token_triggers_force_refresh_retry(monkeypatch):
    _enable_mp(monkeypatch)
    token_calls: list[dict] = []
    bizsend_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal bizsend_calls
        if request.url.path == "/cgi-bin/stable_token":
            body = dict(json.loads(request.content))
            token_calls.append(body)
            return httpx.Response(
                200, json={"access_token": f"tok{len(token_calls)}", "expires_in": 7200}
            )
        bizsend_calls += 1
        if bizsend_calls == 1:
            return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = WechatMpClient(client_factory=_factory(handler))
    results = await client.send_subscribe_batch(
        template_id="tpl-1", recipients=[("o-A", {"thing1": "x"})]
    )

    assert results[0]["errcode"] == 0
    assert [body["force_refresh"] for body in token_calls] == [False, True]
    assert bizsend_calls == 2


@pytest.mark.asyncio
async def test_bizsend_rejections_are_returned_not_raised(monkeypatch):
    _enable_mp(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(200, json={"errcode": 43101, "errmsg": "user refuse"})

    client = WechatMpClient(client_factory=_factory(handler))
    results = await client.send_subscribe_batch(
        template_id="tpl-1", recipients=[("o-A", {"thing1": "x"})]
    )
    assert results[0]["errcode"] == 43101


@pytest.mark.asyncio
async def test_create_bind_qrcode_builds_showqrcode_url(monkeypatch):
    _enable_mp(monkeypatch)
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"ticket": "tick==et", "expire_seconds": 2592000}
        )

    client = WechatMpClient(client_factory=_factory(handler))
    result = await client.create_bind_qrcode("bind:大气科1")

    assert seen[0]["action_name"] == "QR_STR_SCENE"
    assert seen[0]["action_info"]["scene"]["scene_str"] == "bind:大气科1"
    assert result["url"].endswith("ticket=tick%3D%3Det")
    assert result["expire_seconds"] == 2592000


# ---------------------------------------------------------------------------
# Binding store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openid_moves_when_rebound_to_another_account(tmp_path):
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "openid-1")
    await store.bind("大气科2", "openid-1")

    assert (await store.get("大气科1")) is None
    row = await store.get("大气科2")
    assert row["openid"] == "openid-1"
    assert row["status"] == "bound"

    bindings = await store.list_bindings()
    assert [item["account"] for item in bindings] == ["大气科2"]


@pytest.mark.asyncio
async def test_unsubscribe_then_rebind_restores_status(tmp_path):
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "openid-1")

    assert await store.mark_unsubscribed("openid-1") == "大气科1"
    assert (await store.get("大气科1"))["status"] == "unsubscribed"

    await store.bind("大气科1", "openid-1")
    assert (await store.get("大气科1"))["status"] == "bound"


@pytest.mark.asyncio
async def test_record_template_state_filters_invalid_states(tmp_path):
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "openid-1")

    await store.record_template_state("openid-1", "tpl-1", "accept")
    await store.record_template_state("openid-1", "tpl-2", "bogus")

    row = await store.get("大气科1")
    assert row["templates"] == {"tpl-1": "accept"}


def test_normalize_account_strips_social_prefix():
    assert normalize_account("app:android:大气科1") == "大气科1"
    assert normalize_account("  大气科1 ") == "大气科1"
