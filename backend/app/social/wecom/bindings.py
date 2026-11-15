"""App 账号 ↔ 企业微信外部联系人（external_userid）绑定注册表。

与 PushDeviceStore 同款原子 JSON 模式（temp + os.replace + 进程级锁）。
一个 external_userid 标识一个微信用户：换绑到别的 App 账号时自动搬家，
防止推送跨账号泄漏。owner 记录该客户当前由哪个企微成员跟进——企业群发
任务的客户必须是发送成员自己的客户，投递时按 owner 分组。
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
BINDING_STATUS_UNBOUND = "unbound"


def normalize_account(account: str) -> str:
    """同时接受裸账号 id 与 ``app:android:<id>`` 身份形式。"""
    value = str(account or "").strip()
    if value.startswith("app:android:"):
        value = value.removeprefix("app:android:")
    return value.strip()


class WecomBindingStore:
    _lock = asyncio.Lock()

    def __init__(self, path: Path | None = None):
        self.path = path or (get_social_dir() / "wecom_bindings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("wecom_bindings_read_failed", path=str(self.path))
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict[str, dict[str, Any]]) -> None:
        temp = self.path.with_suffix(self.path.suffix + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    async def bind(
        self,
        account: str,
        external_userid: str,
        *,
        owner: str = "",
        name: str | None = None,
    ) -> dict[str, Any]:
        account = normalize_account(account)
        external_userid = str(external_userid or "").strip()
        now = int(time.time())
        async with self._lock:
            data = self._read()
            # 一个 external_userid 是一个人：被其他账号认领时搬家。
            for other, row in list(data.items()):
                if (
                    other != account
                    and isinstance(row, dict)
                    and row.get("external_userid") == external_userid
                ):
                    data.pop(other, None)
                    logger.info(
                        "wecom_binding_moved", previous=other, account=account
                    )
            row = data.get(account) if isinstance(data.get(account), dict) else {}
            row.update(
                {
                    "external_userid": external_userid,
                    "owner": owner or row.get("owner") or "",
                    "status": BINDING_STATUS_BOUND,
                    "bound_at": row.get("bound_at") or now,
                    "updated_at": now,
                }
            )
            if name:
                row["name"] = name
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

    async def mark_unbound(self, external_userid: str) -> str | None:
        """客户删除企微好友/成员删除跟进：标记对应账号为 unbound。"""
        external_userid = str(external_userid or "").strip()
        async with self._lock:
            data = self._read()
            for account, row in data.items():
                if (
                    isinstance(row, dict)
                    and row.get("external_userid") == external_userid
                ):
                    row["status"] = BINDING_STATUS_UNBOUND
                    row["updated_at"] = int(time.time())
                    data[account] = row
                    self._write(data)
                    return account
        return None

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
