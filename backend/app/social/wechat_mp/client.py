"""WeChat Official Account (MP) subscribe-message client.

The application deals only with app-account identities and openids; access
token management, template quirks and vendor error codes stay inside this
module, mirroring how push_service.py hides GeTui behind a provider-neutral
facade.

WeChat MP error codes treated as business outcomes (returned, not raised):
- 43101: user rejected or has no remaining subscription quota
- 43104: user has unfollowed the account
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

_MP_BASE_URL = "https://api.weixin.qq.com"

# Token-level error codes: the cached stable token expired or was invalidated.
_TOKEN_STALE_CODES = {"40001", "40014", "42001"}


class WechatMpError(RuntimeError):
    """Raised when a WeChat MP API call fails at the protocol level."""

    def __init__(self, code: Any, message: str):
        super().__init__(f"wechat_mp_error:{code}:{message}")
        self.code = code
        self.message = message


class WechatMpClient:
    """Thin async client for the MP stable-token / bizsend / qrcode APIs."""

    def __init__(self, *, client_factory=httpx.AsyncClient):
        self.client_factory = client_factory
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(settings.wechat_mp_enabled) and all(
            value.strip()
            for value in (settings.wechat_mp_app_id, settings.wechat_mp_app_secret)
        )

    def _timeout(self) -> httpx.Timeout:
        seconds = settings.wechat_mp_timeout_seconds
        return httpx.Timeout(seconds, connect=min(seconds, 10))

    async def _get_token(self, client: httpx.AsyncClient, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            if (
                not force_refresh
                and self._token
                and time.time() < self._token_expires_at
            ):
                return self._token
            response = await client.post(
                f"{_MP_BASE_URL}/cgi-bin/stable_token",
                json={
                    "grant_type": "client_credential",
                    "appid": settings.wechat_mp_app_id,
                    "secret": settings.wechat_mp_app_secret,
                    "force_refresh": bool(force_refresh),
                },
            )
            response.raise_for_status()
            data = response.json()
            token = str(data.get("access_token") or "").strip()
            if not token:
                raise WechatMpError(
                    data.get("errcode", -1),
                    str(data.get("errmsg") or "missing access_token"),
                )
            expires_in = int(data.get("expires_in") or 7200)
            self._token = token
            self._token_expires_at = time.time() + max(expires_in - 120, 60)
            return token

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """POST with the cached token, retrying once on stale-token codes."""
        token = await self._get_token(client)
        response = await client.post(
            f"{_MP_BASE_URL}{path}", params={"access_token": token}, json=payload
        )
        response.raise_for_status()
        data = response.json()
        if str(data.get("errcode")) in _TOKEN_STALE_CODES:
            token = await self._get_token(client, force_refresh=True)
            response = await client.post(
                f"{_MP_BASE_URL}{path}", params={"access_token": token}, json=payload
            )
            response.raise_for_status()
            data = response.json()
        return data

    def _raise_for_error(self, data: dict[str, Any]) -> None:
        code = str(data.get("errcode", "0"))
        if code not in ("0", ""):
            raise WechatMpError(code, str(data.get("errmsg") or ""))

    async def send_subscribe_batch(
        self,
        *,
        template_id: str,
        recipients: list[tuple[str, dict[str, str]]],
    ) -> list[dict[str, Any]]:
        """Send one subscribe notification per ``(openid, field values)``.

        Business rejections (43101 not-subscribed, 43104 unfollowed) come
        back as result rows so callers can aggregate per-recipient outcomes
        without exception plumbing; transport failures degrade to a single
        failed row for that recipient.
        """
        results: list[dict[str, Any]] = []
        async with self.client_factory(timeout=self._timeout()) as client:
            for openid, fields in recipients:
                payload = {
                    "touser": openid,
                    "template_id": template_id,
                    "data": {key: {"value": value} for key, value in fields.items()},
                }
                try:
                    data = await self._post_json(
                        client, "/cgi-bin/message/subscribe/bizsend", payload
                    )
                    results.append({"openid": openid, **data})
                except Exception as exc:
                    logger.warning(
                        "wechat_mp_bizsend_failed", openid=openid, error=str(exc)
                    )
                    results.append(
                        {"openid": openid, "errcode": -1, "errmsg": str(exc)}
                    )
        return results

    async def create_bind_qrcode(
        self, scene_str: str, *, expire_seconds: int = 2592000
    ) -> dict[str, Any]:
        """Create a temporary scene QR code used for account binding."""
        async with self.client_factory(timeout=self._timeout()) as client:
            data = await self._post_json(
                client,
                "/cgi-bin/qrcode/create",
                {
                    "expire_seconds": expire_seconds,
                    "action_name": "QR_STR_SCENE",
                    "action_info": {"scene": {"scene_str": scene_str}},
                },
            )
        self._raise_for_error(data)
        ticket = str(data.get("ticket") or "")
        return {
            "ticket": ticket,
            "expire_seconds": int(data.get("expire_seconds") or expire_seconds),
            "url": f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={quote(ticket, safe='')}",
        }

    async def send_text_message(self, openid: str, content: str) -> dict[str, Any]:
        """Custom-service text message; requires a 48h interaction window.

        Best-effort by design (welcome note after binding); callers log the
        outcome instead of failing the surrounding flow.
        """
        async with self.client_factory(timeout=self._timeout()) as client:
            data = await self._post_json(
                client,
                "/cgi-bin/message/custom/send",
                {
                    "touser": openid,
                    "msgtype": "text",
                    "text": {"content": content[:600]},
                },
            )
        return data


_client: WechatMpClient | None = None


def get_wechat_mp_client() -> WechatMpClient:
    global _client
    if _client is None:
        _client = WechatMpClient()
    return _client
