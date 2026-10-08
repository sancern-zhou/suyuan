from app.auth.identity_matching import canonical_user_ids, owner_matches


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
