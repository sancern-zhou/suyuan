"""Scheduled-task visibility honors canonical identity and app account bindings."""

from types import SimpleNamespace

from app.api.scheduled_task_routes import (
    _can_access_task,
    _can_view_task,
    _is_scheduled_task_admin,
)
from app.auth.identity_matching import _app_accounts
from app.auth.models import CurrentUser


def _task(owner_user_id: str, *, broadcast=False, targets=(), workspace=False) -> SimpleNamespace:
    return SimpleNamespace(
        owner_user_id=owner_user_id,
        created_by=owner_user_id,
        broadcast_enabled=broadcast,
        target_user_ids=list(targets),
        workspace_entry=SimpleNamespace(enabled=workspace),
    )


def _user(user_id: str, *, admin: bool = False) -> CurrentUser:
    return CurrentUser(
        id=user_id, username=user_id, display_name=user_id, is_admin=admin
    )


def _configure_accounts(accounts_json: str, monkeypatch):
    monkeypatch.setattr(
        "app.auth.identity_matching.settings",
        type("S", (), {"app_accounts_json": accounts_json})(),
    )
    _app_accounts.cache_clear()


def test_app_account_binding_grants_access_in_both_directions(monkeypatch):
    _configure_accounts('{"周三成": {"bind_user_id": "2"}}', monkeypatch)
    try:
        web_user = _user("2")
        app_user = _user("app:android:周三成")

        assert _can_access_task(_task("app:android:周三成"), web_user)
        assert _can_access_task(_task("2"), app_user)
        assert not _can_access_task(_task("app:android:周三成"), _user("3"))
        assert not _can_access_task(_task("app:android:android_demo"), web_user)
    finally:
        _app_accounts.cache_clear()


def test_company_prefix_owner_matches_web_user(monkeypatch):
    _configure_accounts("{}", monkeypatch)
    try:
        assert _can_access_task(_task("company:2"), _user("2"))
    finally:
        _app_accounts.cache_clear()


def test_admin_and_system_super_admin_keep_full_access(monkeypatch):
    _configure_accounts("{}", monkeypatch)
    try:
        assert _is_scheduled_task_admin(_user("1"))
        assert _is_scheduled_task_admin(_user("anyone", admin=True))
        assert _can_access_task(_task("app:android:周三成"), _user("1"))
        assert _can_access_task(_task("someone-else"), _user("anyone", admin=True))
    finally:
        _app_accounts.cache_clear()


def test_broadcast_target_matches_bound_user(monkeypatch):
    _configure_accounts('{"周三成": {"bind_user_id": "2"}}', monkeypatch)
    try:
        shared = _task("1", broadcast=True, targets=["app:android:周三成"], workspace=True)
        assert _can_view_task(shared, _user("2"))

        targeted_other = _task("1", broadcast=True, targets=["3"], workspace=True)
        assert not _can_view_task(targeted_other, _user("2"))

        open_broadcast = _task("1", broadcast=True, targets=[], workspace=True)
        assert _can_view_task(open_broadcast, _user("2"))
    finally:
        _app_accounts.cache_clear()


def test_system_task_view_still_requires_workspace(monkeypatch):
    _configure_accounts("{}", monkeypatch)
    try:
        assert not _can_view_task(_task("system"), _user("2"))
        assert _can_view_task(_task("system", workspace=True), _user("2"))
        assert not _can_access_task(_task("system"), _user("2"))
    finally:
        _app_accounts.cache_clear()
