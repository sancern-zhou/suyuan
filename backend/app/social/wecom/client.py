"""企业微信客户联系 HTTP 客户端。

调用方只处理 App 账号身份与 external_userid；access_token 管理、成员/
客户校验、错误码语义都收敛在本模块（与 push_service.py 隐藏 GeTui 同一
思路）。

关键接口：
- gettoken → access_token（缓存 + 40014/42001 强刷）
- add_contact_way → 带 state 的「联系我」二维码（用户微信扫码加好友即绑定）
- add_msg_template → 企业群发任务（chat_type=single 点对点；任务创建后
  需运营成员在企业微信客户端手动点「发送」，客户才能收到——这是平台
  设计，API 无法代替）
- remind_group_msg_send → 提醒未发送的成员
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

_QYAPI_BASE_URL = "https://qyapi.weixin.qq.com"

# Token-level error codes: cached token expired or invalidated.
_TOKEN_STALE_CODES = {"40014", "42001"}


class WecomError(RuntimeError):
    """Raised when a WeCom API call fails at the protocol level."""

    def __init__(self, code: Any, message: str):
        super().__init__(f"wecom_error:{code}:{message}")
        self.code = code
        self.message = message


class WecomClient:
    def __init__(self, *, client_factory=httpx.AsyncClient):
        self.client_factory = client_factory
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(settings.wecom_enabled) and all(
            value.strip()
            for value in (
                settings.wecom_corpid,
                settings.wecom_contact_secret,
                settings.wecom_default_member,
            )
        )

    def _timeout(self) -> httpx.Timeout:
        seconds = settings.wecom_timeout_seconds
        return httpx.Timeout(seconds, connect=min(seconds, 10))

    async def _get_token(self, client: httpx.AsyncClient, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            if (
                not force_refresh
                and self._token
                and time.time() < self._token_expires_at
            ):
                return self._token
            response = await client.get(
                f"{_QYAPI_BASE_URL}/cgi-bin/gettoken",
                params={
                    "corpid": settings.wecom_corpid,
                    "corpsecret": settings.wecom_contact_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            token = str(data.get("access_token") or "").strip()
            if not token:
                raise WecomError(
                    data.get("errcode", -1),
                    str(data.get("errmsg") or "missing access_token"),
                )
            expires_in = int(data.get("expires_in") or 7200)
            self._token = token
            self._token_expires_at = time.time() + max(expires_in - 120, 60)
            return token

    async def _post_json(
        self, client: httpx.AsyncClient, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        token = await self._get_token(client)
        response = await client.post(
            f"{_QYAPI_BASE_URL}{path}", params={"access_token": token}, json=payload
        )
        response.raise_for_status()
        data = response.json()
        if str(data.get("errcode")) in _TOKEN_STALE_CODES:
            token = await self._get_token(client, force_refresh=True)
            response = await client.post(
                f"{_QYAPI_BASE_URL}{path}", params={"access_token": token}, json=payload
            )
            response.raise_for_status()
            data = response.json()
        return data

    def _raise_for_error(self, data: dict[str, Any]) -> None:
        code = str(data.get("errcode", "0"))
        if code not in ("0", ""):
            raise WecomError(code, str(data.get("errmsg") or ""))

    async def create_bind_qrcode(
        self,
        state: str,
        *,
        members: list[str] | None = None,
        expire_days: int = 30,
    ) -> dict[str, Any]:
        """创建带 state 的「联系我」二维码（用户微信扫码加企微成员好友）。

        企微没有临时二维码过期语义（联系我方式长期有效），expire_days
        仅用于 remark 标注有效期，便于运营侧定期轮换。
        """
        payload = {
            "type": 1,  # 1 = 二维码
            "scene": 2,  # 2 = 网页
            "state": state,
            "user": members or [settings.wecom_default_member],
            "remark": f"suyuan bind (valid {expire_days}d)",
            "skip_verify": True,
        }
        async with self.client_factory(timeout=self._timeout()) as client:
            data = await self._post_json(
                client, "/cgi-bin/externalcontact/add_contact_way", payload
            )
        self._raise_for_error(data)
        return {
            "qr_code": str(data.get("qr_code") or ""),
            "state": state,
            "members": payload["user"],
        }

    async def add_group_msg_task(
        self,
        *,
        sender: str,
        external_userids: list[str],
        content: str,
    ) -> dict[str, Any]:
        """创建点对点企业群发任务（待运营成员在企微客户端确认发送）。

        external_userids 必须全部是 sender 的客户；内容 text 上限 2048
        字节（UTF-8），超限由调用方截断。
        """
        payload = {
            "chat_type": "single",
            "external_userid": external_userids,
            "sender": sender,
            "text": {"content": content},
        }
        async with self.client_factory(timeout=self._timeout()) as client:
            data = await self._post_json(
                client, "/cgi-bin/externalcontact/add_msg_template", payload
            )
        self._raise_for_error(data)
        return {"msgid": str(data.get("msgid") or ""), "sender": sender}

    async def remind_group_msg_send(self, msgid: str) -> dict[str, Any]:
        """提醒未发送的成员处理群发任务（best-effort）。"""
        async with self.client_factory(timeout=self._timeout()) as client:
            data = await self._post_json(
                client,
                "/cgi-bin/externalcontact/remind_group_msg_send",
                {"msgid": msgid},
            )
        return data


_client: WecomClient | None = None


def get_wecom_client() -> WecomClient:
    global _client
    if _client is None:
        _client = WecomClient()
    return _client
