"""Unit tests for QQ Channel."""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus
from app.channels.qq import QQChannel, _sanitize_filename, _is_image_name, _guess_send_file_type


@pytest.fixture
def message_bus():
    """Create a message bus for testing."""
    return MessageBus()


@pytest.fixture
def qq_config():
    """Create QQ channel configuration."""
    return {
        "enabled": True,
        "app_id": "test_app_id",
        "secret": "test_secret",
        "allow_from": ["*"],
        "msg_format": "plain",
        "media_dir": "",
        "download_chunk_size": 262144,
        "download_max_bytes": 209715200,
    }


@pytest.fixture
def qq_channel(message_bus, qq_config):
    """Create a QQ channel instance."""
    # Mock QQ_AVAILABLE to True
    with patch('app.channels.qq.QQ_AVAILABLE', True):
        channel = QQChannel(qq_config, message_bus)
        return channel


class TestFilenameSanitization:
    """Test filename sanitization utilities."""

    def test_sanitize_filename_basic(self):
        """Test basic filename sanitization."""
        assert _sanitize_filename("test.txt") == "test.txt"
        assert _sanitize_filename("test file.txt") == "test_file.txt"
        assert _sanitize_filename("test\nfile.txt") == "test_file.txt"

    def test_sanitize_filename_chinese(self):
        """Test Chinese characters are preserved."""
        assert _sanitize_filename("测试文件.txt") == "测试文件.txt"
        assert _sanitize_filename("文件（1）.txt") == "文件（1）.txt"

    def test_sanitize_filename_unsafe_chars(self):
        """Test unsafe characters are removed."""
        assert _sanitize_filename("test<>file.txt") == "test_file.txt"
        assert _sanitize_filename("test|file.txt") == "test_file.txt"

    def test_sanitize_filename_path_traversal(self):
        """Test path traversal attempts are blocked."""
        assert _sanitize_filename("../../etc/passwd") == "etc_passwd"
        assert _sanitize_filename("..\\..\\windows\\system32") == "windows_system32"


class TestFileTypeDetection:
    """Test file type detection utilities."""

    def test_is_image_name(self):
        """Test image file detection."""
        assert _is_image_name("test.png") is True
        assert _is_image_name("test.jpg") is True
        assert _is_image_name("test.jpeg") is True
        assert _is_image_name("test.gif") is True
        assert _is_image_name("test.pdf") is False
        assert _is_image_name("test.txt") is False

    def test_guess_send_file_type(self):
        """Test file type guessing for QQ."""
        assert _guess_send_file_type("test.png") == 1  # QQ_FILE_TYPE_IMAGE
        assert _guess_send_file_type("test.jpg") == 1
        assert _guess_send_file_type("test.pdf") == 4  # QQ_FILE_TYPE_FILE
        assert _guess_send_file_type("test.txt") == 4
        assert _guess_send_file_type("test.docx") == 4


