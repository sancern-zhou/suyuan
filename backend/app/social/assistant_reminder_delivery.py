"""Reuse the existing inbox/channel implementation, with a fresh binding check."""

import asyncio


async def deliver_reminder(task, trigger, notification):
    from app.conversations.dependencies import get_conversation_catalog

    source = await get_conversation_catalog().find(trigger.grant_session_id)
    if not source or source.owner_user_id != task.owner_user_id:
        return "rejected"
    recipient = notification.recipient
    if recipient.startswith("app:"):
        if recipient != task.owner_user_id:
            return "rejected"
        from app.social.broadcast_context import persist_broadcast_context
        from app.social.push_service import get_unified_push_service

        saved = await persist_broadcast_context(
            session_mapper=None,
            social_user_id=recipient,
            message=notification.content,
            media=[],
            metadata={
                "task_id": task.task_id,
                "event_id": notification.message_id,
                "kind": "assistant_reminder",
            },
        )
        if not saved:
            return "unknown"
        # Durable inbox success must not be obscured by a best-effort push failure.
        try:
            async with asyncio.timeout(5):
                await get_unified_push_service().send_broadcast(
                    social_user_id=recipient, message=notification.content
                )
        except Exception:
            pass
        return "inbox_saved"
    from app.social.binding_service import get_social_binding_service

    parts = recipient.rsplit(":", 2)
    if len(parts) != 3 or not (parts[0] == "weixin" or parts[0].startswith("weixin:")):
        return "rejected"
    binding = await get_social_binding_service().active_for_platform_user(task.owner_user_id)
    if not binding or binding.bot_account != parts[1] or binding.ilink_user_id != parts[2]:
        return "rejected"
    from app.social.broadcast_service import SocialBroadcastService

    result = await SocialBroadcastService().broadcast(
        message=notification.content,
        target_user_ids=[recipient],
        persist_context=True,
        delivery_metadata={"_single_attempt": True, "_expected_bot_account": parts[1]},
        context_metadata={
            "task_id": task.task_id,
            "event_id": notification.message_id,
            "kind": "assistant_reminder",
        },
    )
    results = result.get("delivery_results", [])
    if (
        len(results) == 1
        and results[0].get("social_user_id") == recipient
        and results[0].get("sent")
    ):
        return "provider_accepted"
    return "unknown"
