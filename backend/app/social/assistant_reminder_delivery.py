"""Reuse the existing inbox/channel implementation, with a fresh binding check."""

import asyncio


async def deliver_reminder(task, trigger, notification):
    from app.conversations.dependencies import get_conversation_catalog

    source = await get_conversation_catalog().find(trigger.grant_session_id)
    if not source or source.owner_user_id != task.owner_user_id:
        return "rejected"
    recipient = notification.recipient
    from app.social.web_assistant import web_assistant_recipient
    from app.conversations import ConversationSource

    if recipient.startswith("web:"):
        if source.source != ConversationSource.WEB or recipient != web_assistant_recipient(task.owner_user_id):
            return "rejected"
        from app.social.assistant_notifications import AssistantNotificationService
        from config.settings import settings

        service = AssistantNotificationService()
        payload = dict(
            message_id="followup:" + notification.message_id,
            project=settings.project_id, owner=task.owner_user_id,
            source_session_id=trigger.grant_session_id, recipient=recipient,
            content=notification.content, data={"task_id": task.task_id, "kind": "assistant_followup"},
        )
        transaction = getattr(notification, "_delivery_session", None)
        if transaction is not None:
            return await service.publish_web(transaction, **payload)
        message_id = await service.enqueue(**payload)
        return await service.deliver(message_id)
    if recipient.startswith("app:"):
        if recipient != task.owner_user_id:
            return "rejected"
        from app.social.broadcast_context import persist_broadcast_context
        from app.social.push_service import get_unified_push_service

        saved = await persist_broadcast_context(
            session_mapper=None,
            social_user_id=recipient,
            message=notification.content,
            media=getattr(notification, "media", []),
            metadata={
                "task_id": task.task_id,
                "event_id": notification.message_id,
                "kind": getattr(notification, "kind", "assistant_reminder"),
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
    # 对话社交渠道（个人微信/QQ）已退役：weixin: 收件人一律拒绝。
    return "rejected"
