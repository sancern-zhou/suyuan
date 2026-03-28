"""Personal WeChat (微信) channel using HTTP long-poll API.

Uses the ilinkai.weixin.qq.com API for personal WeChat messaging.
No WebSocket, no local WeChat client needed — just HTTP requests with a
bot token obtained via QR code login.

Protocol reverse-engineered from ``@tencent-weixin/openclaw-weixin`` v1.0.3.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from app.social.events import OutboundMessage
from app.social.message_bus import MessageBus
from app.channels.base import BaseChannel
from config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

# MessageItemType
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# MessageType  (1 = inbound from user, 2 = outbound from bot)
MESSAGE_TYPE_USER = 1
MESSAGE_TYPE_BOT = 2

# MessageState
MESSAGE_STATE_FINISH = 2

WEIXIN_MAX_MESSAGE_LEN = 4000
WEIXIN_CHANNEL_VERSION = "1.0.3"
BASE_INFO: dict[str, str] = {"channel_version": WEIXIN_CHANNEL_VERSION}

# Session-expired error code
ERRCODE_SESSION_EXPIRED = -14
SESSION_PAUSE_DURATION_S = 60 * 60

# Retry constants
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_S = 30
RETRY_DELAY_S = 2
MAX_QR_REFRESH_COUNT = 3

# Default long-poll timeout
DEFAULT_LONG_POLL_TIMEOUT_S = 35

# Media-type codes for upload
UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3

# File extensions
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico", ".svg"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}


def _parse_aes_key(aes_key_b64: str) -> bytes:
    """Parse a base64-encoded AES key, handling both encodings.

    From nanobot pic-decrypt.ts parseAesKey:
    * base64(raw 16 bytes)            → images (media.aes_key)
    * base64(hex string of 16 bytes)  → file / voice / video

    In the second case base64-decoding yields 32 ASCII hex chars which must
    then be parsed as hex to recover the actual 16-byte key.
    """
    import re
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and re.fullmatch(rb"[0-9a-fA-F]{32}", decoded):
        # hex-encoded key: base64 → hex string → raw bytes
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError(
        f"aes_key must decode to 16 raw bytes or 32-char hex string, got {len(decoded)} bytes"
    )


def _decrypt_aes_ecb(encrypted_data: bytes, key_b64: str) -> bytes:
    """Decrypt AES-128-ECB media data.

    Args:
        encrypted_data: Encrypted bytes
        key_b64: Base64-encoded AES key (always base64-encoded)

    Returns:
        Decrypted bytes
    """
    try:
        key = _parse_aes_key(key_b64)
    except Exception as e:
        logger.warning("Failed to parse AES key", error=str(e))
        raise

    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        cipher = AES.new(key, AES.MODE_ECB)
        decrypted = cipher.decrypt(encrypted_data)
        # Remove PKCS#7 padding
        return unpad(decrypted, AES.block_size)
    except ImportError:
        logger.warning("pycryptodome not installed, cannot decrypt WeChat media")
        raise
    except Exception as e:
        logger.error("AES decryption failed", error=str(e))
        raise


def _ext_for_type(media_type: str) -> str:
    """Get file extension for media type."""
    if media_type == "image":
        return ".jpg"
    elif media_type == "video":
        return ".mp4"
    elif media_type == "voice":
        return ".silk"
    elif media_type == "file":
        return ".bin"
    return ".bin"


def _is_url(path: str) -> bool:
    """Check if path is a URL."""
    return path.startswith(("http://", "https://"))


async def _download_from_url(url: str, dest_dir: Path, client: httpx.AsyncClient) -> Path | None:
    """Download file from URL to local temp directory."""
    try:
        response = await client.get(url)
        response.raise_for_status()

        # Generate filename from URL
        import urllib.parse
        url_path = urllib.parse.urlparse(url).path
        filename = os.path.basename(url_path) or f"download_{int(time.time())}.bin"

        # Try to get extension from Content-Type
        content_type = response.headers.get("content-type", "")
        if "image/png" in content_type:
            if "." not in filename or not filename.endswith(".png"):
                filename = filename.rsplit(".", 1)[0] + ".png" if "." in filename else filename + ".png"
        elif "image/jpeg" in content_type or "image/jpg" in content_type:
            if "." not in filename or not filename.endswith((".jpg", ".jpeg")):
                filename = filename.rsplit(".", 1)[0] + ".jpg" if "." in filename else filename + ".jpg"

        dest_path = dest_dir / filename
        dest_path.write_bytes(response.content)

        logger.info("Downloaded media from URL", url=url, dest=str(dest_path))
        return dest_path

    except Exception as e:
        logger.error("Failed to download media from URL", url=url, error=str(e))
        return None


def _parse_aes_key(aes_key_b64: str) -> bytes:
    """Parse a base64-encoded AES key.

    From nanobot-main: supports two encodings:
    - base64(raw 16 bytes) → images
    - base64(hex string of 16 bytes) → file/voice/video
    """
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded  # 直接是 16 字节原始密钥
    if len(decoded) == 32 and re.fullmatch(rb"[0-9a-fA-F]{32}", decoded):
        # hex-encoded key: base64 → hex string → raw bytes
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError(
        f"aes_key must decode to 16 raw bytes or 32-char hex string, got {len(decoded)} bytes"
    )


def _encrypt_aes_ecb(data: bytes, aes_key_b64: str) -> bytes:
    """Encrypt data with AES-128-ECB and PKCS7 padding."""
    try:
        key = _parse_aes_key(aes_key_b64)
    except Exception as e:
        logger.warning("Failed to parse AES key for encryption", error=str(e))
        return data

    # PKCS7 padding
    pad_len = 16 - len(data) % 16
    padded = data + bytes([pad_len] * pad_len)

    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(padded)
    except ImportError:
        logger.warning("pycryptodome not installed, cannot encrypt")
        return data


def _split_message(text: str, max_len: int) -> list[str]:
    """Split message into chunks if too long."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            if current:
                current += "\n" + line
            else:
                current = line
    if current:
        chunks.append(current)
    return chunks


