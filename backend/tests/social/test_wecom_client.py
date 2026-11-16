"""企业微信客户端与回调加解密：token 缓存/强刷、群发任务参数、绑定搬家。"""

from __future__ import annotations

import base64
import json
import os

import httpx
import pytest

from app.social.wecom.bindings import WecomBindingStore, normalize_account
from app.social.wecom.client import WecomClient
from app.social.wecom.crypto import WecomCrypto, WecomCryptoError
from config.settings import settings


def _aes_key() -> str:
    # 43 位合法 EncodingAESKey（32 字节随机数的 Base64 去掉末尾 "="）。
    return base64.b64encode(os.urandom(32)).decode("utf-8").rstrip("=")


def _enable_wecom(monkeypatch, *, member="ops-member"):
    monkeypatch.setattr(settings, "wecom_enabled", True)
    monkeypatch.setattr(settings, "wecom_corpid", "ww-corp-1")
    monkeypatch.setattr(settings, "wecom_contact_secret", "contact-secret")
    monkeypatch.setattr(settings, "wecom_default_member", member)
    monkeypatch.setattr(settings, "wecom_timeout_seconds", 5.0)


def _factory(handler):
    transport = httpx.MockTransport(handler)
    return lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs)


# ---------------------------------------------------------------------------
# Callback crypto
# ---------------------------------------------------------------------------


def test_crypto_roundtrip_and_signature():
    crypto = WecomCrypto("token-1", _aes_key(), receive_id="ww-corp-1")
    message = "<xml><Event><![CDATA[change_external_contact]]></Event></xml>"
    encrypt = crypto.encrypt(message)

    sig = crypto.signature("1700000000", "n1", encrypt)
    assert crypto.verify(sig, "1700000000", "n1", encrypt) is True
    assert crypto.verify("deadbeef", "1700000000", "n1", encrypt) is False
    assert crypto.decrypt(encrypt) == message


def test_crypto_rejects_bad_key_or_ciphertext():
    with pytest.raises(WecomCryptoError):
        WecomCrypto("t", "a" * 42)
    crypto = WecomCrypto("t", _aes_key())
    with pytest.raises(WecomCryptoError):
        crypto.decrypt("not-base64-!!!")


def test_crypto_keys_are_isolated():
    message = "<xml>ok</xml>"
    a = WecomCrypto("t", _aes_key())
    b = WecomCrypto("t", _aes_key())
    # 不同 key 加密的密文互相解不开。
    with pytest.raises(WecomCryptoError):
        b.decrypt(a.encrypt(message))


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_when_config_missing(monkeypatch):
    monkeypatch.setattr(settings, "wecom_enabled", False)
    assert WecomClient().enabled is False


@pytest.mark.asyncio
async def test_token_cached_and_task_payload(monkeypatch):
    _enable_wecom(monkeypatch)
    token_calls = 0
    task_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/cgi-bin/gettoken":
            token_calls += 1
            return httpx.Response(
                200, json={"access_token": "tok", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/externalcontact/add_msg_template":
            task_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"errcode": 0, "msgid": "msg-1"})
        return httpx.Response(200, json={"errcode": 0})

    client = WecomClient(client_factory=_factory(handler))
    assert client.enabled is True

    first = await client.add_group_msg_task(
        sender="ops-member", external_userids=["wm-1", "wm-2"], content="周报"
    )
    second = await client.add_group_msg_task(
        sender="ops-member", external_userids=["wm-3"], content="月报"
    )

    assert (first["msgid"], second["msgid"]) == ("msg-1", "msg-1")
    # 一次 gettoken 服务多次调用（缓存生效）
    assert token_calls == 1
    body = task_payloads[0]
    assert body["chat_type"] == "single"
    assert body["sender"] == "ops-member"
    assert body["external_userid"] == ["wm-1", "wm-2"]
    assert body["text"]["content"] == "周报"


@pytest.mark.asyncio
async def test_stale_token_triggers_force_refresh(monkeypatch):
    _enable_wecom(monkeypatch)
    token_calls: list[dict] = []
    task_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal task_calls
        if request.url.path == "/cgi-bin/gettoken":
            token_calls.append(dict(request.url.params))
            return httpx.Response(
                200, json={"access_token": f"tok{len(token_calls)}", "expires_in": 7200}
            )
        task_calls += 1
        if task_calls == 1:
            return httpx.Response(200, json={"errcode": 42001, "errmsg": "expired"})
        return httpx.Response(200, json={"errcode": 0, "msgid": "msg-2"})

    client = WecomClient(client_factory=_factory(handler))
    result = await client.add_group_msg_task(
        sender="ops-member", external_userids=["wm-1"], content="x"
    )
    assert result["msgid"] == "msg-2"
    assert len(token_calls) == 2
    assert task_calls == 2


@pytest.mark.asyncio
async def test_qrcode_uses_default_member(monkeypatch):
    _enable_wecom(monkeypatch, member="boss-member")
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/gettoken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"errcode": 0, "qr_code": "https://wework.qpic.cn/qr"})

    client = WecomClient(client_factory=_factory(handler))
    result = await client.create_bind_qrcode("bind:大气科1")

    assert result["qr_code"] == "https://wework.qpic.cn/qr"
    assert payloads[0]["state"] == "bind:大气科1"
    assert payloads[0]["user"] == ["boss-member"]
    assert payloads[0]["type"] == 1


# ---------------------------------------------------------------------------
# Binding store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_userid_moves_when_rebound(tmp_path):
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="memberA")
    await store.bind("大气科2", "wm-1", owner="memberB")

    assert (await store.get("大气科1")) is None
    row = await store.get("大气科2")
    assert row["external_userid"] == "wm-1"
    assert row["owner"] == "memberB"
    assert row["status"] == "bound"


@pytest.mark.asyncio
async def test_mark_unbound_and_rebind_restores(tmp_path):
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="memberA")

    assert await store.mark_unbound("wm-1") == "大气科1"
    assert (await store.get("大气科1"))["status"] == "unbound"

    await store.bind("大气科1", "wm-1", owner="memberA")
    assert (await store.get("大气科1"))["status"] == "bound"


@pytest.mark.asyncio
async def test_record_push_updates_timestamp(tmp_path):
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1")
    await store.record_push("大气科1")
    assert (await store.get("大气科1"))["last_push_at"]


def test_normalize_account():
    assert normalize_account("app:android:大气科1") == "大气科1"
    assert normalize_account(" 大气科1 ") == "大气科1"