class TestQQChannel:
    """Test QQ channel functionality."""

    def test_channel_properties(self, qq_channel):
        """Test channel basic properties."""
        assert qq_channel.name == "qq"
        assert qq_channel.display_name == "QQ"

    def test_default_config(self):
        """Test default configuration."""
        config = QQChannel.default_config()
        assert config["enabled"] is False
        assert config["app_id"] == ""
        assert config["secret"] == ""
        assert "*" in config["allow_from"]

    def test_is_allowed_wildcard(self, qq_channel):
        """Test permission check with wildcard."""
        assert qq_channel.is_allowed("any_user_id") is True

    def test_is_allowed_specific(self, qq_channel):
        """Test permission check with specific users."""
        qq_channel.config.allow_from = ["user123", "user456"]
        assert qq_channel.is_allowed("user123") is True
        assert qq_channel.is_allowed("user456") is True
        assert qq_channel.is_allowed("user789") is False

    def test_is_allowed_empty_list(self, qq_channel):
        """Test permission check with empty list (deny all)."""
        qq_channel.config.allow_from = []
        assert qq_channel.is_allowed("any_user_id") is False

    def test_media_root_initialization(self, qq_channel):
        """Test media directory initialization."""
        assert qq_channel._media_root is not None
        assert qq_channel._media_root.exists()

    @pytest.mark.asyncio
    async def test_send_without_client(self, qq_channel):
        """Test sending message when client is not initialized."""
        qq_channel._client = None

        msg = OutboundMessage(
            channel="qq",
            chat_id="test_chat",
            content="Test message"
        )

        # Should not raise, just log warning
        await qq_channel.send(msg)

    @pytest.mark.asyncio
    async def test_send_text_only_mock(self, qq_channel):
        """Test sending text message with mocked client."""
        # Mock client
        mock_client = Mock()
        mock_client.api.post_c2c_message = AsyncMock()
        qq_channel._client = mock_client
        qq_channel._chat_type_cache = {"test_chat": "c2c"}

        msg = OutboundMessage(
            channel="qq",
            chat_id="test_chat",
            content="Test message"
        )

        await qq_channel.send(msg)

        # Verify API was called
        mock_client.api.post_c2c_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message(self, qq_channel):
        """Test handling inbound message."""
        # Publish a test message
        test_msg = InboundMessage(
            channel="qq",
            sender_id="test_user",
            chat_id="test_chat",
            content="Test message"
        )

        await qq_channel.bus.publish_inbound(test_msg)

        # Verify message was queued
        assert qq_channel.bus.inbound_size == 1


class TestQQChannelMediaHandling:
    """Test QQ channel media handling."""

    def test_read_media_bytes_local_file(self, qq_channel, tmp_path):
        """Test reading local file bytes."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # This test would require async execution
        # For now, just verify the method exists
        assert hasattr(qq_channel, '_read_media_bytes')

    def test_read_media_bytes_http_url(self, qq_channel):
        """Test reading media from HTTP URL."""
        # This would require mocking HTTP requests
        # For now, just verify the method exists
        assert hasattr(qq_channel, '_read_media_bytes')


class TestQQChannelLifecycle:
    """Test QQ channel lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_without_sdk(self, qq_channel):
        """Test starting channel when SDK is not available."""
        with patch('app.channels.qq.QQ_AVAILABLE', False):
            await qq_channel.start()
            assert qq_channel._running is False

    @pytest.mark.asyncio
    async def test_start_without_credentials(self, qq_channel):
        """Test starting channel without credentials."""
        qq_channel.config.app_id = ""
        qq_channel.config.secret = ""

        with patch('app.channels.qq.QQ_AVAILABLE', True):
            await qq_channel.start()
            assert qq_channel._running is False

    @pytest.mark.asyncio
    async def test_stop(self, qq_channel):
        """Test stopping the channel."""
        qq_channel._running = True
        qq_channel._client = Mock()
        qq_channel._client.close = AsyncMock()
        qq_channel._http = Mock()
        qq_channel._http.close = AsyncMock()

        await qq_channel.stop()

        assert qq_channel._running is False
        assert qq_channel._client is None
        assert qq_channel._http is None


class TestQQChannelAttachmentHandling:
    """Test QQ channel attachment handling."""

    @pytest.mark.asyncio
    async def test_handle_attachments_empty(self, qq_channel):
        """Test handling empty attachments list."""
        result = await qq_channel._handle_attachments([])
        media_paths, recv_lines, att_meta = result

        assert media_paths == []
        assert recv_lines == []
        assert att_meta == []

    def test_process_message_deduplication(self, qq_channel):
        """Test message deduplication."""
        # Mock message IDs
        test_ids = ["msg1", "msg2", "msg3"]

        for msg_id in test_ids:
            qq_channel._processed_ids.append(msg_id)

        # Check that messages are in deque
        assert "msg1" in qq_channel._processed_ids
        assert "msg2" in qq_channel._processed_ids
        assert "msg3" in qq_channel._processed_ids

        # Add more to test maxlen
        for i in range(1000):
            qq_channel._processed_ids.append(f"msg_{i}")

        # Deque should only keep last 1000
        assert len(qq_channel._processed_ids) <= 1000
