"""Provider-neutral mobile push registration and delivery.

The rest of the application stores only a social identity and a provider
device identifier.  GeTui is an implementation detail of this module; it can
be replaced later without changing broadcast or App gateway contracts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.utils.path_config import get_social_dir
from config.settings import settings

logger = structlog.get_logger(__name__)


class PushDeviceStore:
    """Small atomic JSON registry used by the existing file-backed social data."""

    _lock = asyncio.Lock()

    def __init__(self, path: Path | None = None):
        self.path = path or (get_social_dir() / "push_devices.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("push_device_registry_read_failed", path=str(self.path))
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict[str, list[dict[str, Any]]]) -> None:
        temp = self.path.with_suffix(self.path.suffix + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    async def upsert(
        self,
        social_user_id: str,
        *,
        provider: str,
        device_id: str,
        platform: str = "android",
        app_id: str | None = None,
    ) -> dict[str, Any]:
        now = int(time.time())
        async with self._lock:
            data = self._read()
            # A CID identifies one app installation, not a person.  When a
            # shared device signs into another account, move the CID to the
            # new owner so broadcasts cannot leak across accounts.
            for owner, owner_devices in list(data.items()):
                if owner == social_user_id or not isinstance(owner_devices, list):
                    continue
                remaining = [
                    item
                    for item in owner_devices
                    if not (
                        isinstance(item, dict)
                        and item.get("provider") == provider
                        and item.get("device_id") == device_id
                    )
                ]
                if remaining:
                    data[owner] = remaining
                else:
                    data.pop(owner, None)
            devices = [item for item in data.get(social_user_id, []) if isinstance(item, dict)]
            row = next((item for item in devices if item.get("provider") == provider and item.get("device_id") == device_id), None)
            if row is None:
                row = {"provider": provider, "device_id": device_id}
                devices.append(row)
            row.update({"platform": platform, "app_id": app_id or "", "enabled": True, "updated_at": now})
            data[social_user_id] = devices
            self._write(data)
            return dict(row)

    async def remove(self, social_user_id: str, device_id: str, provider: str | None = None) -> bool:
        async with self._lock:
            data = self._read()
            old = data.get(social_user_id, [])
            new = [
                item for item in old
                if not (
                    isinstance(item, dict)
                    and item.get("device_id") == device_id
                    and (provider is None or item.get("provider") == provider)
                )
            ]
            if len(new) == len(old):
                return False
            if new:
                data[social_user_id] = new
            else:
                data.pop(social_user_id, None)
            self._write(data)
            return True

    async def list_active(self, social_user_id: str, provider: str) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                dict(item)
                for item in self._read().get(social_user_id, [])
                if isinstance(item, dict)
                and item.get("provider") == provider
                and item.get("enabled", True)
                and str(item.get("device_id") or "").strip()
            ]


class UnifiedPushService:
    """Unified push facade; currently backed by GeTui REST API V2."""

    def __init__(self, *, device_store: PushDeviceStore | None = None, client_factory=httpx.AsyncClient):
        self.device_store = device_store or PushDeviceStore()
        self.client_factory = client_factory
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def provider(self) -> str:
        return settings.push_provider.strip().lower()

    @property
    def enabled(self) -> bool:
        return self.provider == "getui" and all(
            value.strip() for value in (
                settings.push_getui_app_id,
                settings.push_getui_app_key,
                settings.push_getui_master_secret,
            )
        )

    def status(self) -> dict[str, Any]:
        return {"provider": self.provider, "enabled": self.enabled}

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        async with self._token_lock:
            if self._token and time.time() < self._token_expires_at - 30:
                return self._token
            timestamp = str(int(time.time() * 1000))
            sign = hashlib.sha256(
                f"{settings.push_getui_app_key}{timestamp}{settings.push_getui_master_secret}".encode()
            ).hexdigest()
            response = await client.post(
                f"{settings.push_getui_base_url.rstrip('/')}/{settings.push_getui_app_id}/auth",
                json={"sign": sign, "timestamp": timestamp, "appkey": settings.push_getui_app_key},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (0, "0"):
                raise RuntimeError(f"push_auth_failed:{payload.get('code')}:{payload.get('msg', '')}")
            data = payload.get("data") or {}
            token = str(data.get("token") or "").strip()
            if not token:
                raise RuntimeError("push_auth_missing_token")
            expire_time = float(data.get("expire_time") or 0)
            # GeTui returns an absolute millisecond expiry in current REST V2.
            self._token_expires_at = expire_time / 1000 if expire_time > 10_000_000_000 else time.time() + max(expire_time, 3600)
            self._token = token
            return token

    async def _push_cid(self, client: httpx.AsyncClient, cid: str, title: str, body: str) -> dict[str, Any]:
        token = await self._get_token(client)
        payload = {
            "request_id": uuid.uuid4().hex,
            "settings": {"ttl": settings.push_offline_ttl_ms},
            "audience": {"cid": [cid]},
            "push_message": {
                "notification": {
                    "title": title[:50],
                    "body": body[:256],
                    "click_type": "startapp",
                }
            },
        }
        response = await client.post(
            f"{settings.push_getui_base_url.rstrip('/')}/{settings.push_getui_app_id}/push/single/cid",
            headers={"token": token},
            json=payload,
        )
        if response.status_code == 401:
            self._token = None
            self._token_expires_at = 0
            token = await self._get_token(client)
            response = await client.post(
                f"{settings.push_getui_base_url.rstrip('/')}/{settings.push_getui_app_id}/push/single/cid",
                headers={"token": token},
                json=payload,
            )
        response.raise_for_status()
        result = response.json()
        # REST V2 can report an expired token as code 10001 with HTTP 200.
        if str(result.get("code")) == "10001":
            self._token = None
            self._token_expires_at = 0
            token = await self._get_token(client)
            response = await client.post(
                f"{settings.push_getui_base_url.rstrip('/')}/{settings.push_getui_app_id}/push/single/cid",
                headers={"token": token},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        if result.get("code") not in (0, "0"):
            raise RuntimeError(f"push_send_failed:{result.get('code')}:{result.get('msg', '')}")
        return result

    async def send_broadcast(self, *, social_user_id: str, message: str) -> dict[str, Any]:
        if not self.enabled or not social_user_id.startswith("app:"):
            return {"enabled": False, "sent": 0, "failed": 0}
        devices = await self.device_store.list_active(social_user_id, self.provider)
        if not devices:
            return {"enabled": True, "sent": 0, "failed": 0, "error": "no_registered_device"}
        sent = failed = 0
        errors: list[str] = []
        timeout = httpx.Timeout(settings.push_timeout_seconds, connect=min(settings.push_timeout_seconds, 10))
        async with self.client_factory(timeout=timeout) as client:
            for device in devices:
                try:
                    await self._push_cid(client, str(device["device_id"]), "溯源 Agent", message)
                    sent += 1
                except Exception as exc:
                    failed += 1
                    errors.append(str(exc))
                    logger.warning("unified_push_failed", provider=self.provider, social_user_id=social_user_id, error=str(exc))
        result: dict[str, Any] = {"enabled": True, "sent": sent, "failed": failed}
        if errors:
            result["errors"] = errors[:3]
        return result


_service: UnifiedPushService | None = None


def get_unified_push_service() -> UnifiedPushService:
    global _service
    if _service is None:
        _service = UnifiedPushService()
    return _service
