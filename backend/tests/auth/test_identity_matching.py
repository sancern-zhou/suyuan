from app.auth.identity_matching import (
    _app_accounts,
    canonical_user_ids,
    owner_matches,
    visible_owner_ids,
)


def test_web_user_matches_company_prefixed_owner():
    assert canonical_user_ids("u1") == ("u1", "company:u1")
    assert owner_matches("company:u1", "u1")
    assert owner_matches("u1", "u1")


def test_company_login_matches_web_owned_records():
    assert canonical_user_ids("company:u1") == ("company:u1", "u1")
    assert owner_matches("u1", "company:u1")


def test_app_device_account_never_merges():
    assert canonical_user_ids("app:android:demo") == ("app:android:demo",)
    assert not owner_matches("u1", "app:android:demo")
    assert not owner_matches("company:demo", "app:android:demo")
    assert not owner_matches("app:android:demo", "demo")


def test_blank_and_edge_inputs_fail_closed():
    assert canonical_user_ids("") == ()
    assert not owner_matches(None, "u1")
    assert not owner_matches("", "u1")
    assert canonical_user_ids("company:") == ("company:",)
    assert not owner_matches("company:", "")


def test_bound_app_account_sees_company_user_records(monkeypatch):
    monkeypatch.setattr(
        "app.auth.identity_matching.settings",
        type("S", (), {"app_accounts_json": '{"周三成": {"bind_user_id": "2"}}'})(),
    )
    _app_accounts.cache_clear()
    try:
        assert owner_matches("2", "app:android:周三成")
        assert "app:android:周三成" in visible_owner_ids("2")
        assert not owner_matches("2", "app:android:android_demo")
    finally:
        _app_accounts.cache_clear()


def test_unbound_company_user_stays_isolated(monkeypatch):
    monkeypatch.setattr(
        "app.auth.identity_matching.settings",
        type("S", (), {"app_accounts_json": '{"android_demo": {}}'})(),
    )
    _app_accounts.cache_clear()
    try:
        assert visible_owner_ids("app:android:android_demo") == ("app:android:android_demo",)
        assert not owner_matches("app:android:android_demo", "2")
    finally:
        _app_accounts.cache_clear()
