"""Resolve task ownership from the server's conversation catalog, never model input."""

from app.auth.models import CurrentUser


async def resolve_task_user(context) -> CurrentUser:
    from app.conversations.dependencies import get_conversation_catalog

    session_id = getattr(context, "session_id", None)
    if not session_id:
        raise ValueError("无法确认当前登录用户，未操作定时任务")
    record = await get_conversation_catalog().find(str(session_id))
    if not record or not record.owner_user_id or record.owner_user_id == "system":
        raise ValueError("无法确认当前登录用户，未操作定时任务")
    return CurrentUser(
        id=record.owner_user_id,
        username=record.owner_username or record.owner_user_id,
        display_name=record.owner_display_name or record.owner_username or record.owner_user_id,
    )
