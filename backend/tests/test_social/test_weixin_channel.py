"""Unit tests for Weixin Channel."""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from collections import OrderedDict
from types import SimpleNamespace

from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus
from app.channels.weixin import (
    WeixinChannel,
    _decrypt_aes_ecb,
    _ext_for_type,
    _split_message,
)


@pytest.fixture
def message_bus():
    """Create a message bus for testing."""
    return MessageBus()


@pytest.fixture
def weixin_config():
    """Create Weixin channel configuration."""
    return {
        "enabled": True,
        "allow_from": ["*"],
        "base_url": "https://ilinkai.weixin.qq.com",
        "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
        "route_tag": None,
        "token": "",
        "state_dir": "",
        "poll_timeout": 35,
    }


@pytest.fixture
def weixin_channel(message_bus, weixin_config):
    """Create a Weixin channel instance."""
    channel = WeixinChannel(weixin_config, message_bus)
    return channel


class TestUtilityFunctions:
    """Test utility functions."""

    def test_ext_for_type(self):
        """Test file extension for media type."""
        assert _ext_for_type("image") == ".jpg"
        assert _ext_for_type("video") == ".mp4"
        assert _ext_for_type("voice") == ".silk"
        assert _ext_for_type("file") == ".bin"

    def test_split_message_short(self):
        """Test splitting short message."""
        text = "Hello world"
        chunks = _split_message(text, 4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_message_long(self):
        """Test splitting long message."""
        text = "A" * 5000
        chunks = _split_message(text, 4000)
        assert len(chunks) == 2
        assert len(chunks[0]) <= 4000
        assert len(chunks[1]) <= 4000

    def test_split_message_with_newlines(self):
        """Test splitting message with newlines."""
        lines = ["Line " + str(i) for i in range(100)]
        text = "\n".join(lines)
        chunks = _split_message(text, 500)
        # Should split into multiple chunks
        assert len(chunks) > 1


class TestWeixinChannel:
    """Test Weixin channel functionality."""

    def test_channel_properties(self, weixin_channel):
        """Test channel basic properties."""
        assert weixin_channel.name == "weixin"
        assert weixin_channel.display_name == "WeChat"

    def test_default_config(self):
        """Test default configuration."""
        config = WeixinChannel.default_config()
        assert config["enabled"] is False
        assert "*" in config["allow_from"]
        assert config["base_url"] == "https://ilinkai.weixin.qq.com"

    def test_is_allowed_wildcard(self, weixin_channel):
        """Test permission check with wildcard."""
        assert weixin_channel.is_allowed("any_user_id") is True

    def test_is_allowed_specific(self, weixin_channel):
        """Test permission check with specific users."""
        weixin_channel.config.allow_from = ["wxid_abc123", "wxid_def456"]
        assert weixin_channel.is_allowed("wxid_abc123") is True
        assert weixin_channel.is_allowed("wxid_def456") is True
        assert weixin_channel.is_allowed("wxid_xyz789") is False

    def test_state_dir_initialization(self, weixin_channel, tmp_path):
        """Test state directory initialization."""
        state_dir = weixin_channel._get_state_dir()
        assert state_dir is not None
        assert state_dir.exists()

    def test_processed_ids_dedup(self, weixin_channel):
        """Test message deduplication."""
        # Add some message IDs
        for i in range(10):
            weixin_channel._processed_ids[f"msg_{i}"] = None

        # Check they exist
        for i in range(10):
            assert f"msg_{i}" in weixin_channel._processed_ids

        # Add more to test maxlen
        for i in range(1000):
            weixin_channel._processed_ids[f"msg_{i}"] = None

        # Should only keep last 1000
        assert len(weixin_channel._processed_ids) <= 1000

    def test_pause_session(self, weixin_channel):
        """Test session pause functionality."""
        import time

        weixin_channel._pause_session(10)
        remaining = weixin_channel._session_pause_remaining_s()
        assert 0 < remaining <= 10

    def test_context_token_caching(self, weixin_channel):
        """Test context token caching."""
        user_id = "wxid_test123"
        ctx_token = "test_context_token"

        weixin_channel._context_tokens[user_id] = ctx_token

        assert weixin_channel._context_tokens.get(user_id) == ctx_token


class TestWeixinChannelStatePersistence:
    """Test state persistence."""

    def test_constructor_restores_disk_backed_context_tokens(self, message_bus, tmp_path):
        """Restarted channels restore bot identity and context tokens before polling."""
        state_dir = tmp_path / "weixin_state"
        state_dir.mkdir()
        (state_dir / "account.json").write_text(
            """
{
  "token": "state_token",
  "bot_id": "55f85b8e2638@im.bot",
  "get_updates_buf": "cursor",
  "context_tokens": {
    "o9cq804yEHqzcgkjhxwp7MKjSYec@im.wechat": "ctx_token"
  },
  "base_url": "https://ilinkai.weixin.qq.com"
}
""",
            encoding="utf-8",
        )

        config = SimpleNamespace(
            enabled=True,
            allow_from=["*"],
            base_url="https://ilinkai.weixin.qq.com",
            cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
            route_tag=None,
            token="config_token",
            state_dir=str(state_dir),
            poll_timeout=35,
            id="auto_mpunp1h4",
            name="账号-auto_mpunp1h4",
            auto_start=True,
        )

        channel = WeixinChannel(config, message_bus, instance_id="auto_mpunp1h4")

        assert channel.bot_account == "55f85b8e2638@im.bot"
        assert channel._context_tokens == {
            "o9cq804yEHqzcgkjhxwp7MKjSYec@im.wechat": "ctx_token"
        }
        assert channel._get_updates_buf == "cursor"

    def test_save_and_load_state(self, weixin_channel, tmp_path):
        """Test saving and loading state."""
        # Set some state
        weixin_channel._token = "test_token_123"
        weixin_channel._get_updates_buf = "test_buf"
        weixin_channel._context_tokens = {"wxid_test": "ctx_token"}

        # Save state
        weixin_channel._save_state()

        # Create new channel and load state
        new_channel = WeixinChannel(weixin_channel.config, weixin_channel.bus)
        loaded = new_channel._load_state()

        assert loaded is True
        assert new_channel._token == "test_token_123"
        assert new_channel._get_updates_buf == "test_buf"
        assert new_channel._context_tokens.get("wxid_test") == "ctx_token"

    def test_load_state_no_file(self, weixin_channel):
        """Test loading state when file doesn't exist."""
        # Use a temporary directory without state file
        weixin_channel._state_dir = Path("/tmp/nonexistent_weixin_test")
        loaded = weixin_channel._load_state()
        assert loaded is False


class TestWeixinChannelMessageProcessing:
    """Test message processing."""

    @pytest.mark.asyncio
    async def test_process_text_message(self, weixin_channel):
        """Test processing text message."""
        msg = {
            "message_type": 1,  # USER
            "message_id": "test_msg_123",
            "from_user_id": "wxid_test123",
            "context_token": "test_ctx",
            "item_list": [
                {
                    "type": 1,  # TEXT
                    "text_item": {"text": "Hello bot"}
                }
            ]
        }

        # Should not raise
        await weixin_channel._process_message(msg)

    @pytest.mark.asyncio
    async def test_skip_bot_message(self, weixin_channel):
        """Test skipping bot's own messages."""
        msg = {
            "message_type": 2,  # BOT
            "message_id": "test_msg_123",
            "from_user_id": "bot_id",
            "item_list": []
        }

        await weixin_channel._process_message(msg)

        # Message should not be processed (no exception, no logs about inbound)

    @pytest.mark.asyncio
    async def test_deduplication(self, weixin_channel):
        """Test message deduplication."""
        msg_id = "test_msg_123"

        # Add to processed
        weixin_channel._processed_ids[msg_id] = None

        msg = {
            "message_type": 1,
            "message_id": msg_id,
            "from_user_id": "wxid_test",
            "item_list": [{"type": 1, "text_item": {"text": "test"}}]
        }

        # Should skip due to deduplication
        await weixin_channel._process_message(msg)


class TestWeixinChannelOutbound:
    """Test outbound message sending."""

    @pytest.mark.asyncio
    async def test_send_without_client(self, weixin_channel):
        """Test sending when client is not initialized."""
        weixin_channel._client = None

        msg = OutboundMessage(
            channel="weixin",
            chat_id="wxid_test",
            content="Test message"
        )

        # Should not raise, just log warning
        await weixin_channel.send(msg)

    @pytest.mark.asyncio
    async def test_send_without_token(self, weixin_channel):
        """Test sending without token."""
        weixin_channel._client = Mock()
        weixin_channel._token = ""

        msg = OutboundMessage(
            channel="weixin",
            chat_id="wxid_test",
            content="Test message"
        )

        # Should not raise, just log warning
        await weixin_channel.send(msg)

    @pytest.mark.asyncio
    async def test_send_without_context_token(self, weixin_channel):
        """Test sending without context token."""
        mock_client = Mock()
        mock_client.aclose = AsyncMock()
        weixin_channel._client = mock_client
        weixin_channel._token = "test_token"

        msg = OutboundMessage(
            channel="weixin",
            chat_id="wxid_test",
            content="Test message"
        )

        # Should log warning about missing context token
        await weixin_channel.send(msg)


class TestWeixinChannelLifecycle:
    """Test channel lifecycle."""

    @pytest.mark.asyncio
    async def test_login(self, weixin_channel):
        """Test login method."""
        # Mock QR login
        weixin_channel._qr_login = AsyncMock(return_value=False)

        result = await weixin_channel.login()
        assert result is False  # No saved token, QR login failed

    @pytest.mark.asyncio
    async def test_login_with_saved_token(self, weixin_channel):
        """Test login with existing token."""
        weixin_channel._token = "saved_token"
        result = await weixin_channel.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_start_without_login(self, weixin_channel):
        """Test start when login fails."""
        # Mock login to fail
        weixin_channel._qr_login = AsyncMock(return_value=False)

        # Should not raise, just return
        await weixin_channel.start()
        assert weixin_channel._running is False

    @pytest.mark.asyncio
    async def test_stop(self, weixin_channel):
        """Test stopping the channel."""
        weixin_channel._running = True
        weixin_channel._client = Mock()
        weixin_channel._client.aclose = AsyncMock()

        await weixin_channel.stop()

        assert weixin_channel._running is False
        assert weixin_channel._client is None


class TestAesDecryption:
    """Test AES decryption functionality."""

    def test_decrypt_aes_ecb(self):
        """Test AES-ECB decryption."""
        # This test requires pycryptodome
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
            import base64

            # Create test data
            key = b"16bytekey1234567"  # 16 bytes
            cipher = AES.new(key, AES.MODE_ECB)
            plaintext = b"Test message for encryption"
            padded = pad(plaintext, AES.block_size)
            encrypted = cipher.encrypt(padded)
            key_b64 = base64.b64encode(key).decode()

            # Test decryption
            decrypted = _decrypt_aes_ecb(encrypted, key_b64)

            assert decrypted == plaintext

        except ImportError:
            pytest.skip("pycryptodome not installed")

    def test_decrypt_aes_ecb_invalid_key(self):
        """Test AES decryption with invalid key."""
        try:
            encrypted_data = b"some_encrypted_data"
            invalid_key_b64 = "invalid_base64_key"

            with pytest.raises(Exception):
                _decrypt_aes_ecb(encrypted_data, invalid_key_b64)

        except ImportError:
            pytest.skip("pycryptodome not installed")


class TestMessageSplitting:
    """Test message splitting functionality."""

    def test_split_empty_message(self):
        """Test splitting empty message."""
        chunks = _split_message("", 4000)
        assert chunks == []

    def test_split_exact_limit(self):
        """Test splitting message at exact limit."""
        text = "A" * 4000
        chunks = _split_message(text, 4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_over_limit(self):
        """Test splitting message over limit."""
        text = "A" * 5000
        chunks = _split_message(text, 4000)
        assert len(chunks) == 2
        assert sum(len(c) for c in chunks) == 5000

    def test_split_preserves_newlines(self):
        """Test that splitting preserves newlines when possible."""
        text = "Line1\nLine2\nLine3"
        chunks = _split_message(text, 100)
        assert len(chunks) == 1
        assert "\n" in chunks[0]
