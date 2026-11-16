"""企业微信投递层：字节截断、受众分组建任务、失败隔离、提醒发送。"""

from __future__ import annotations

import json

import pytest

from app.scenarios.xuchang_push_common.wecom_delivery import (
    CONTENT_LIMIT_BYTES,
    clip_content,
    push_wecom_report,
)
from app.social.wecom.bindings import WecomBindingStore
from config.settings import settings


class FakeClient:
    enabled = True

    def __init__(self, fail_senders: set[str] | None = None):
        self.fail_senders = fail_senders or set()
        self.tasks: list[dict] = []
        self.reminded: list[str] = []

    async def add_group_msg_task(self, *, sender, external_userids, content):
        if sender in self.fail_senders:
            raise RuntimeError(f"wecom task failed for {sender}")
        self.tasks.append(
            {"sender": sender, "external_userids": list(external_userids), "content": content}
        )
        return {"msgid": f"msg-{len(self.tasks)}", "sender": sender}

    async def remind_group_msg_send(self, msgid):
        self.reminded.append(msgid)
        return {"errcode": 0}


class DisabledClient:
    enabled = False


def test_clip_content_keeps_short_text_and_is_byte_safe():
    assert clip_content("简短周报") == "简短周报"

    long_text = "空气污染特征分析。" * 500  # 远超 2048 字节
    clipped = clip_content(long_text)
    assert len(clipped.encode("utf-8")) <= CONTENT_LIMIT_BYTES
    assert clipped.endswith("（内容过长已截断，完整通报见微信群/系统）")
    # 截断后仍是合法 UTF-8 文本（不撕裂多字节字符）
    clipped.encode("utf-8").decode("utf-8")


# ---------------------------------------------------------------------------
# Delivery orchestration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_disabled_short_circuits(tmp_path):
    store = WecomBindingStore(tmp_path / "bindings.json")
    result = await push_wecom_report(
        "monthly_review",
        title="【月度特征分析】",
        content="正文",
        accounts=["大气科1"],
        client=DisabledClient(),
        binding_store=store,
    )
    assert result == {
        "enabled": False,
        "kind": "monthly_review",
        "tasks": [],
        "recipients": 0,
        "skipped": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_report_groups_by_owner_and_reminds(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wecom_default_member", "ops-member")
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="memberA")
    await store.bind("大气科2", "wm-2", owner="memberA")
    await store.bind("执法1", "wm-3", owner="memberB")
    await store.bind("无主者", "wm-4", owner="")  # 兜底到 default_member
    await store.bind("已断开", "wm-5", owner="memberA")
    await store.mark_unbound("wm-5")
    client = FakeClient()

    result = await push_wecom_report(
        "enterprise_clue",
        title="【企业核查线索周报】",
        content="周报正文",
        accounts=["大气科1", "app:android:大气科2", "执法1", "无主者", "已断开", "未绑定者"],
        client=client,
        binding_store=store,
    )

    # memberA / memberB / 兜底 ops-member 三个任务；已断开与未绑定跳过
    assert [t["sender"] for t in client.tasks] == ["memberA", "memberB", "ops-member"]
    assert client.tasks[0]["external_userids"] == ["wm-1", "wm-2"]
    assert client.tasks[1]["external_userids"] == ["wm-3"]
    assert client.tasks[2]["external_userids"] == ["wm-4"]
    assert result["recipients"] == 4
    assert result["skipped"] == 2
    assert result["failed"] == 0
    # 每个任务都被提醒一次
    assert sorted(client.reminded) == ["msg-1", "msg-2", "msg-3"]
    # 成功后回写推送时间
    assert (await store.get("大气科1"))["last_push_at"]
    assert (await store.get("执法1"))["last_push_at"]


@pytest.mark.asyncio
async def test_report_single_task_failure_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wecom_default_member", "ops-member")
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="memberA")
    await store.bind("执法1", "wm-3", owner="memberB")
    client = FakeClient(fail_senders={"memberA"})

    result = await push_wecom_report(
        "monthly_review",
        title="t",
        content="c",
        accounts=["大气科1", "执法1"],
        client=client,
        binding_store=store,
    )

    assert result["failed"] == 1
    assert result["recipients"] == 1
    assert [t["sender"] for t in result["tasks"]] == ["memberB"]


@pytest.mark.asyncio
async def test_report_resolves_roles_via_push_audiences(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "push_audiences.json").write_text(
        json.dumps({"科长": {"app_accounts": ["大气科1"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.scenarios.xuchang_push_common.audiences.get_data_registry",
        lambda: registry,
    )
    monkeypatch.setattr(settings, "wecom_default_member", "ops-member")
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="ops-member")
    client = FakeClient()

    result = await push_wecom_report(
        "monthly_review",
        title="t",
        content="c",
        roles=["科长"],
        client=client,
        binding_store=store,
    )

    assert result["recipients"] == 1
    assert client.tasks[0]["sender"] == "ops-member"


@pytest.mark.asyncio
async def test_report_content_clipped_to_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "wecom_default_member", "ops-member")
    store = WecomBindingStore(tmp_path / "bindings.json")
    await store.bind("大气科1", "wm-1", owner="ops-member")
    client = FakeClient()

    await push_wecom_report(
        "monthly_review",
        title="【月度特征分析】",
        content="长文" * 3000,
        accounts=["大气科1"],
        client=client,
        binding_store=store,
    )

    assert len(client.tasks[0]["content"].encode("utf-8")) <= CONTENT_LIMIT_BYTES