class WeixinChannel(BaseChannel):
    """
    Personal WeChat channel using HTTP long-poll.

    Connects to ilinkai.weixin.qq.com API to receive and send personal
    WeChat messages. Authentication is via QR code login which produces
    a bot token.

    Supports multiple instances with instance_id parameter.
    """

    name = "weixin"  # 会被实例ID覆盖
    display_name = "WeChat"  # 会被配置中的name覆盖

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {
            "enabled": False,
            "allow_from": ["*"],
            "base_url": "https://ilinkai.weixin.qq.com",
            "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
            "route_tag": None,
            "token": "",
            "state_dir": "",
            "poll_timeout": DEFAULT_LONG_POLL_TIMEOUT_S,
            # 多实例支持
            "id": "",  # 账号ID
            "name": "",  # 显示名称
            "auto_start": True,  # 是否自动启动
        }

    def __init__(self, config: Any, bus: MessageBus, instance_id: str = None):
        """
        Initialize WeixinChannel.

        Args:
            config: Channel configuration
            bus: Message bus instance
            instance_id: Instance ID for multi-account support (e.g., "account_1")
        """
        super().__init__(config, bus)

        # ✅ 多实例支持
        self.instance_id = instance_id or getattr(config, 'id', None) or "default"
        self.name = f"weixin:{self.instance_id}"
        self.display_name = getattr(config, 'name', f"WeChat ({self.instance_id})")

        # State
        self._client: httpx.AsyncClient | None = None
        self._get_updates_buf: str = ""
        self._context_tokens: dict[str, str] = {}
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._state_dir: Path | None = None
        self._token: str = ""
        self._bot_id: str = ""  # ✅ 新增：机器人账号ID
        self._poll_task: asyncio.Task | None = None
        self._next_poll_timeout_s: int = DEFAULT_LONG_POLL_TIMEOUT_S
        self._session_pause_until: float = 0.0

        # QR code state
        self._current_qr_code_path: Path | None = None
        self._current_qr_code_id: str = ""
        self._qr_scanned: bool = False
        self._qr_code_ready = asyncio.Event()  # ✅ 新增：二维码就绪事件
        self._qr_code_ready.clear()  # 确保初始状态为未就绪

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _get_state_dir(self) -> Path:
        """
        Get state directory for this instance.

        Each instance has its own subdirectory for isolation.
        Format: backend_data_registry/social/weixin/{instance_id}/
        """
        if self._state_dir:
            return self._state_dir

        state_dir = getattr(self.config, 'state_dir', '')
        if state_dir:
            d = Path(state_dir).expanduser()
        else:
            # ✅ 多实例支持：每个账号独立的子目录
            d = Path(settings.data_registry_dir) / "social" / "weixin" / self.instance_id

        d.mkdir(parents=True, exist_ok=True)
        self._state_dir = d
        return d

    def _load_state(self) -> bool:
        """Load saved account state. Returns True if a valid token was found."""
        state_file = self._get_state_dir() / "account.json"

        logger.info(
            "loading_state",
            instance_id=self.instance_id,
            state_file=str(state_file),
            file_exists=state_file.exists()
        )

        if not state_file.exists():
            logger.info("state_file_not_found", instance_id=self.instance_id, path=str(state_file))
            return False

        try:
            data = json.loads(state_file.read_text())
            self._token = data.get("token", "")
            self._bot_id = data.get("bot_id", "")  # ✅ 新增：加载机器人账号
            self._get_updates_buf = data.get("get_updates_buf", "")
            context_tokens = data.get("context_tokens", {})
            if isinstance(context_tokens, dict):
                self._context_tokens = {
                    str(user_id): str(token)
                    for user_id, token in context_tokens.items()
                    if str(user_id).strip() and str(token).strip()
                }
            else:
                self._context_tokens = {}
            base_url = data.get("base_url", "")
            if base_url:
                self.config.base_url = base_url

            logger.info(
                "state_loaded_successfully",
                instance_id=self.instance_id,
                has_token=bool(self._token),
                token_preview=self._token[:20] if self._token else "",
                bot_id=self._bot_id,
                context_tokens_count=len(self._context_tokens)
            )

            return bool(self._token)
        except Exception as e:
            logger.warning(
                "Failed to load WeChat state",
                instance_id=self.instance_id,
                error=str(e),
                exc_info=True
            )
            return False

    def _save_state(self, update_config: bool = True) -> None:
        """Save state to local file and optionally update config file.

        Args:
            update_config: Whether to update the token in config file (for persistence)
        """
        state_file = self._get_state_dir() / "account.json"
        try:
            data = {
                "token": self._token,
                "bot_id": self._bot_id,  # ✅ 新增：保存机器人账号
                "get_updates_buf": self._get_updates_buf,
                "context_tokens": self._context_tokens,
                "base_url": getattr(self.config, 'base_url', 'https://ilinkai.weixin.qq.com'),
            }
            state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("Failed to save WeChat state", error=str(e))

        # ✅ 更新配置文件中的 token（确保重启后能恢复登录）
        if update_config and self._token and hasattr(self.config, 'token'):
            try:
                # 保存 token 到配置对象
                self.config.token = self._token

                # 如果有 instance_id，更新配置文件
                if self.instance_id:
                    from config.social_config import load_social_config, save_social_config
                    config = load_social_config()

                    # 找到对应的账号并更新 token
                    for acc in config.weixin.accounts:
                        if acc.id == self.instance_id:
                            acc.token = self._token
                            # logger.info("Updating token in config file", account_id=self.instance_id)  # 已禁用日志
                            break

                    # 保存配置
                    save_social_config(config)
                    # logger.info("Token saved to config file", account_id=self.instance_id)  # 已禁用日志

            except Exception as e:
                logger.warning("Failed to save token to config file", error=str(e))

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _random_wechat_uin() -> str:
        """X-WECHAT-UIN: random uint32 -> decimal string -> base64."""
        uint32 = int.from_bytes(os.urandom(4), "big")
        return base64.b64encode(str(uint32).encode()).decode()

    def _make_headers(self, *, auth: bool = True) -> dict[str, str]:
        """Build per-request headers."""
        headers: dict[str, str] = {
            "X-WECHAT-UIN": self._random_wechat_uin(),
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
        }
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        route_tag = getattr(self.config, 'route_tag', None)
        if route_tag is not None and str(route_tag).strip():
            headers["SKRouteTag"] = str(route_tag).strip()

        return headers

    async def _api_get(
        self,
        endpoint: str,
        params: dict | None = None,
        *,
        auth: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        assert self._client is not None
        url = f"{getattr(self.config, 'base_url', 'https://ilinkai.weixin.qq.com')}/{endpoint}"
        hdrs = self._make_headers(auth=auth)
        if extra_headers:
            hdrs.update(extra_headers)
        resp = await self._client.get(url, params=params, headers=hdrs)
        resp.raise_for_status()
        return resp.json()

    async def _api_post(
        self,
        endpoint: str,
        body: dict | None = None,
        *,
        auth: bool = True,
    ) -> dict:
        assert self._client is not None
        url = f"{getattr(self.config, 'base_url', 'https://ilinkai.weixin.qq.com')}/{endpoint}"
        payload = body or {}
        if "base_info" not in payload:
            payload["base_info"] = BASE_INFO
        resp = await self._client.post(url, json=payload, headers=self._make_headers(auth=auth))
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # QR Code Login
    # ------------------------------------------------------------------

    async def _fetch_qr_code(self) -> tuple[str, str]:
        """Fetch a fresh QR code. Returns (qrcode_id, scan_url)."""
        data = await self._api_get(
            "ilink/bot/get_bot_qrcode",
            params={"bot_type": "3"},
            auth=False,
        )
        qrcode_img_content = data.get("qrcode_img_content", "")
        qrcode_id = data.get("qrcode", "")
        if not qrcode_id:
            raise RuntimeError(f"Failed to get QR code from WeChat API: {data}")
        return qrcode_id, (qrcode_img_content or qrcode_id)

    async def _init_qr_login(self) -> str:
        """
        初始化二维码登录（只生成二维码，不等待扫码）

        Returns:
            二维码ID
        """
        # ✅ 清除就绪事件，准备生成新的二维码
        self._qr_code_ready.clear()

        logger.info("Initializing WeChat QR code...")
        qrcode_id, scan_url = await self._fetch_qr_code()

        # Save QR code as image for web UI
        self._save_qr_code_image(scan_url, qrcode_id)

        # Also print to terminal
        self._print_qr_code(scan_url)

        logger.info("QR code initialized", qrcode_id=qrcode_id)
        return qrcode_id

    async def _wait_for_qr_scan(self, qrcode_id: str) -> bool:
        """
        等待已有二维码的扫码（不生成新二维码）

        Args:
            qrcode_id: 二维码ID

        Returns:
            是否登录成功
        """
        logger.info("Waiting for QR code scan...", qrcode_id=qrcode_id)

        refresh_count = 0
        while self._running:
            try:
                status_data = await self._api_get(
                    "ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode_id},
                    auth=False,
                    extra_headers={"iLink-App-ClientVersion": "1"},
                )
            except httpx.TimeoutException:
                continue

            status = status_data.get("status", "")
            if status == "confirmed":
                token = status_data.get("bot_token", "")
                bot_id = status_data.get("ilink_bot_id", "")
                base_url = status_data.get("baseurl", "")
                user_id = status_data.get("ilink_user_id", "")
                if token:
                    self._token = token
                    self._bot_id = bot_id
                    if base_url:
                        self.config.base_url = base_url
                    self._save_state()
                    logger.info(
                        "WeChat login successful",
                        bot_id=bot_id,
                        user_id=user_id
                    )
                    return True
                else:
                    logger.error("Login confirmed but no bot_token in response")
                    return False
            elif status == "scaned":
                logger.info("QR code scanned, waiting for confirmation...")
            elif status == "expired":
                refresh_count += 1
                if refresh_count > MAX_QR_REFRESH_COUNT:
                    logger.warning(
                        "QR code expired too many times, giving up",
                        count=refresh_count,
                        max_count=MAX_QR_REFRESH_COUNT
                    )
                    return False
                logger.warning(
                    "QR code expired, refreshing...",
                    count=refresh_count,
                    max_count=MAX_QR_REFRESH_COUNT
                )
                # 刷新二维码（生成新的）
                qrcode_id, scan_url = await self._fetch_qr_code()
                self._save_qr_code_image(scan_url, qrcode_id)
                self._print_qr_code(scan_url)
                logger.info("New QR code generated, waiting for scan...")
                continue

            await asyncio.sleep(1)

        logger.error("WeChat QR scan wait failed")
        return False

    async def _qr_login(self) -> bool:
        """Perform QR code login flow. Returns True on success."""
        try:
            # ✅ 清除就绪事件，准备生成新的二维码
            self._qr_code_ready.clear()

            logger.info("Starting WeChat QR code login...")
            refresh_count = 0
            qrcode_id, scan_url = await self._fetch_qr_code()

            # Save QR code as image for web UI
            self._save_qr_code_image(scan_url, qrcode_id)

            # Also print to terminal
            self._print_qr_code(scan_url)

            logger.info("Waiting for QR code scan...")
            while self._running:
                try:
                    status_data = await self._api_get(
                        "ilink/bot/get_qrcode_status",
                        params={"qrcode": qrcode_id},
                        auth=False,
                        extra_headers={"iLink-App-ClientVersion": "1"},
                    )
                except httpx.TimeoutException:
                    continue

                status = status_data.get("status", "")
                if status == "confirmed":
                    token = status_data.get("bot_token", "")
                    bot_id = status_data.get("ilink_bot_id", "")
                    base_url = status_data.get("baseurl", "")
                    user_id = status_data.get("ilink_user_id", "")
                    if token:
                        self._token = token
                        self._bot_id = bot_id  # ✅ 新增：保存机器人账号
                        if base_url:
                            self.config.base_url = base_url
                        self._save_state()
                        logger.info(
                            "WeChat login successful",
                            bot_id=bot_id,
                            user_id=user_id
                        )
                        return True
                    else:
                        logger.error("Login confirmed but no bot_token in response")
                        return False
                elif status == "scaned":
                    logger.info("QR code scanned, waiting for confirmation...")
                elif status == "expired":
                    refresh_count += 1
                    if refresh_count > MAX_QR_REFRESH_COUNT:
                        logger.warning(
                            "QR code expired too many times, giving up",
                            count=refresh_count,
                            max_count=MAX_QR_REFRESH_COUNT
                        )
                        return False
                    logger.warning(
                        "QR code expired, refreshing...",
                        count=refresh_count,
                        max_count=MAX_QR_REFRESH_COUNT
                    )
                    qrcode_id, scan_url = await self._fetch_qr_code()
                    self._print_qr_code(scan_url)
                    logger.info("New QR code generated, waiting for scan...")
                    continue

                await asyncio.sleep(1)

        except Exception as e:
            logger.error("WeChat QR login failed", error=str(e))

        return False

    @staticmethod
    def _print_qr_code(url: str) -> None:
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except ImportError:
            logger.info("QR code URL (install 'qrcode' for terminal display)", url=url)
            print(f"\nLogin URL: {url}\n")

    def _save_qr_code_image(self, url: str, qrcode_id: str) -> None:
        """Save QR code as image file for web UI access."""
        try:
            import qrcode as qr_lib

            # Create QR code directory
            state_dir = self._get_state_dir()
            qr_dir = state_dir / "qrcode"
            qr_dir.mkdir(parents=True, exist_ok=True)

            # Generate QR code image
            qr = qr_lib.QRCode(
                version=1,
                error_correction=qr_lib.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Save image
            qr_path = qr_dir / f"qrcode_{qrcode_id}.png"
            img.save(qr_path)

            # Store path for API access
            self._current_qr_code_path = qr_path
            self._current_qr_code_id = qrcode_id

            # ✅ 设置二维码就绪事件
            self._qr_code_ready.set()

            logger.info("QR code saved", path=str(qr_path))
        except Exception as e:
            logger.warning("Failed to save QR code image", error=str(e))

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    async def login(self, force: bool = False) -> bool:
        """Perform QR code login and save token. Returns True on success."""
        if force:
            self._token = ""
            self._get_updates_buf = ""
            state_file = self._get_state_dir() / "account.json"
            if state_file.exists():
                state_file.unlink()

        if self._token or self._load_state():
            return True

        # Initialize HTTP client for the login flow
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=30),
            follow_redirects=True,
        )
        self._running = True
        try:
            return await self._qr_login()
        finally:
            self._running = False
            if self._client:
                await self._client.aclose()
                self._client = None

    async def start(self) -> None:
        """Start the WeChat channel with long-poll."""
        self._running = True
        poll_timeout = getattr(self.config, 'poll_timeout', DEFAULT_LONG_POLL_TIMEOUT_S)
        self._next_poll_timeout_s = poll_timeout
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._next_poll_timeout_s + 10, connect=30),
            follow_redirects=True,
        )

        logger.info(
            "WeChat channel starting",
            instance_id=self.instance_id,
            state_dir=str(self._get_state_dir())
        )

        config_token = getattr(self.config, 'token', '')
        logger.info(
            "weixin_start_token_check",
            instance_id=self.instance_id,
            has_config_token=bool(config_token),
            config_token_preview=config_token[:10] if config_token else ""
        )

        if config_token:
            # 配置文件中指定了 token，使用配置的 token
            self._token = config_token
            logger.info("using_config_token", instance_id=self.instance_id)
        else:
            # 尝试从状态文件加载
            state_loaded = self._load_state()
            logger.info(
                "state_load_attempt",
                instance_id=self.instance_id,
                state_loaded=state_loaded,
                has_token=bool(self._token),
                token_preview=self._token[:10] if self._token else "",
                bot_id=self._bot_id
            )

            if not state_loaded:
                # 状态文件不存在或无效
                # 检查是否已经有二维码在等待（由 _init_qr_login 生成）
                if self._current_qr_code_path and self._current_qr_code_id:
                    # 已有二维码，继续等待扫码
                    logger.info(
                        "existing_qrcode_found_continuing_wait",
                        instance_id=self.instance_id,
                        qrcode_id=self._current_qr_code_id
                    )
                    # 继续等待该二维码的扫码状态
                    if not await self._wait_for_qr_scan(self._current_qr_code_id):
                        logger.error("WeChat QR scan wait failed", instance_id=self.instance_id)
                        self._running = False
                        return
                else:
                    # 没有二维码，生成新的并等待扫码
                    logger.info("no_saved_state_starting_qr_login", instance_id=self.instance_id)
                    if not await self._qr_login():
                        logger.error("WeChat QR login failed", instance_id=self.instance_id)
                        self._running = False
                        return
            else:
                logger.info(
                    "loaded_saved_state",
                    instance_id=self.instance_id,
                    bot_id=self._bot_id,
                    token_valid=bool(self._token)
                )

        logger.info(
            "WeChat channel starting with long-poll",
            instance_id=self.instance_id,
            has_token=bool(self._token),
            bot_id=self._bot_id
        )

        consecutive_failures = 0
        while self._running:
            try:
                await self._poll_once()
                consecutive_failures = 0
            except httpx.TimeoutException:
                # Normal for long-poll
                continue
            except Exception as e:
                if not self._running:
                    break
                consecutive_failures += 1
                logger.error(
                    "WeChat poll error",
                    count=consecutive_failures,
                    max=MAX_CONSECUTIVE_FAILURES,
                    error=str(e)
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await asyncio.sleep(BACKOFF_DELAY_S)
                else:
                    await asyncio.sleep(RETRY_DELAY_S)

    async def stop(self) -> None:
        """Stop the WeChat channel."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        if self._client:
            await self._client.aclose()
            self._client = None
        self._save_state()
        logger.info("WeChat channel stopped")

    @property
    def bot_account(self) -> str:
        """
        获取微信机器人账号标识

        Returns:
            机器人账号ID（格式：wxid_abc）或带实例ID的默认值
        """
        if self._bot_id:
            return self._bot_id
        # 返回带实例ID的默认标识
        return f"weixin_{self.instance_id}"

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _pause_session(self, duration_s: int = SESSION_PAUSE_DURATION_S) -> None:
        self._session_pause_until = time.time() + duration_s

    def _session_pause_remaining_s(self) -> int:
        remaining = int(self._session_pause_until - time.time())
        if remaining <= 0:
            self._session_pause_until = 0.0
            return 0
        return remaining

    def _assert_session_active(self) -> None:
        remaining = self._session_pause_remaining_s()
        if remaining > 0:
            remaining_min = max((remaining + 59) // 60, 1)
            raise RuntimeError(
                f"WeChat session paused, {remaining_min} min remaining (errcode {ERRCODE_SESSION_EXPIRED})"
            )

    async def _poll_once(self) -> None:
        remaining = self._session_pause_remaining_s()
        if remaining > 0:
            logger.warning(
                "WeChat session paused, waiting before next poll",
                minutes=max((remaining + 59) // 60, 1)
            )
            await asyncio.sleep(remaining)
            return

        body: dict[str, Any] = {
            "get_updates_buf": self._get_updates_buf,
            "base_info": BASE_INFO,
        }

        assert self._client is not None
        self._client.timeout = httpx.Timeout(self._next_poll_timeout_s + 10, connect=30)

        data = await self._api_post("ilink/bot/getupdates", body)

        # Check for API-level errors
        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)
        is_error = (ret is not None and ret != 0) or (errcode is not None and errcode != 0)

        if is_error:
            if errcode == ERRCODE_SESSION_EXPIRED or ret == ERRCODE_SESSION_EXPIRED:
                self._pause_session()
                remaining = self._session_pause_remaining_s()
                logger.warning(
                    "WeChat session expired, pausing",
                    errcode=errcode,
                    minutes=max((remaining + 59) // 60, 1)
                )
                return
            raise RuntimeError(
                f"getUpdates failed: ret={ret} errcode={errcode} errmsg={data.get('errmsg', '')}"
            )

        # Honour server-suggested poll timeout
        server_timeout_ms = data.get("longpolling_timeout_ms")
        if server_timeout_ms and server_timeout_ms > 0:
            self._next_poll_timeout_s = max(server_timeout_ms // 1000, 5)

        # Update cursor
        new_buf = data.get("get_updates_buf", "")
        if new_buf:
            self._get_updates_buf = new_buf
            self._save_state()

        # Process messages
        msgs: list[dict] = data.get("msgs", []) or []
        for msg in msgs:
            try:
                await self._process_message(msg)
            except Exception as e:
                logger.error("Error processing WeChat message", error=str(e))

    # ------------------------------------------------------------------
    # Inbound message processing
    # ------------------------------------------------------------------

    async def _process_message(self, msg: dict) -> None:
        """Process a single WeixinMessage from getUpdates."""
        # Skip bot's own messages
        if msg.get("message_type") == MESSAGE_TYPE_BOT:
            return

        # Deduplication by message_id
        msg_id = str(msg.get("message_id", "") or msg.get("seq", ""))
        if not msg_id:
            msg_id = f"{msg.get('from_user_id', '')}_{msg.get('create_time_ms', '')}"
        if msg_id in self._processed_ids:
            return
        self._processed_ids[msg_id] = None
        while len(self._processed_ids) > 1000:
            self._processed_ids.popitem(last=False)

        from_user_id = msg.get("from_user_id", "") or ""
        if not from_user_id:
            return

        # Cache context_token
        ctx_token = msg.get("context_token", "")
        if ctx_token:
            self._context_tokens[from_user_id] = ctx_token
            self._save_state()

        # Parse item_list
        item_list: list[dict] = msg.get("item_list") or []
        content_parts: list[str] = []
        media_paths: list[str] = []

        for item in item_list:
            item_type = item.get("type", 0)

            if item_type == ITEM_TEXT:
                text = (item.get("text_item") or {}).get("text", "")
                if text:
                    # Handle quoted/ref messages
                    ref = item.get("ref_msg")
                    if ref:
                        ref_item = ref.get("message_item")
                        if ref_item and ref_item.get("type", 0) in (
                            ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO
                        ):
                            content_parts.append(text)
                        else:
                            parts: list[str] = []
                            if ref.get("title"):
                                parts.append(ref["title"])
                            if ref_item:
                                ref_text = (ref_item.get("text_item") or {}).get("text", "")
                                if ref_text:
                                    parts.append(ref_text)
                            if parts:
                                content_parts.append(f"[引用: {' | '.join(parts)}]\n{text}")
                            else:
                                content_parts.append(text)
                    else:
                        content_parts.append(text)

            elif item_type == ITEM_IMAGE:
                image_item = item.get("image_item") or {}
                file_path = await self._download_media_item(image_item, "image")
                if file_path:
                    content_parts.append(f"[image]\n[Image: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    content_parts.append("[image]")

            elif item_type == ITEM_VOICE:
                voice_item = item.get("voice_item") or {}
                voice_text = voice_item.get("text", "")
                if voice_text:
                    content_parts.append(f"[voice] {voice_text}")
                else:
                    file_path = await self._download_media_item(voice_item, "voice")
                    if file_path:
                        content_parts.append(f"[voice]\n[Audio: source: {file_path}]")
                        media_paths.append(file_path)
                    else:
                        content_parts.append("[voice]")

            elif item_type == ITEM_FILE:
                file_item = item.get("file_item") or {}
                file_name = file_item.get("file_name", "unknown")
                file_path = await self._download_media_item(
                    file_item,
                    "file",
                    file_name,
                )
                if file_path:
                    content_parts.append(f"[file: {file_name}]\n[File: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    # 文件下载失败，明确提示
                    logger.warning("File download failed, adding error message to content", file_name=file_name)
                    content_parts.append(f"[file: {file_name}]\n⚠️ 文件下载失败，无法读取文件内容。请尝试重新发送文件。")

            elif item_type == ITEM_VIDEO:
                video_item = item.get("video_item") or {}
                file_path = await self._download_media_item(video_item, "video")
                if file_path:
                    content_parts.append(f"[video]\n[Video: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    content_parts.append("[video]")

        content = "\n".join(content_parts)
        if not content:
            return

        logger.info(
            "WeChat inbound message",
            from_user=from_user_id,
            item_types=",".join(str(i.get("type", 0)) for i in item_list),
            content_len=len(content)
        )

        await self._handle_message(
            sender_id=from_user_id,
            chat_id=from_user_id,
            content=content,
            media=media_paths or None,
            metadata={"message_id": msg_id},
        )

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    async def _download_media_item(
        self,
        typed_item: dict,
        media_type: str,
        filename: str | None = None,
    ) -> str | None:
        """Download + AES-decrypt a media item. Returns local path or None."""
        try:
            media = typed_item.get("media") or {}
            encrypt_query_param = media.get("encrypt_query_param", "")

            if not encrypt_query_param:
                logger.warning("WeChat media item missing encrypt_query_param", media_type=media_type, filename=filename)
                return None

            # Resolve AES key
            raw_aeskey_hex = typed_item.get("aeskey", "")
            media_aes_key_b64 = media.get("aes_key", "")

            aes_key_b64: str = ""
            if raw_aeskey_hex:
                aes_key_b64 = base64.b64encode(bytes.fromhex(raw_aeskey_hex)).decode()
                logger.debug("Using raw_aeskey_hex for decryption", media_type=media_type)
            elif media_aes_key_b64:
                aes_key_b64 = media_aes_key_b64
                logger.debug("Using media_aes_key_b64 for decryption", media_type=media_type)

            logger.debug("AES key info", has_key=bool(aes_key_b64), media_type=media_type, filename=filename)

            # Build CDN download URL
            cdn_base = getattr(self.config, 'cdn_base_url', 'https://novac2c.cdn.weixin.qq.com/c2c')
            cdn_url = (
                f"{cdn_base}/download"
                f"?encrypted_query_param={quote(encrypt_query_param)}"
            )

            assert self._client is not None
            resp = await self._client.get(cdn_url)
            resp.raise_for_status()
            data = resp.content

            # 尝试 AES 解密（所有媒体类型都需要解密）
            if aes_key_b64 and data:
                try:
                    data = _decrypt_aes_ecb(data, aes_key_b64)
                    logger.debug("AES decryption successful", type=media_type, filename=filename)
                except Exception as decrypt_error:
                    logger.error("AES decryption failed", type=media_type, error=str(decrypt_error))
                    return None
            elif not aes_key_b64:
                logger.debug("No AES key for media item, using raw bytes", type=media_type)

            if not data:
                return None

            media_dir = self._get_state_dir() / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            ext = _ext_for_type(media_type)
            if not filename:
                ts = int(time.time())
                h = abs(hash(encrypt_query_param)) % 100000
                filename = f"{media_type}_{ts}_{h}{ext}"
            safe_name = os.path.basename(filename)
            file_path = media_dir / safe_name
            file_path.write_bytes(data)
            # 返回绝对路径，避免工具查找时路径不匹配
            absolute_path = file_path.resolve()
            logger.debug("Downloaded WeChat media", type=media_type, path=str(absolute_path))
            return str(absolute_path)

        except Exception as e:
            logger.error("Error downloading WeChat media", error=str(e))
            return None

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WeChat.

        ⚠️ 支持流式输出（social模式）：
        - 检查metadata中的_stream_id和_stream_end标志
        - 流式中间片段：快速发送，不分割
        - 最终消息：正常处理（分割长消息）
        """
        logger.info("WeChat send called",
                   chat_id=msg.chat_id,
                   content_preview=msg.content[:50] if msg.content else "",
                   context_tokens_count=len(self._context_tokens),
                   available_context_tokens=list(self._context_tokens.keys()))

        if not self._client or not self._token:
            logger.warning("WeChat client not initialized or not authenticated")
            return

        try:
            self._assert_session_active()
        except RuntimeError as e:
            logger.warning("WeChat send blocked", error=str(e))
            return

        content = msg.content.strip()
        ctx_token = self._context_tokens.get(msg.chat_id, "")
        if not ctx_token:
            logger.warning("WeChat: no context_token for chat_id",
                           chat_id=msg.chat_id,
                           available_tokens=list(self._context_tokens.keys()))
            return

        # ✅ 检查是否为流式消息（social模式）
        stream_id = msg.metadata.get("_stream_id") if msg.metadata else None
        is_stream_end = msg.metadata.get("_stream_end", True) if msg.metadata else True

        # Send media files first（仅最终消息）
        logger.info("WeChat send: checking media",
                   media_count=len(msg.media or []),
                   media_list=msg.media,
                   is_stream_end=is_stream_end)
        if is_stream_end:
            for media_path in (msg.media or []):
                try:
                    logger.info("WeChat send: attempting to send media", path=media_path)
                    await self._send_media_file(msg.chat_id, media_path, ctx_token)
                    logger.info("WeChat send: media sent successfully", path=media_path)
                except Exception as e:
                    filename = Path(media_path).name
                    logger.error("Failed to send WeChat media", path=media_path, error=str(e))
                    await self._send_text(
                        msg.chat_id, f"[Failed to send: {filename}]", ctx_token
                    )

        # Send text content
        if not content:
            return

        try:
            # ✅ 流式中间片段：快速发送，不分割
            if stream_id and not is_stream_end:
                # 流式输出：直接发送，不分割
                await self._send_text(msg.chat_id, content, ctx_token)
                logger.debug("stream_chunk_sent", stream_id=stream_id, length=len(content))
            else:
                # 最终消息：正常处理（分割长消息）
                chunks = _split_message(content, WEIXIN_MAX_MESSAGE_LEN)
                for chunk in chunks:
                    await self._send_text(msg.chat_id, chunk, ctx_token)
        except Exception as e:
            logger.error("Error sending WeChat message", error=str(e))
            raise

    async def _send_text(
        self,
        to_user_id: str,
        text: str,
        context_token: str,
    ) -> None:
        """Send a text message."""
        client_id = f"suyuan-{uuid.uuid4().hex[:12]}"

        item_list: list[dict] = []
        if text:
            item_list.append({"type": ITEM_TEXT, "text_item": {"text": text}})

        weixin_msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
        }
        if item_list:
            weixin_msg["item_list"] = item_list
        if context_token:
            weixin_msg["context_token"] = context_token

        body: dict[str, Any] = {
            "msg": weixin_msg,
            "base_info": BASE_INFO,
        }

        logger.info("WeChat API calling",
                   endpoint="ilink/bot/sendmessage",
                   to_user_id=to_user_id,
                   text_length=len(text),
                   has_context_token=bool(context_token))

        data = await self._api_post("ilink/bot/sendmessage", body)

        logger.info("WeChat API response received",
                   errcode=data.get("errcode", 0),
                   response=data)

        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning(
                "WeChat send error",
                code=errcode,
                message=data.get("errmsg", "")
            )
        else:
            logger.info("WeChat message sent successfully",
                       to_user_id=to_user_id,
                       text_length=len(text))

    async def _send_media_file(
        self,
        to_user_id: str,
        media_path: str,
        context_token: str,
    ) -> None:
        """Upload a local file to WeChat CDN and send it as a media message.

        Follows the exact protocol from @tencent-weixin/openclaw-weixin v1.0.3:
        1. Generate a random 16-byte AES key (client-side).
        2. Call getuploadurl with file metadata + hex-encoded AES key.
        3. AES-128-ECB encrypt the file and POST to CDN.
        4. Read x-encrypted-param header from CDN response as the download param.
        5. Send a sendmessage with the appropriate media item referencing the upload.

        Note: Simplified from nanobot implementation - no URL download support.
        """
        p = Path(media_path)
        try:
            if not p.is_file():
                raise FileNotFoundError(f"Media file not found: {media_path}")
        except PermissionError as e:
            logger.error(
                "Permission denied when accessing file",
                path=media_path,
                error=str(e)
            )
            raise FileNotFoundError(
                f"Cannot access file (permission denied): {media_path}. "
                f"Please ensure the file is in a readable location (not in /root/ directory)."
            )

        raw_data = p.read_bytes()
        raw_size = len(raw_data)
        raw_md5 = hashlib.md5(raw_data).hexdigest()

        # Determine upload media type from extension
        ext = p.suffix.lower()
        if ext in _IMAGE_EXTS:
            upload_type = UPLOAD_MEDIA_IMAGE
            item_type = ITEM_IMAGE
            item_key = "image_item"
        elif ext in _VIDEO_EXTS:
            upload_type = UPLOAD_MEDIA_VIDEO
            item_type = ITEM_VIDEO
            item_key = "video_item"
        else:
            upload_type = UPLOAD_MEDIA_FILE
            item_type = ITEM_FILE
            item_key = "file_item"

        # Generate client-side AES-128 key (16 random bytes)
        aes_key_raw = os.urandom(16)
        aes_key_hex = aes_key_raw.hex()

        # Compute encrypted size: PKCS7 padding to 16-byte boundary
        padded_size = ((raw_size + 1 + 15) // 16) * 16

        # Step 1: Get upload URL (upload_param) from server
        file_key = os.urandom(16).hex()
        upload_body: dict[str, Any] = {
            "filekey": file_key,
            "media_type": upload_type,
            "to_user_id": to_user_id,
            "rawsize": raw_size,
            "rawfilemd5": raw_md5,
            "filesize": padded_size,
            "no_need_thumb": True,  # ✅ 关键参数：不需要生成缩略图
            "aeskey": aes_key_hex,
        }

        assert self._client is not None
        upload_resp = await self._api_post("ilink/bot/getuploadurl", upload_body)
        logger.debug("WeChat getuploadurl response", response=upload_resp)

        upload_param = upload_resp.get("upload_param", "")
        if not upload_param:
            raise RuntimeError(f"getuploadurl returned no upload_param: {upload_resp}")

        # Step 2: AES-128-ECB encrypt and POST to CDN
        aes_key_b64 = base64.b64encode(aes_key_raw).decode()
        encrypted_data = _encrypt_aes_ecb(raw_data, aes_key_b64)

        cdn_base = getattr(self.config, 'cdn_base_url', 'https://novac2c.cdn.weixin.qq.com/c2c')
        cdn_upload_url = (
            f"{cdn_base}/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(file_key)}"
        )
        logger.debug(
            "WeChat CDN POST",
            url=cdn_upload_url[:80],
            ciphertext_size=len(encrypted_data)
        )

        cdn_resp = await self._client.post(
            cdn_upload_url,
            content=encrypted_data,
            headers={"Content-Type": "application/octet-stream"},
        )
        cdn_resp.raise_for_status()

        # The download encrypted_query_param comes from CDN response header
        download_param = cdn_resp.headers.get("x-encrypted-param", "")
        if not download_param:
            raise RuntimeError(
                "CDN upload response missing x-encrypted-param header; "
                f"status={cdn_resp.status_code} headers={dict(cdn_resp.headers)}"
            )
        logger.debug("WeChat CDN upload success", filename=p.name)

        # Step 3: Send message with the media item
        cdn_aes_key_b64 = base64.b64encode(aes_key_hex.encode()).decode()

        media_item: dict[str, Any] = {
            "media": {
                "encrypt_query_param": download_param,
                "aes_key": cdn_aes_key_b64,
                "encrypt_type": 1,
            },
        }

        if item_type == ITEM_IMAGE:
            media_item["mid_size"] = padded_size
        elif item_type == ITEM_VIDEO:
            media_item["video_size"] = padded_size
        elif item_type == ITEM_FILE:
            media_item["file_name"] = p.name
            media_item["len"] = str(raw_size)

        client_id = f"suyuan-{uuid.uuid4().hex[:12]}"
        item_list: list[dict] = [{"type": item_type, item_key: media_item}]

        weixin_msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
        }
        if context_token:
            weixin_msg["context_token"] = context_token

        body: dict[str, Any] = {
            "msg": weixin_msg,
            "base_info": BASE_INFO,
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            raise RuntimeError(
                f"WeChat send media error (code {errcode}): {data.get('errmsg', '')}"
            )
        logger.info(
            "WeChat media sent successfully",
            filename=p.name,
            type=item_key,
            size=raw_size,
            source="url" if _is_url(media_path) else "local"
        )

        # Cleanup: delete temp file if it was downloaded from URL
        if _is_url(media_path) and p.exists():
            try:
                p.unlink()
                logger.debug("Cleaned up temp file", path=str(p))
            except Exception as e:
                logger.warning("Failed to cleanup temp file", path=str(p), error=str(e))
