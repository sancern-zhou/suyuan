"""公众号订阅通知投递层：模板加载、受众→绑定→发送编排、状态回写。"""

from __future__ import annotations

import json

import pytest

from app.scenarios.xuchang_push_common.wechat_mp_delivery import (
    _zip_fields,
    first_notice_line,
    load_wechat_mp_templates,
    push_wechat_mp_notice,
    today_str,
)
from app.social.wechat_mp.bindings import WechatMpBindingStore

TEMPLATES_PAYLOAD = {
    "monthly_review": {
        "template_id": "tpl-monthly",
        "field_keys": ["thing1", "time2", "thing3", "date4"],
    }
}


class FakeClient:
    enabled = True

    def __init__(self, outcomes: dict[str, int] | None = None):
        self.outcomes = outcomes or {}
        self.calls: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []

    async def send_subscribe_batch(self, *, template_id, recipients):
        self.calls.append((template_id, list(recipients)))
        return [
            {"openid": openid, "errcode": self.outcomes.get(openid, 0), "errmsg": "ok"}
            for openid, _ in recipients
        ]


class DisabledClient:
    enabled = False


def _write_templates(registry, payload):
    (registry / "wechat_mp_templates.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def test_load_templates_prefers_env_override(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    _write_templates(registry, TEMPLATES_PAYLOAD)
    override = tmp_path / "override.json"
    override.write_text(
        json.dumps({"enterprise_clue": {"template_id": "tpl-weekly", "field_keys": ["thing1"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("XUCHANG_WECHAT_MP_TEMPLATES", str(override))

    templates = load_wechat_mp_templates(registry_root=registry)

    assert templates == {"enterprise_clue": {"template_id": "tpl-weekly", "field_keys": ["thing1"]}}


def test_load_templates_missing_file_or_invalid_entries(tmp_path):
    assert load_wechat_mp_templates(registry_root=tmp_path) == {}

    _write_templates(tmp_path, {"monthly_review": {"field_keys": ["thing1"]}, "x": {"template_id": "t"}})
    templates = load_wechat_mp_templates(registry_root=tmp_path)
    assert templates == {"x": {"template_id": "t"}}


# ---------------------------------------------------------------------------
# Delivery orchestration
# ---------------------------------------------------------------------------


async def _bind(store: WechatMpBindingStore, account: str, openid: str):
    await store.bind(account, openid)


@pytest.mark.asyncio
async def test_notice_disabled_or_unconfigured_short_circuits(tmp_path):
    store = WechatMpBindingStore(tmp_path / "bindings.json")

    disabled = await push_wechat_mp_notice(
        "monthly_review", fields=["a"], accounts=["大气科1"],
        client=DisabledClient(), binding_store=store, registry_root=tmp_path,
    )
    assert disabled == {"enabled": False, "configured": False, "kind": "monthly_review", "sent": 0, "failed": 0, "skipped": 0}

    unconfigured = await push_wechat_mp_notice(
        "monthly_review", fields=["a"], accounts=["大气科1"],
        client=FakeClient(), binding_store=store, registry_root=tmp_path,
    )
    assert unconfigured["enabled"] is True
    assert unconfigured["configured"] is False


@pytest.mark.asyncio
async def test_notice_sends_to_bound_accounts_and_records_push(tmp_path):
    registry = tmp_path / "registry"
    registry.mkdir()
    _write_templates(registry, TEMPLATES_PAYLOAD)
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await _bind(store, "大气科1", "openid-1")
    await _bind(store, "大气科2", "openid-2")
    client = FakeClient()

    result = await push_wechat_mp_notice(
        "monthly_review",
        fields=["月度特征分析", "2026-10", "PM2.5 同比改善", today_str()],
        accounts=["app:android:大气科1", "大气科2", "未绑定账号"],
        client=client,
        binding_store=store,
        registry_root=registry,
    )

    assert result["sent"] == 2
    assert result["failed"] == 0
    assert result["skipped"] == 1  # 未绑定账号
    template_id, recipients = client.calls[0]
    assert template_id == "tpl-monthly"
    assert [openid for openid, _ in recipients] == ["openid-1", "openid-2"]
    fields = dict(recipients[0][1])
    assert fields == {
        "thing1": "月度特征分析",
        "time2": "2026-10",
        "thing3": "PM2.5 同比改善",
        "date4": today_str(),
    }
    assert (await store.get("大气科1"))["last_push_at"]


@pytest.mark.asyncio
async def test_notice_skips_unsubscribed_and_rejected(tmp_path):
    registry = tmp_path / "registry"
    registry.mkdir()
    _write_templates(registry, TEMPLATES_PAYLOAD)
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await _bind(store, "取关者", "openid-gone")
    await store.mark_unsubscribed("openid-gone")
    await _bind(store, "拒收者", "openid-reject")
    await store.record_template_state("openid-reject", "tpl-monthly", "reject")
    client = FakeClient()

    result = await push_wechat_mp_notice(
        "monthly_review",
        fields=["a", "b", "c", "d"],
        accounts=["取关者", "拒收者"],
        client=client,
        binding_store=store,
        registry_root=registry,
    )

    assert result["sent"] == 0
    assert result["skipped"] == 2
    assert client.calls == []


@pytest.mark.asyncio
async def test_notice_writes_back_rejection_states(tmp_path):
    registry = tmp_path / "registry"
    registry.mkdir()
    _write_templates(registry, TEMPLATES_PAYLOAD)
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await _bind(store, "额度耗尽", "openid-nosub")
    await _bind(store, "已取关", "openid-unfollowed")
    client = FakeClient(
        outcomes={"openid-nosub": 43101, "openid-unfollowed": 43104}
    )

    result = await push_wechat_mp_notice(
        "monthly_review",
        fields=["a", "b", "c", "d"],
        accounts=["额度耗尽", "已取关"],
        client=client,
        binding_store=store,
        registry_root=registry,
    )

    assert result["sent"] == 0
    assert result["failed"] == 2
    assert (await store.get("额度耗尽"))["templates"] == {"tpl-monthly": "reject"}
    assert (await store.get("已取关"))["status"] == "unsubscribed"


@pytest.mark.asyncio
async def test_notice_resolves_roles_via_push_audiences(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    _write_templates(registry, TEMPLATES_PAYLOAD)
    (registry / "push_audiences.json").write_text(
        json.dumps({"科长": {"app_accounts": ["大气科1"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.scenarios.xuchang_push_common.audiences.get_data_registry",
        lambda: registry,
    )
    store = WechatMpBindingStore(tmp_path / "bindings.json")
    await _bind(store, "大气科1", "openid-1")
    client = FakeClient()

    result = await push_wechat_mp_notice(
        "monthly_review",
        fields=["a", "b", "c", "d"],
        roles=["科长"],
        client=client,
        binding_store=store,
        registry_root=registry,
    )

    assert result["sent"] == 1
    assert client.calls[0][1][0][0] == "openid-1"


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def test_zip_fields_truncates_and_skips_blanks():
    fields = _zip_fields(["thing1", "thing2"], ["x" * 60, " "], "k")
    assert fields == {"thing1": "x" * 40}


def test_first_notice_line_falls_back():
    assert first_notice_line("\n\n  【月度特征分析】许昌…  \n正文") == "【月度特征分析】许昌…"
    assert first_notice_line("", limit=5) == ""
