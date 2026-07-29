import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import social_account_routes
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.social.binding_schemas import SocialBindingRecord, WeixinScanTaskRecord
from app.social.binding_service import get_social_binding_service


class FakeChannel:
    def __init__(self, config, *, scanner_user_id="", bot_account=""):
        self.config = config
        self.display_name = config.name
        self._token = "token" if scanner_user_id else ""
        self._scanner_user_id = scanner_user_id
        self._bot_account = bot_account
        self._current_qr_code_path = None
        self._qr_code_ready = asyncio.Event()
        self._qr_code_ready.set()
        self._running = False

    @property
    def scanner_user_id(self):
        return self._scanner_user_id

    @property
    def bot_account(self):
        return self._bot_account or f"bot-{self.config.id}"

    @property
    def is_running(self):
        return self._running

    async def _init_qr_login(self):
        return "qr-1"

    async def start(self):
        return None

    async def stop(self):
        self._running = False


class FakeManager:
    def __init__(self):
        self.channels = {}
        self.agent_bridge = None

    def _create_weixin_channel(self, config):
        return FakeChannel(config)


class FakeBindings:
    def __init__(self):
        self.tasks = {}
        self.bindings = []

    async def create_scan_task(self, user):
        now = datetime.utcnow()
        task = WeixinScanTaskRecord(
            id=f"task-{user.id}", account_id=f"auto_{user.id}",
            owner_user_id=user.id, owner_username=user.username,
            owner_display_name=user.display_name, status="created",
            created_at=now, updated_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        self.tasks[task.id] = task
        return task

    async def require_scan_task(self, task_id, user):
        task = self.tasks.get(task_id)
        if task is None or (not user.is_admin and task.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="weixin_scan_not_found")
        return task

    async def active_for_account(self, account_id):
        return next((row for row in self.bindings if row.account_id == account_id and row.status == "active"), None)

    async def active_for_platform_user(self, user_id):
        return next((row for row in self.bindings if row.platform_user_id == user_id and row.status == "active"), None)

    async def list_visible(self, user):
        return self.bindings if user.is_admin else [row for row in self.bindings if row.platform_user_id == user.id]

    async def activate(self, *, task_id, user, account_id, ilink_user_id, bot_account):
        record = SocialBindingRecord(
            id=f"binding-{user.id}", platform_user_id=user.id,
            platform_username=user.username, platform_display_name=user.display_name,
            account_id=account_id, ilink_user_id=ilink_user_id,
            bot_account=bot_account, status="active", bound_at=datetime.utcnow(),
        )
        self.bindings.append(record)
        return record

    async def mark_scan_status(self, task_id, user, status):
        task = await self.require_scan_task(task_id, user)
        task = task.model_copy(update={"status": status})
        self.tasks[task_id] = task
        return task

    async def deactivate_account(self, account_id):
        return False


@pytest.fixture
def route_environment(monkeypatch):
    manager = FakeManager()
    bindings = FakeBindings()
    config = SimpleNamespace(weixin=SimpleNamespace(accounts=[]))
    social_account_routes.set_channel_manager_override(manager)
    monkeypatch.setattr(social_account_routes, "load_config", lambda: config)
    monkeypatch.setattr(social_account_routes, "save_config", lambda value: True)
    yield manager, bindings, config
    social_account_routes.set_channel_manager_override(None)


def _client(user, bindings):
    app = FastAPI()
    app.include_router(social_account_routes.router)
    app.dependency_overrides[require_current_user] = lambda: user
    app.dependency_overrides[get_social_binding_service] = lambda: bindings
    return TestClient(app)


def _user(user_id, username, *, admin=False):
    return CurrentUser(
        id=user_id, username=username, display_name=username.title(), is_admin=admin
    )


def test_auto_create_ignores_client_identity_and_uses_current_user(route_environment):
    _, bindings, _ = route_environment
    client = _client(_user("u1", "alice"), bindings)

    response = client.post(
        "/api/social/accounts/weixin/auto-create",
        json={"temp_id": "forged", "platform_user_id": "u2"},
    )

    assert response.status_code == 200
    assert response.json()["platform_user_id"] == "u1"
    assert response.json()["platform_username"] == "alice"
    assert response.json()["account_id"].startswith("auto_")
    assert response.json()["task_id"] == "task-u1"


def test_other_user_cannot_operate_scan_task(route_environment):
    _, bindings, _ = route_environment
    owner = _user("u1", "alice")
    task = asyncio.run(bindings.create_scan_task(owner))
    client = _client(_user("u2", "bob"), bindings)

    for method, path in (
        ("GET", f"/api/social/accounts/weixin/{task.id}/status"),
        ("GET", f"/api/social/accounts/weixin/{task.id}/qrcode"),
        ("POST", f"/api/social/accounts/weixin/{task.id}/refresh-qrcode"),
        ("POST", f"/api/social/accounts/weixin/{task.id}/finalize"),
        ("DELETE", f"/api/social/accounts/weixin/{task.id}"),
    ):
        assert client.request(method, path, json={}).status_code == 404


def test_account_list_is_owner_scoped_while_admin_sees_all(route_environment):
    manager, bindings, config = route_environment
    for user_id, username in (("u1", "alice"), ("u2", "bob")):
        account_id = f"a-{user_id}"
        account_config = SimpleNamespace(id=account_id, name=username, enabled=True)
        config.weixin.accounts.append(account_config)
        manager.channels[f"weixin:{account_id}"] = FakeChannel(account_config)
        bindings.bindings.append(SocialBindingRecord(
            id=f"b-{user_id}", platform_user_id=user_id,
            platform_username=username, platform_display_name=username.title(),
            account_id=account_id, ilink_user_id=f"wx-{user_id}",
            bot_account=f"bot-{user_id}", status="active", bound_at=datetime.utcnow(),
        ))

    ordinary = _client(_user("u1", "alice"), bindings).get("/api/social/accounts")
    admin = _client(_user("1", "ScGuanLy", admin=True), bindings).get("/api/social/accounts")

    assert {row["id"] for row in ordinary.json()} == {"a-u1"}
    assert {row["id"] for row in admin.json()} == {"a-u1", "a-u2"}


def test_finalize_uses_confirmed_scanner_identity(route_environment):
    manager, bindings, config = route_environment
    user = _user("u1", "alice")
    task = asyncio.run(bindings.create_scan_task(user))
    account_config = SimpleNamespace(
        id=task.account_id, name="temporary", enabled=True, token=""
    )
    config.weixin.accounts.append(account_config)
    manager.channels[f"weixin:{task.account_id}"] = FakeChannel(
        account_config, scanner_user_id="wx-u1", bot_account="bot-u1"
    )

    response = _client(user, bindings).post(
        f"/api/social/accounts/weixin/{task.id}/finalize", json={}
    )

    assert response.status_code == 200
    assert response.json()["platform_user_id"] == "u1"
    assert response.json()["ilink_user_id"] == "wx-u1"
    assert "token" not in response.json()


def test_expired_scan_cleans_temporary_channel_and_configuration(route_environment):
    manager, bindings, config = route_environment
    user = _user("u1", "alice")
    task = asyncio.run(bindings.create_scan_task(user)).model_copy(
        update={"expires_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    bindings.tasks[task.id] = task
    account_config = SimpleNamespace(id=task.account_id, name="temporary", enabled=True)
    config.weixin.accounts.append(account_config)
    manager.channels[f"weixin:{task.account_id}"] = FakeChannel(account_config)

    response = _client(user, bindings).get(
        f"/api/social/accounts/weixin/{task.id}/status"
    )

    assert response.status_code == 410
    assert f"weixin:{task.account_id}" not in manager.channels
    assert config.weixin.accounts == []
