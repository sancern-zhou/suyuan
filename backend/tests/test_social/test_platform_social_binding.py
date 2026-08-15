from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.models import CurrentUser
from app.social.binding_schemas import SocialBindingRecord, WeixinScanTaskRecord
from app.social.binding_service import SocialBindingConflict, SocialBindingService
from app.social import binding_repository


class ForeignWeixinIdentityError(RuntimeError):
    pass


class FakeBindingRepository:
    def __init__(self):
        self.tasks = {}
        self.bindings = []

    async def create_scan_task(self, user):
        now = datetime.utcnow()
        task = WeixinScanTaskRecord(
            id=str(uuid4()),
            account_id=f"auto_{uuid4().hex}",
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            status="created",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        self.tasks[task.id] = task
        return task

    async def get_scan_task(self, task_id):
        return self.tasks.get(task_id)

    async def set_scan_status(self, task_id, status):
        task = self.tasks[task_id]
        updated = task.model_copy(update={"status": status, "updated_at": datetime.utcnow()})
        self.tasks[task_id] = updated
        return updated

    async def replace_active_binding(self, *, task, ilink_user_id, bot_account):
        foreign = next((
            row for row in self.bindings
            if row.status == "active"
            and row.ilink_user_id == ilink_user_id
            and row.platform_user_id != task.owner_user_id
        ), None)
        if foreign:
            from app.social.binding_repository import ForeignWeixinIdentityError
            raise ForeignWeixinIdentityError(ilink_user_id)

        self.bindings = [
            row.model_copy(update={"status": "replaced"})
            if row.status == "active" and row.platform_user_id == task.owner_user_id
            else row
            for row in self.bindings
        ]
        record = SocialBindingRecord(
            id=str(uuid4()),
            platform_user_id=task.owner_user_id,
            platform_username=task.owner_username,
            platform_display_name=task.owner_display_name,
            account_id=task.account_id,
            ilink_user_id=ilink_user_id,
            bot_account=bot_account,
            status="active",
            bound_at=datetime.utcnow(),
        )
        self.bindings.append(record)
        await self.set_scan_status(task.id, "confirmed")
        return record

    async def active_for_platform_user(self, user_id):
        return next((row for row in self.bindings if row.status == "active" and row.platform_user_id == user_id), None)

    async def resolve_sender(self, *, bot_account, ilink_user_id):
        return next((
            row for row in self.bindings
            if row.status == "active" and row.bot_account == bot_account and row.ilink_user_id == ilink_user_id
        ), None)


@pytest.mark.asyncio
async def test_new_wechat_binding_persists_full_channel_key(monkeypatch):
    task = WeixinScanTaskRecord(
        id="scan-1",
        account_id="auto_account_1",
        owner_user_id="u1",
        owner_username="alice",
        owner_display_name="Alice",
        status="confirmed",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    added = []

    class TransactionContext:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeSession:
        def __init__(self):
            self.scalar_results = [
                SimpleNamespace(account_id=task.account_id, status="confirmed"),
                None,
                None,
                None,
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def begin(self):
            return TransactionContext()

        async def scalar(self, _statement):
            return self.scalar_results.pop(0)

        def add(self, row):
            row.id = "binding-1"
            added.append(row)

        async def refresh(self, _row):
            return None

    monkeypatch.setattr(binding_repository, "async_session", FakeSession)

    await binding_repository.SocialBindingRepository().replace_active_binding(
        task=task,
        ilink_user_id="wx-user-1",
        bot_account="bot-1",
    )

    assert added[0].channel == "weixin:auto_account_1"
    assert (
        added[0].social_user_id
        == "weixin:auto_account_1:bot-1:wx-user-1"
    )


@pytest.mark.asyncio
async def test_same_platform_user_replaces_previous_wechat_binding():
    repository = FakeBindingRepository()
    service = SocialBindingService(repository)
    user = CurrentUser(id="u1", username="alice", display_name="Alice")
    first_task = await service.create_scan_task(user)
    second_task = await service.create_scan_task(user)

    first = await service.activate(
        task_id=first_task.id, user=user, account_id=first_task.account_id,
        ilink_user_id="wx-1", bot_account="bot-1",
    )
    second = await service.activate(
        task_id=second_task.id, user=user, account_id=second_task.account_id,
        ilink_user_id="wx-2", bot_account="bot-2",
    )

    assert first.id != second.id
    assert len([row for row in repository.bindings if row.status == "replaced"]) == 1
    assert await repository.active_for_platform_user("u1") == second


@pytest.mark.asyncio
async def test_wechat_identity_cannot_be_taken_from_another_platform_user():
    repository = FakeBindingRepository()
    service = SocialBindingService(repository)
    alice = CurrentUser(id="u1", username="alice", display_name="Alice")
    bob = CurrentUser(id="u2", username="bob", display_name="Bob")
    alice_task = await service.create_scan_task(alice)
    bob_task = await service.create_scan_task(bob)
    await service.activate(
        task_id=alice_task.id, user=alice, account_id=alice_task.account_id,
        ilink_user_id="wx-shared", bot_account="bot-1",
    )

    with pytest.raises(SocialBindingConflict):
        await service.activate(
            task_id=bob_task.id, user=bob, account_id=bob_task.account_id,
            ilink_user_id="wx-shared", bot_account="bot-2",
        )


@pytest.mark.asyncio
async def test_scan_task_is_visible_only_to_owner_or_admin():
    service = SocialBindingService(FakeBindingRepository())
    owner = CurrentUser(id="u1", username="alice", display_name="Alice")
    other = CurrentUser(id="u2", username="bob", display_name="Bob")
    admin = CurrentUser(id="1", username="ScGuanLy", display_name="超级管理员", is_admin=True)
    task = await service.create_scan_task(owner)

    assert await service.require_scan_task(task.id, owner) == task
    assert await service.require_scan_task(task.id, admin) == task
    with pytest.raises(HTTPException) as exc:
        await service.require_scan_task(task.id, other)
    assert exc.value.status_code == 404
