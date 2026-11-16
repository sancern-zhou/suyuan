"""Resolve configured administrators and deliver event task output."""

from __future__ import annotations

from typing import Any

from app.social.app_identity import _accounts
from app.social.broadcast_service import SocialBroadcastService

from .event_output import EventTaskOutput
from .models import ScheduledTask, TaskEvent, TaskExecution


class EventTaskDelivery:
    """Event task broadcast delivery.  Chat channels (personal WeChat / QQ)
    are retired; App identities are the only supported recipients."""

    def __init__(self, broadcast_service=None):
        self.broadcast_service = broadcast_service or SocialBroadcastService()

    async def resolve_recipients(
        self,
        target_user_ids: list[str],
    ) -> list[dict[str, str]]:
        recipients: list[dict[str, str]] = []
        for user_id in target_user_ids:
            if str(user_id).startswith("app-account-"):
                account_id = str(user_id).removeprefix("app-account-")
                account = _accounts().get(account_id)
                if account and str(account.get("status", "active")).lower() == "active":
                    user_id = f"app:android:{account_id}"
            # App identities can be targeted directly without a legacy
            # social-user registry row.
            if str(user_id).startswith("app:"):
                recipients.append({
                    "user_id": user_id,
                    "social_user_id": user_id,
                    "name": user_id.rsplit(":", 1)[-1],
                })
        return recipients

    async def deliver(
        self,
        *,
        task: ScheduledTask,
        event: TaskEvent | None,
        execution: TaskExecution,
        output: EventTaskOutput,
        recipients: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not output.broadcast:
            return []

        social_to_user = {
            recipient["social_user_id"]: recipient["user_id"]
            for recipient in recipients
        }
        result = await self.broadcast_service.broadcast(
            message=output.broadcast.message,
            media=output.broadcast.media,
            channels=["app"],
            target_user_ids=list(social_to_user),
            persist_context=True,
            context_metadata={
                "task_id": task.task_id,
                "execution_id": execution.execution_id,
                "event_id": event.event_id if event else None,
                "event_type": event.event_type if event else None,
            },
        )
        return [
            {
                "user_id": social_to_user.get(row.get("social_user_id")),
                **row,
            }
            for row in result.get("delivery_results", [])
        ]
