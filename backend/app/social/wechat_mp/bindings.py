"""App-account ↔ WeChat MP openid binding registry.

Same atomic-JSON pattern as PushDeviceStore: one file under the social
directory, temp write + os.replace, one asyncio lock per process.  An
openid identifies one human WeChat user; when the same openid binds to
another app account the binding moves, so subscribe notices cannot leak
across accounts.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import get_social_dir

logger = structlog.get_logger(__name__)

BINDING_STATUS_BOUND = "bound"
BINDING_STATUS_UNSUBSCRIBED = "unsubscribed"


def normalize_account(account: str) -> str:
    """Accept both bare app-account ids and ``app:android:<id>`` identities."""
    value = str(account or "").strip()
    if value.startswith("app:android:"):
        value = value.removeprefix("app:android:")
    return value.strip()


class WechatMpBindingStore:
    """JSON registry: app account → {openid, status, template states}."""

    _lock = asyncio.Lock()

    def __init__(self, path: Path | None = None):
        self.path = path or (get_social_dir() / "wechat_mp_bindings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("wechat_mp_bindings_read_failed", path=str(self.path))
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict[str, dict[str, Any]]) -> None:
        temp = self.path.with_suffix(self.path.suffix + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    async def bind(
        self,
        account: str,
        openid: str,
        *,
        nickname: str | None = None,
    ) -> dict[str, Any]:
        account = normalize_account(account)
        openid = str(openid or "").strip()
        now = int(time.time())
        async with self._lock:
            data = self._read()
            # One openid is one person: move the binding if it was claimed by
            # another account, mirroring the shared-CID rule in PushDeviceStore.
            for other, row in list(data.items()):
                if other != account and isinstance(row, dict) and row.get("openid") == openid:
                    data.pop(other, None)
                    logger.info(
                        "wechat_mp_binding_moved", previous=other, account=account
                    )
            row = data.get(account) if isinstance(data.get(account), dict) else {}
            row.update(
                {
                    "openid": openid,
                    # Re-following after unsubscribe restores delivery.
                    "status": BINDING_STATUS_BOUND,
                    "bound_at": row.get("bound_at") or now,
                    "updated_at": now,
                }
            )
            if nickname:
                row["nickname"] = nickname
            row.setdefault("templates", {})
            data[account] = row
            self._write(data)
            return dict(row)

    async def unbind(self, account: str) -> bool:
        account = normalize_account(account)
        async with self._lock:
            data = self._read()
            if account not in data:
                return False
            data.pop(account, None)
            self._write(data)
            return True

    async def mark_unsubscribed(self, openid: str) -> str | None:
        """Flag the account bound to ``openid`` as unfollowed; return account."""
        openid = str(openid or "").strip()
        async with self._lock:
            data = self._read()
            for account, row in data.items():
                if isinstance(row, dict) and row.get("openid") == openid:
                    row["status"] = BINDING_STATUS_UNSUBSCRIBED
                    row["updated_at"] = int(time.time())
                    data[account] = row
                    self._write(data)
                    return account
        return None

    async def record_template_state(
        self, openid: str, template_id: str, state: str
    ) -> None:
        openid = str(openid or "").strip()
        template_id = str(template_id or "").strip()
        state = str(state or "").strip().lower()
        if state not in ("accept", "reject"):
            return
        async with self._lock:
            data = self._read()
            for row in data.values():
                if not isinstance(row, dict) or row.get("openid") != openid:
                    continue
                templates = row.get("templates")
                if not isinstance(templates, dict):
                    templates = {}
                templates[template_id] = state
                row["templates"] = templates
                row["updated_at"] = int(time.time())
            self._write(data)

    async def get(self, account: str) -> dict[str, Any] | None:
        account = normalize_account(account)
        async with self._lock:
            row = self._read().get(account)
            return dict(row) if isinstance(row, dict) else None

    async def list_bindings(self) -> list[dict[str, Any]]:
        async with self._lock:
            data = self._read()
        return [
            {"account": account, **row}
            for account, row in sorted(data.items())
            if isinstance(row, dict)
        ]

    async def record_push(self, account: str) -> None:
        account = normalize_account(account)
        async with self._lock:
            data = self._read()
            row = data.get(account)
            if not isinstance(row, dict):
                return
            row["last_push_at"] = int(time.time())
            data[account] = row
            self._write(data)
