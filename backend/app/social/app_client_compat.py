"""Temporary request compatibility for App clients predating shared SQL chats.

Remove with the header/mapping hooks after all supported clients send protocol 2.
This module never imports or claims pre-upgrade channel conversations.
"""

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.auth.identity_matching import owner_matches
from app.conversations.models import ConversationCatalogDB
from app.db.models_session import SessionDB, SessionMessageDB


def is_legacy_app(request):
    headers = getattr(request, "headers", None)
    return headers is not None and headers.get("X-App-Conversation-Version") != "2"


async def bind_draft_mode(identity, session_id, mode):
    """An old create request omits mode; bind once at the first actual turn."""
    from app.db.session_database import session_async_session

    async with session_async_session() as db:
        await db.execute(update(SessionDB).where(SessionDB.session_id == session_id).values(
            updated_at=SessionDB.updated_at
        ))
        session = (await db.execute(select(SessionDB).where(
            SessionDB.session_id == session_id
        ).with_for_update())).scalar_one_or_none()
        row = (await db.execute(select(ConversationCatalogDB).where(
            ConversationCatalogDB.session_id == session_id
        ).with_for_update())).scalar_one_or_none()
        if row is None or row.source != "web" or row.read_only_on_web or not owner_matches(row.owner_user_id, identity.social_user_id):
            raise HTTPException(404, "session_not_found")
        if row.mode:
            if row.mode != mode:
                raise HTTPException(409, "session_mode_conflict")
            return
        metadata = dict(session.session_metadata or {}) if session else {}
        count = await db.scalar(select(func.count()).select_from(SessionMessageDB).where(
            SessionMessageDB.session_id == session_id
        ))
        if not session or not metadata.pop("app_legacy_mode_pending", False) or count:
            raise HTTPException(409, "session_mode_conflict")
        metadata["mode"] = mode
        session.session_metadata = metadata
        session.mode = row.mode = mode
        await db.commit()


async def copy_upload_resources(identity, target, uploaded_files, catalog, resource_service):
    """Old uploads omit session_id; authorize and copy refs when the turn selects it."""
    from app.agent.resources.contracts import ResourceDeclaration

    sources = {row.session_id for row in uploaded_files if row.session_id != target}
    pages = {}
    # Authorize the whole batch before publishing any resources.
    for source in sources:
        owner = await catalog.find(source) if source else None
        if owner is None or owner.source != "web" or owner.read_only_on_web or not owner_matches(owner.owner_user_id, identity.social_user_id):
            raise HTTPException(404, "attachment_not_found")
        pages[source] = await resource_service.list_resources(source, status="active", limit=1000)
    if not sources:
        return
    target_page = await resource_service.list_resources(target, status="active", limit=1000)
    existing = {item.metadata.get("file_id") for item in target_page.resources if item.relation == "primary"}
    publications = []
    for row in uploaded_files:
        if row.session_id == target or row.id in existing:
            continue
        resources = pages[row.session_id].resources
        primary = next((item for item in resources if item.relation == "primary"
                        and item.role == "attachment" and item.metadata.get("file_id") == row.id), None)
        if primary is None:
            raise HTTPException(404, "attachment_not_found")
        group = [item for item in resources if item.group_id == primary.group_id and item.version == primary.version]
        keys = {item.resource_id: item.resource_key for item in group}
        group_key = f"upload:{row.id}"
        declarations = [ResourceDeclaration(
            **{key: getattr(item, key) for key in (
                "kind", "resource_key", "relation", "role", "label", "locator", "format",
                "media_type", "renderer", "capabilities", "metadata", "status", "tool_name"
            )}, group_key=group_key, parent_key=keys.get(item.parent_resource_id),
        ) for item in group]
        publications.append((group_key, declarations))
    for group_key, declarations in publications:
        await resource_service.publish_group(target, group_key, group_key, declarations)
