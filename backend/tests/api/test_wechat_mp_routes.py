"""微信公众号回调：签名校验、扫码绑定、取关/授权状态回写、管理 API。"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.wechat_mp_routes import router
from app.auth.dependencies import optional_current_user
from config.settings import settings

BINDINGS_DIR_PATCH = "app.social.wechat_mp.bindings.get_social_dir"


def _sign(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1(
        "".join(sorted([token, timestamp, nonce])).encode("utf-8")
    ).hexdigest()


@pytest.fixture
def callback_client(tmp_path, monkeypatch):
    """已配置回调 token、绑定文件指向 tmp 的客户端。"""
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    monkeypatch.setattr(settings, "wechat_mp_token", "mp-token-1")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), tmp_path


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    monkeypatch.setattr(settings, "wechat_mp_token", "")
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


def _event_xml(
    event: str,
    openid: str = "openid-A",
    event_key: str = "",
    extra: str = "",
) -> str:
    key = f"<EventKey><![CDATA[{event_key}]]></EventKey>" if event_key else ""
    return f"""<xml>
<ToUserName><![CDATA[gh_x]]></ToUserName>
<FromUserName><![CDATA[{openid}]]></FromUserName>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[{event}]]></Event>
{key}
{extra}
</xml>"""


def _post_event(client: TestClient, xml: str):
    return client.post(
        "/api/wechat-mp/callback",
        params={
            "signature": _sign("mp-token-1", "1700000000", "n1"),
            "timestamp": "1700000000",
            "nonce": "n1",
        },
        content=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
    )


# ---------------------------------------------------------------------------
# URL verification + signature enforcement
# ---------------------------------------------------------------------------


def test_callback_url_verification_echoes(callback_client):
    client, _ = callback_client
    response = client.get(
        "/api/wechat-mp/callback",
        params={
            "signature": _sign("mp-token-1", "1700000000", "n1"),
            "timestamp": "1700000000",
            "nonce": "n1",
            "echostr": "echo-42",
        },
    )
    assert response.status_code == 200
    assert response.text == "echo-42"


def test_callback_rejects_bad_signature(callback_client):
    client, _ = callback_client
    response = client.get(
        "/api/wechat-mp/callback",
        params={
            "signature": "deadbeef",
            "timestamp": "1700000000",
            "nonce": "n1",
            "echostr": "echo-42",
        },
    )
    assert response.status_code == 403

    forged = _post_event_with_signature(client, "deadbeef", _event_xml("subscribe", event_key="qrscene_bind:大气科1"))
    assert forged.status_code == 403


def _post_event_with_signature(client: TestClient, signature: str, xml: str):
    return client.post(
        "/api/wechat-mp/callback",
        params={
            "signature": signature,
            "timestamp": "1700000000",
            "nonce": "n1",
        },
        content=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
    )


# ---------------------------------------------------------------------------
# Binding flow
# ---------------------------------------------------------------------------


def test_subscribe_with_bind_scene_binds_account(callback_client, monkeypatch):
    client, tmp_path = callback_client
    sent: list[tuple[str, str]] = []

    class FakeClient:
        enabled = True

        async def send_text_message(self, openid: str, content: str):
            sent.append((openid, content))
            return {"errcode": 0}

    monkeypatch.setattr(
        "app.social.wechat_mp.client.get_wechat_mp_client", lambda: FakeClient()
    )

    response = _post_event(
        client, _event_xml("subscribe", event_key="qrscene_bind:大气科1")
    )
    assert response.status_code == 200
    assert response.text == "success"

    import json

    data = json.loads((tmp_path / "wechat_mp_bindings.json").read_text("utf-8"))
    assert data["大气科1"]["openid"] == "openid-A"
    assert data["大气科1"]["status"] == "bound"
    # 欢迎语 best-effort 发出
    assert sent and sent[0][0] == "openid-A"


def test_scan_event_rebinds_existing_follower(callback_client):
    client, tmp_path = callback_client
    response = _post_event(client, _event_xml("SCAN", event_key="bind:大气科2"))
    assert response.status_code == 200

    import json

    data = json.loads((tmp_path / "wechat_mp_bindings.json").read_text("utf-8"))
    assert data["大气科2"]["openid"] == "openid-A"


def test_follow_without_scene_is_ignored(callback_client):
    client, tmp_path = callback_client
    response = _post_event(client, _event_xml("subscribe"))
    assert response.status_code == 200
    assert not (tmp_path / "wechat_mp_bindings.json").exists()


def test_unsubscribe_marks_binding(callback_client):
    client, _ = callback_client
    _post_event(client, _event_xml("subscribe", event_key="qrscene_bind:大气科1"))
    response = _post_event(client, _event_xml("unsubscribe"))
    assert response.status_code == 200

    import json

    from app.social.wechat_mp.bindings import WechatMpBindingStore

    data = json.loads(WechatMpBindingStore().path.read_text("utf-8"))
    assert data["大气科1"]["status"] == "unsubscribed"


def test_popup_records_template_states(callback_client):
    client, _ = callback_client
    _post_event(client, _event_xml("subscribe", event_key="qrscene_bind:大气科1"))
    xml = _event_xml(
        "subscribe_msg_popup",
        extra="""<SubscribeMsgPopupEvent>
<List>
<TemplateId><![CDATA[tpl-9]]></TemplateId>
<SubscribeStatusString><![CDATA[accept]]></SubscribeStatusString>
</List>
</SubscribeMsgPopupEvent>""",
    )
    response = _post_event(client, xml)
    assert response.status_code == 200

    import json

    from app.social.wechat_mp.bindings import WechatMpBindingStore

    data = json.loads(WechatMpBindingStore().path.read_text("utf-8"))
    assert data["大气科1"]["templates"] == {"tpl-9": "accept"}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


def test_admin_endpoints_reject_non_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(BINDINGS_DIR_PATCH, lambda: tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[optional_current_user] = lambda: None
    client = TestClient(app)

    assert client.get("/api/wechat-mp/admin/status").status_code == 403


def test_bind_qrcode_validates_account(admin_client, monkeypatch):
    client, _ = admin_client

    class FakeClient:
        enabled = True

        async def create_bind_qrcode(self, scene, *, expire_seconds=2592000):
            return {"ticket": "t", "expire_seconds": expire_seconds, "url": "https://x/t"}

    monkeypatch.setattr(
        "app.social.wechat_mp.client.get_wechat_mp_client", lambda: FakeClient()
    )

    missing = client.post("/api/wechat-mp/admin/bind-qrcode", json={"account": "nope"})
    assert missing.status_code == 404

    ok = client.post(
        "/api/wechat-mp/admin/bind-qrcode", json={"account": "app:android:大气科1"}
    )
    assert ok.status_code == 200
    assert ok.json()["account"] == "大气科1"
    assert ok.json()["url"].startswith("https://")


def test_status_reports_binding_counts(admin_client):
    client, tmp_path = admin_client
    list_response = client.get("/api/wechat-mp/admin/bindings")
    assert list_response.status_code == 200
    assert list_response.json() == {"bindings": [], "count": 0}

    status = client.get("/api/wechat-mp/admin/status").json()
    assert status["enabled"] is False  # app id/secret 未配置
    assert status["callback_configured"] is False
    assert status["callback_path"] == "/api/wechat-mp/callback"
