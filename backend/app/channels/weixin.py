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


def _decrypt_aes_ecb(encrypted_data: bytes, key_b64: str) -> bytes:
    """Decrypt AES-ECB encrypted data.

    Args:
        encrypted_data: Encrypted bytes
        key_b64: Base64-encoded AES key

    Returns:
        Decrypted bytes
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        key = base64.b64decode(key_b64)
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
    """

    name = "weixin"
    display_name = "WeChat"

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
        }

    def __init__(self, config: Any, bus: MessageBus):
        super().__init__(config, bus)

        # State
        self._client: httpx.AsyncClient | None = None
        self._get_updates_buf: str = ""
        self._context_tokens: dict[str, str] = {}
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._state_dir: Path | None = None
        self._token: str = ""
        self._poll_task: asyncio.Task | None = None
        self._next_poll_timeout_s: int = DEFAULT_LONG_POLL_TIMEOUT_S
        self._session_pause_until: float = 0.0

        # QR code state
        self._current_qr_code_path: Path | None = None
        self._current_qr_code_id: str = ""
        self._qr_scanned: bool = False

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _get_state_dir(self) -> Path:
        if self._state_dir:
            return self._state_dir

        state_dir = getattr(self.config, 'state_dir', '')
        if state_dir:
            d = Path(state_dir).expanduser()
        else:
            d = Path(settings.data_registry_dir) / "social" / "weixin"

        d.mkdir(parents=True, exist_ok=True)
        self._state_dir = d
        return d

    def _load_state(self) -> bool:
        """Load saved account state. Returns True if a valid token was found."""
        state_file = self._get_state_dir() / "account.json"
        if not state_file.exists():
            return False

        try:
            data = json.loads(state_file.read_text())
            self._token = data.get("token", "")
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
            return bool(self._token)
        except Exception as e:
            logger.warning("Failed to load WeChat state", error=str(e))
            return False

    def _save_state(self) -> None:
        state_file = self._get_state_dir() / "account.json"
        try:
            data = {
                "token": self._token,
                "get_updates_buf": self._get_updates_buf,
                "context_tokens": self._context_tokens,
                "base_url": getattr(self.config, 'base_url', 'https://ilinkai.weixin.qq.com'),
            }
            state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("Failed to save WeChat state", error=str(e))

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

    async def _qr_login(self) -> bool:
        """Perform QR code login flow. Returns True on success."""
        try:
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

        config_token = getattr(self.config, 'token', '')
        if config_token:
            self._token = config_token
        elif not self._load_state():
            if not await self._qr_login():
                logger.error("WeChat login failed")
                self._running = False
                return

        logger.info("WeChat channel starting with long-poll...")

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
                    content_parts.append(f"[file: {file_name}]")

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
                return None

            # Resolve AES key
            raw_aeskey_hex = typed_item.get("aeskey", "")
            media_aes_key_b64 = media.get("aes_key", "")

            aes_key_b64: str = ""
            if raw_aeskey_hex:
                aes_key_b64 = base64.b64encode(bytes.fromhex(raw_aeskey_hex)).decode()
            elif media_aes_key_b64:
                aes_key_b64 = media_aes_key_b64

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

            if aes_key_b64 and data:
                data = _decrypt_aes_ecb(data, aes_key_b64)
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
            logger.debug("Downloaded WeChat media", type=media_type, path=str(file_path))
            return str(file_path)

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
            logger.warning("WeChat: no context_token for chat_id", chat_id=msg.chat_id)
            return

        # ✅ 检查是否为流式消息（social模式）
        stream_id = msg.metadata.get("_stream_id") if msg.metadata else None
        is_stream_end = msg.metadata.get("_stream_end", True) if msg.metadata else True

        # Send media files first（仅最终消息）
        if is_stream_end:
            for media_path in (msg.media or []):
                try:
                    await self._send_media_file(msg.chat_id, media_path, ctx_token)
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

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning(
                "WeChat send error",
                code=errcode,
                message=data.get("errmsg", "")
            )

    async def _send_media_file(
        self,
        to_user_id: str,
        media_path: str,
        context_token: str,
    ) -> None:
        """Send a media file (image, video, or file)."""
        try:
            # 检查文件是否存在
            if not Path(media_path).exists():
                logger.warning("Media file not found", path=media_path)
                filename = Path(media_path).name
                await self._send_text(to_user_id, f"[文件不存在: {filename}]", context_token)
                return

            # 判断文件类型
            filename = Path(media_path).name
            suffix = Path(media_path).suffix.lower()

            if suffix in _IMAGE_EXTS:
                # 上传并发送图片
                await self._send_image(to_user_id, media_path, context_token)
            elif suffix in _VIDEO_EXTS:
                # 上传并发送视频
                await self._send_video(to_user_id, media_path, context_token)
            else:
                # 上传并发送文件
                await self._send_file(to_user_id, media_path, context_token)

            logger.info("Media file sent successfully", path=media_path, type=suffix)

        except Exception as e:
            logger.error("Failed to send media file", path=media_path, error=str(e))
            filename = Path(media_path).name
            await self._send_text(to_user_id, f"[发送文件失败: {filename}]", context_token)

    async def _upload_media(
        self,
        file_path: str,
        media_type: int
    ) -> str | None:
        """
        上传媒体文件到微信服务器

        Args:
            file_path: 文件路径
            media_type: 媒体类型（1=图片, 2=视频, 3=文件）

        Returns:
            media_id 或 None
        """
        try:
            if not Path(file_path).exists():
                logger.warning("File not found for upload", path=file_path)
                return None

            # 读取文件
            with open(file_path, "rb") as f:
                file_data = f.read()

            # 构建multipart/form-data请求
            filename = Path(file_path).name
            files = {
                "media": (filename, file_data),
                "type": str(media_type)
            }

            # 发送上传请求
            url = f"{getattr(self.config, 'base_url', 'https://ilinkai.weixin.qq.com')}/ilink/bot/uploadmedia"

            headers = {
                "Authorization": f"ilink_bot_token {self._token}",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, files=files)
                response.raise_for_status()
                data = response.json()

            # 检查上传结果
            errcode = data.get("errcode", 0)
            if errcode == 0:
                media_id = data.get("data", {}).get("media_id")
                logger.info("Media uploaded successfully", media_id=media_id, path=file_path)
                return media_id
            else:
                logger.error("Failed to upload media", errcode=errcode, errmsg=data.get("errmsg"))
                return None

        except Exception as e:
            logger.error("Error uploading media", path=file_path, error=str(e))
            return None

    async def _send_image(
        self,
        to_user_id: str,
        image_path: str,
        context_token: str,
    ) -> None:
        """发送图片"""
        # 上传图片
        media_id = await self._upload_media(image_path, UPLOAD_MEDIA_IMAGE)
        if not media_id:
            logger.warning("Failed to upload image", path=image_path)
            filename = Path(image_path).name
            await self._send_text(to_user_id, f"[图片上传失败: {filename}]", context_token)
            return

        # 发送图片消息
        client_id = f"suyuan-{uuid.uuid4().hex[:12]}"

        item_list = [
            {
                "type": ITEM_IMAGE,
                "image_item": {
                    "image_id": media_id
                }
            }
        ]

        weixin_msg = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
            "context_token": context_token
        }

        body = {
            "msg": weixin_msg,
            "base_info": BASE_INFO
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning("Failed to send image", errcode=errcode, errmsg=data.get("errmsg"))

    async def _send_video(
        self,
        to_user_id: str,
        video_path: str,
        context_token: str,
    ) -> None:
        """发送视频"""
        # 上传视频
        media_id = await self._upload_media(video_path, UPLOAD_MEDIA_VIDEO)
        if not media_id:
            logger.warning("Failed to upload video", path=video_path)
            filename = Path(video_path).name
            await self._send_text(to_user_id, f"[视频上传失败: {filename}]", context_token)
            return

        # 发送视频消息
        client_id = f"suyuan-{uuid.uuid4().hex[:12]}"

        item_list = [
            {
                "type": ITEM_VIDEO,
                "video_item": {
                    "video_id": media_id
                }
            }
        ]

        weixin_msg = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
            "context_token": context_token
        }

        body = {
            "msg": weixin_msg,
            "base_info": BASE_INFO
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning("Failed to send video", errcode=errcode, errmsg=data.get("errmsg"))

    async def _send_file(
        self,
        to_user_id: str,
        file_path: str,
        context_token: str,
    ) -> None:
        """发送文件"""
        # 上传文件
        media_id = await self._upload_media(file_path, UPLOAD_MEDIA_FILE)
        if not media_id:
            logger.warning("Failed to upload file", path=file_path)
            filename = Path(file_path).name
            await self._send_text(to_user_id, f"[文件上传失败: {filename}]", context_token)
            return

        # 发送文件消息
        client_id = f"suyuan-{uuid.uuid4().hex[:12]}"

        item_list = [
            {
                "type": ITEM_FILE,
                "file_item": {
                    "file_id": media_id
                }
            }
        ]

        weixin_msg = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
            "context_token": context_token
        }

        body = {
            "msg": weixin_msg,
            "base_info": BASE_INFO
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning("Failed to send file", errcode=errcode, errmsg=data.get("errmsg"))
