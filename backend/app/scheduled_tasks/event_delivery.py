"""Resolve configured administrators and deliver event task output."""

from __future__ import annotations

from typing import Any

from app.social.broadcast_service import SocialBroadcastService
from app.social.user_registry import get_social_user_registry

from .event_output import EventTaskOutput
from .models import ScheduledTask, TaskEvent, TaskExecution


class EventTaskDelivery:
    def __init__(self, user_registry=None, broadcast_service=None):
        self.user_registry = user_registry or get_social_user_registry()
        self.broadcast_service = broadcast_service or SocialBroadcastService()

    async def resolve_recipients(
        self,
        target_user_ids: list[str],
    ) -> list[dict[str, str]]:
        recipients: list[dict[str, str]] = []
        for user_id in target_user_ids:
            record = await self.user_registry.get_user(user_id)
            if not record or record.status != "active" or not record.social_user_id:
                continue
            channel = str(record.channel or "")
            if not channel.startswith(("weixin", "app")):
                continue
            recipients.append({
                "user_id": user_id,
                "social_user_id": record.social_user_id,
                "name": record.name,
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
        channels = sorted({
            "app" if str(recipient.get("social_user_id", "")).startswith("app:") else "weixin"
            for recipient in recipients
        })
        result = await self.broadcast_service.broadcast(
            message=output.broadcast.message,
            media=output.broadcast.media,
            channels=channels,
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
