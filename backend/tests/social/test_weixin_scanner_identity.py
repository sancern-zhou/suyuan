import json
from types import SimpleNamespace

import pytest

from app.channels.weixin import WeixinChannel
from app.social.message_bus import MessageBus


def _channel(tmp_path):
    config = SimpleNamespace(
        id="account-1",
        name="WeChat",
        state_dir=str(tmp_path),
        base_url="https://ilinkai.weixin.qq.com",
    )
    return WeixinChannel(config, MessageBus(), instance_id="account-1")


@pytest.mark.asyncio
async def test_confirmed_qr_scan_persists_ilink_user_id(tmp_path, monkeypatch):
    channel = _channel(tmp_path)

    async def fake_get(*args, **kwargs):
        return {
            "status": "confirmed",
            "bot_token": "secret-token",
            "ilink_bot_id": "bot-1",
            "ilink_user_id": "wx-user-1",
            "baseurl": "https://example.invalid",
        }

    monkeypatch.setattr(channel, "_api_get", fake_get)
    channel._running = True

    assert await channel._wait_for_qr_scan("qr-1") is True
    assert channel.scanner_user_id == "wx-user-1"

    state = json.loads((channel._get_state_dir() / "account.json").read_text())
    assert state["scanner_user_id"] == "wx-user-1"


def test_scanner_identity_survives_channel_restart(tmp_path):
    state_file = tmp_path / "account.json"
    state_file.write_text(json.dumps({
        "token": "secret-token",
        "bot_id": "bot-1",
        "scanner_user_id": "wx-user-1",
    }))

    restarted = _channel(tmp_path)

    assert restarted.scanner_user_id == "wx-user-1"
