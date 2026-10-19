"""App 会话懒注册行为测试。

背景：App 端“新建对话”“从广播消息退出”都会调用 POST /api/social/app/sessions。
旧实现立即把会话注册进 conversation_catalog，用户没有发送任何消息也会在
历史列表留下空会话（生产库曾积累 14 条 msg_count=0 的无标题 social 会话）。
修复后目录注册延迟到首条消息（_ensure_session 兜底懒注册）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import social_app_routes
from app.auth import identity_matching
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource
from app.conversations.service import ConversationCatalogService
from app.social.app_identity import AppIdentity


def _identity(caller="app:android:alice"):
    return AppIdentity(caller, "Caller", caller, 9999999999)


LEGIT_SESSION_ID = "assistant_session_1791910261228_a9985d22e841"


def _catalog_with(row):
    store = {"row": row}

    async def get(session_id):
        return store["row"]

    async def upsert(record):
        store["row"] = record
        return record

    repository = SimpleNamespace(get=AsyncMock(side_effect=get), upsert=AsyncMock(side_effect=upsert))
    return ConversationCatalogService(repository), repository


def _mapper(current_session=None, or_create=None):
    return SimpleNamespace(
        get_session=AsyncMock(return_value=current_session),
        get_or_create_session=AsyncMock(return_value=or_create),
        save_mapping=AsyncMock(),
        new_session_id=lambda mode: "assistant_session_new",
    )


@pytest.mark.asyncio
async def test_create_app_session_does_not_register_catalog(monkeypatch):
    """新建对话只保存 mapper 映射，不得写会话目录。"""
    catalog, repository = _catalog_with(row=None)
    mapper = _mapper()
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(social_app_routes, "_loaded_session_mapper", AsyncMock(return_value=mapper))

    result = await social_app_routes.create_app_session(object(), _identity())

    assert result["session_id"] == "assistant_session_new"
    mapper.save_mapping.assert_awaited_once()
    repository.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_session_lazy_registers_app_session_id(monkeypatch):
    """格式合法的未注册 App 会话在续聊/恢复时补注册（懒注册兜底）。"""
    catalog, repository = _catalog_with(row=None)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(
        social_app_routes, "_loaded_session_mapper",
        AsyncMock(return_value=_mapper(current_session=LEGIT_SESSION_ID)),
    )

    session_id = await social_app_routes._ensure_session(object(), _identity(), LEGIT_SESSION_ID)

    assert session_id == LEGIT_SESSION_ID
    repository.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_session_rejects_unknown_session(monkeypatch):
    """非 App 会话格式的未知 session_id 必须拒绝。"""
    catalog, repository = _catalog_with(row=None)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(
        social_app_routes, "_loaded_session_mapper",
        AsyncMock(return_value=_mapper(current_session=LEGIT_SESSION_ID)),
    )

    with pytest.raises(HTTPException) as exc:
        await social_app_routes._ensure_session(object(), _identity(), "forged_session_id")
    assert exc.value.status_code == 404
    repository.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_session_skips_duplicate_registration(monkeypatch):
    """目录中已存在的会话不重复注册（避免所有权转移路径）。"""
    row = ConversationCatalogRecord(
        session_id="assistant_session_existing", owner_user_id="app:android:alice",
        owner_username="alice", owner_display_name="Alice",
        source=ConversationSource.SOCIAL, mode="assistant", title="已注册",
        read_only_on_web=True,
    )
    catalog, repository = _catalog_with(row=row)
    mapper = _mapper(or_create="assistant_session_existing")
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(social_app_routes, "_loaded_session_mapper", AsyncMock(return_value=mapper))

    session_id = await social_app_routes._ensure_session(object(), _identity(), None)

    assert session_id == "assistant_session_existing"
    repository.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_session_registers_new_or_create_result(monkeypatch):
    """get_or_create 产出新映射时注册（上传附件等隐式建会话路径）。"""
    catalog, repository = _catalog_with(row=None)
    mapper = _mapper(or_create="assistant_session_new")
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(social_app_routes, "_loaded_session_mapper", AsyncMock(return_value=mapper))

    session_id = await social_app_routes._ensure_session(object(), _identity(), None)

    assert session_id == "assistant_session_new"
    repository.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_readable_app_session_row_lazy_registers_new_conversation(monkeypatch):
    """App 点击未发过消息的新对话恢复历史时不再 404（懒注册兜底）。"""
    catalog, repository = _catalog_with(row=None)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(
        social_app_routes, "_loaded_session_mapper",
        AsyncMock(return_value=_mapper(current_session=LEGIT_SESSION_ID)),
    )
    identity = _identity()

    row = await social_app_routes._readable_app_session_row(
        object(), LEGIT_SESSION_ID, identity
    )

    assert row.session_id == LEGIT_SESSION_ID
    assert row.source == ConversationSource.SOCIAL
    repository.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_readable_app_session_row_still_404_for_non_app_session(monkeypatch):
    """非 App 会话格式的未知 session_id 恢复历史仍返回 404。"""
    catalog, repository = _catalog_with(row=None)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(
        social_app_routes, "_loaded_session_mapper",
        AsyncMock(return_value=_mapper(current_session=None)),
    )
    monkeypatch.setattr(
        social_app_routes, "_authorize_scheduled_session_row",
        AsyncMock(side_effect=HTTPException(status_code=404, detail="session_not_found")),
    )

    with pytest.raises(HTTPException) as exc:
        await social_app_routes._readable_app_session_row(
            object(), "forged_session_id", _identity()
        )
    assert exc.value.status_code == 404
    repository.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_app_session_list_hides_sessions_without_content(monkeypatch, tmp_path):
    """历史列表隐藏从未落盘的空会话（点击过的懒注册会话不回显）。"""
    live = ConversationCatalogRecord(
        session_id=LEGIT_SESSION_ID, owner_user_id="app:android:alice",
        owner_username="alice", owner_display_name="Alice",
        source=ConversationSource.SOCIAL, mode="assistant", title="你好",
        read_only_on_web=True,
    )
    empty = ConversationCatalogRecord(
        session_id="assistant_session_1791910276138_d4843e07b640",
        owner_user_id="app:android:alice",
        owner_username="alice", owner_display_name="Alice",
        source=ConversationSource.SOCIAL, mode="assistant", title="新对话",
        read_only_on_web=True,
    )
    web_row = ConversationCatalogRecord(
        session_id="web-1", owner_user_id="app:android:alice",
        owner_username="alice", owner_display_name="Alice",
        source=ConversationSource.WEB, mode="custom", title="定时任务",
        read_only_on_web=False,
    )
    catalog = SimpleNamespace(list_visible=AsyncMock(return_value=[live, empty, web_row]))
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(
        social_app_routes, "_loaded_session_mapper",
        AsyncMock(return_value=_mapper(current_session=LEGIT_SESSION_ID)),
    )
    (tmp_path / f"{LEGIT_SESSION_ID}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(social_app_routes, "get_sessions_dir", lambda: tmp_path)

    result = await social_app_routes.sessions(object(), _identity())

    assert [item["session_id"] for item in result] == [LEGIT_SESSION_ID]
