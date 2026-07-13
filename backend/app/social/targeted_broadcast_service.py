"""Safely broadcast to explicitly named, uniquely matched social users."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.social.broadcast_service import SocialBroadcastService
from app.social.user_registry import get_social_user_registry


class TargetedSocialBroadcastService:
    """Resolve exact user names and fan out through the live social broadcaster."""

    def __init__(self, user_registry=None, broadcast_service=None):
        self.user_registry = user_registry or get_social_user_registry()
        self.broadcast_service = broadcast_service or SocialBroadcastService()

    async def broadcast(
        self,
        *,
        message: str,
        target_user_names: list[str],
        media: list[str] | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        names = list(dict.fromkeys(
            name.strip() for name in (target_user_names or []) if name.strip()
        ))
        if not names:
            return self._result([], [], "必须指定目标用户名称")
        if not (message or "").strip():
            return self._result([], names, "缺少广播内容")

        users_by_name: dict[str, list[Any]] = defaultdict(list)
        for user in await self.user_registry.list_users():
            users_by_name[str(user.name)].append(user)

        valid: list[tuple[str, Any]] = []
        rows_by_name: dict[str, dict[str, Any]] = {}
        for name in names:
            matches = users_by_name.get(name, [])
            if not matches:
                rows_by_name[name] = self._failed_row(name, "user not found")
                continue
            if len(matches) != 1:
                rows_by_name[name] = self._failed_row(name, "duplicate user name")
                continue

            user = matches[0]
            if user.status != "active":
                rows_by_name[name] = self._failed_row(
                    name,
                    "user is not active",
                    user_id=user.id,
                )
                continue
            if not user.social_user_id:
                rows_by_name[name] = self._failed_row(
                    name,
                    "user is not bound",
                    user_id=user.id,
                )
                continue
            if not str(user.channel or "").startswith("weixin"):
                rows_by_name[name] = self._failed_row(
                    name,
                    "user is not bound to WeChat",
                    user_id=user.id,
                )
                continue
            valid.append((name, user))

        users_by_social_id: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for name, user in valid:
            users_by_social_id[user.social_user_id].append((name, user))
        valid = []
        for bindings in users_by_social_id.values():
            if len(bindings) == 1:
                valid.append(bindings[0])
                continue
            for name, user in bindings:
                rows_by_name[name] = self._failed_row(
                    name,
                    "duplicate social binding",
                    user_id=user.id,
                    social_user_id=user.social_user_id,
                )

        broadcast_result: dict[str, Any] = {}
        if valid:
            broadcast_result = await self.broadcast_service.broadcast(
                message=message,
                media=media or [],
                channels=["weixin"],
                target_user_ids=[user.social_user_id for _, user in valid],
                persist_context=True,
                context_metadata=context_metadata or {},
            )
            identity_by_social_id = {
                user.social_user_id: (name, user.id)
                for name, user in valid
            }
            delivered_social_ids: set[str] = set()
            for row in broadcast_result.get("delivery_results", []):
                social_user_id = row.get("social_user_id")
                identity = identity_by_social_id.get(social_user_id)
                if not identity:
                    continue
                name, user_id = identity
                delivered_social_ids.add(social_user_id)
                rows_by_name[name] = {
                    "user_name": name,
                    "user_id": user_id,
                    **row,
                }

            for name, user in valid:
                if user.social_user_id not in delivered_social_ids:
                    rows_by_name[name] = self._failed_row(
                        name,
                        "delivery returned no result",
                        user_id=user.id,
                        social_user_id=user.social_user_id,
                    )

        delivery_results = [rows_by_name[name] for name in names]
        failed_names = [
            row["user_name"]
            for row in delivery_results
            if not (
                row.get("sent") and row.get("context_persisted") is True
            )
        ]
        completed_count = sum(
            bool(row.get("sent") and row.get("context_persisted") is True)
            for row in delivery_results
        )
        success = completed_count > 0
        summary = f"已发送并持久化给 {completed_count} 个目标用户"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        return {
            "status": "success" if success else "failed",
            "success": success,
            "channels_sent": broadcast_result.get("channels_sent", []),
            "failed_user_names": failed_names,
            "delivery_results": delivery_results,
            "media_sent": broadcast_result.get("media_sent", 0),
            "summary": summary,
        }

    @staticmethod
    def _failed_row(
        user_name: str,
        error: str,
        *,
        user_id: str | None = None,
        social_user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "user_name": user_name,
            "user_id": user_id,
            "social_user_id": social_user_id,
            "sent": False,
            "context_persisted": False,
            "error": error,
        }

    @staticmethod
    def _result(
        delivery_results: list[dict[str, Any]],
        failed_names: list[str],
        summary: str,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "channels_sent": [],
            "failed_user_names": failed_names,
            "delivery_results": delivery_results,
            "media_sent": 0,
            "summary": summary,
        }
