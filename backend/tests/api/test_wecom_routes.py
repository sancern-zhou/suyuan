"""企业微信回调：加密验签 URL 验证、加好友绑定流转、管理 API 鉴权。"""

from __future__ import annotations

import base64
import os
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.wecom_routes import router
from app.auth.dependencies import optional_current_user
from app.social.wecom.crypto import WecomCrypto
from config.settings import settings

BINDINGS_DIR_PATCH = "app.social.wecom.bindings.get_social_dir"
_AES_KEY = base64.b64encode(os.urandom(32)).decode("utf-8").rstrip("=")


def _configure(monkeypatch, *, token="wecom-token-1", aes_key=_AES_KEY):
    monkeypatch.setattr(settings, "wecom_token", token)
    monkeypatch.setattr(settings, "wecom_aes_key", aes_key)
    monkeypatch.setattr(settings, "wecom_corpid", "ww-corp-1")
    monkeypatch.setattr(settings, "wecom_api_prefix", "/api/wecom")


@pytest.fixture
def callback_client(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    _configure(monkeypatch)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), tmp_path


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    monkeypatch.setattr(settings, "wecom_token", "")
    monkeypatch.setattr(settings, "wecom_aes_key", "")
    monkeypatch.setattr(
        settings,
        "app_accounts_json",
        '{"大气科1": {"secret": "s", "name": "大气科1", "status": "active"}}',
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(
        is_admin=True
    )
    return TestClient(app), tmp_path


def _crypto() -> WecomCrypto:
    return WecomCrypto("wecom-token-1", _AES_KEY, receive_id="ww-corp-1")


def _signed_params(crypto: WecomCrypto, encrypt: str, timestamp="1700000000", nonce="n1"):
    return {
        "msg_signature": crypto.signature(timestamp, nonce, encrypt),
        "timestamp": timestamp,
        "nonce": nonce,
    }


def _event_xml(
    change_type: str,
    *,
    external_userid: str = "wm-A",
    member: str = "ops-member",
    state: str = "",
) -> str:
    state_xml = f"<State><![CDATA[{state}]]></State>" if state else ""
    return f"""<xml>
<ToUserName><![CDATA[ww-corp-1]]></ToUserName>
<FromUserName><![CDATA[sys]]></FromUserName>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[change_external_contact]]></Event>
<ChangeType><![CDATA[{change_type}]]></ChangeType>
<UserID><![CDATA[{member}]]></UserID>
<ExternalUserID><![CDATA[{external_userid}]]></ExternalUserID>
{state_xml}
</xml>"""


def _encrypted_body(crypto: WecomCrypto, plain_xml: str) -> bytes:
    encrypt = crypto.encrypt(plain_xml)
    envelope = f"<xml><Encrypt><![CDATA[{encrypt}]]></Encrypt></xml>"
    return envelope.encode("utf-8")


# ---------------------------------------------------------------------------
# URL verification
# ---------------------------------------------------------------------------


def test_callback_url_verification_roundtrip(callback_client):
    client, _ = callback_client
    crypto = _crypto()
    echo = crypto.encrypt("echo-42")

    response = client.get(
        "/api/wecom/callback",
        params={"echostr": echo, **_signed_params(crypto, echo)},
    )
    assert response.status_code == 200
    assert response.text == "echo-42"


def test_callback_rejects_bad_signature(callback_client):
    client, _ = callback_client
    crypto = _crypto()
    echo = crypto.encrypt("echo-42")

    response = client.get(
        "/api/wecom/callback",
        params={
            "echostr": echo,
            "msg_signature": "deadbeef",
            "timestamp": "1700000000",
            "nonce": "n1",
        },
    )
    assert response.status_code == 403


def test_callback_disabled_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    monkeypatch.setattr(settings, "wecom_token", "")
    monkeypatch.setattr(settings, "wecom_aes_key", "")
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get(
        "/api/wecom/callback",
        params={
            "msg_signature": "x",
            "timestamp": "1",
            "nonce": "n",
            "echostr": "e",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "wecom_callback_disabled"


# ---------------------------------------------------------------------------
# Binding flow
# ---------------------------------------------------------------------------


def test_add_external_contact_with_state_binds(callback_client):
    client, tmp_path = callback_client
    crypto = _crypto()
    body = _encrypted_body(
        crypto, _event_xml("add_external_contact", state="bind:大气科1")
    )

    response = client.post(
        "/api/wecom/callback", params=_signed_params(crypto, _extract(body)), content=body
    )
    assert response.status_code == 200
    assert response.text == "success"

    import json

    data = json.loads((tmp_path / "wecom_bindings.json").read_text("utf-8"))
    assert data["大气科1"]["external_userid"] == "wm-A"
    assert data["大气科1"]["owner"] == "ops-member"
    assert data["大气科1"]["status"] == "bound"


def _extract(body: bytes) -> str:
    root = ET.fromstring(body)
    return root.find("Encrypt").text.strip()


def test_add_external_contact_without_state_is_ignored(callback_client):
    client, tmp_path = callback_client
    crypto = _crypto()
    body = _encrypted_body(crypto, _event_xml("add_external_contact"))

    response = client.post(
        "/api/wecom/callback", params=_signed_params(crypto, _extract(body)), content=body
    )
    assert response.status_code == 200
    assert not (tmp_path / "wecom_bindings.json").exists()


def test_del_external_contact_marks_unbound(callback_client):
    client, tmp_path = callback_client
    crypto = _crypto()
    add = _encrypted_body(crypto, _event_xml("add_external_contact", state="bind:大气科1"))
    client.post(
        "/api/wecom/callback", params=_signed_params(crypto, _extract(add)), content=add
    )

    dele = _encrypted_body(crypto, _event_xml("del_external_contact"))
    response = client.post(
        "/api/wecom/callback", params=_signed_params(crypto, _extract(dele)), content=dele
    )
    assert response.status_code == 200

    import json

    data = json.loads((tmp_path / "wecom_bindings.json").read_text("utf-8"))
    assert data["大气科1"]["status"] == "unbound"


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


def test_admin_endpoints_reject_non_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: None
    client = TestClient(app)

    assert client.get("/api/wecom/admin/status").status_code == 403


def test_bind_qrcode_validates_account_and_uses_client(admin_client, monkeypatch):
    client, _ = admin_client

    class FakeClient:
        enabled = True

        async def create_bind_qrcode(self, state, *, members=None, expire_days=30):
            return {
                "qr_code": "https://wework.qpic.cn/qr",
                "state": state,
                "members": members or ["ops"],
            }

    monkeypatch.setattr(
        "app.social.wecom.client.get_wecom_client", lambda: FakeClient()
    )

    missing = client.post("/api/wecom/admin/bind-qrcode", json={"account": "nope"})
    assert missing.status_code == 404

    ok = client.post(
        "/api/wecom/admin/bind-qrcode", json={"account": "app:android:大气科1"}
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["account"] == "大气科1"
    assert body["state"] == "bind:大气科1"
    assert body["qr_code"].startswith("https://")


def test_status_reports_channel_state(admin_client):
    client, _ = admin_client
    status = client.get("/api/wecom/admin/status").json()
    assert status["enabled"] is False  # corpid/secret/member 未配置
    assert status["callback_configured"] is False
    assert status["callback_path"] == "/api/wecom/callback"
    assert status["binding_count"] == 0
