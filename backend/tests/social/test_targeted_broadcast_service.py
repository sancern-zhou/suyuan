from types import SimpleNamespace

import pytest

from app.social.targeted_broadcast_service import TargetedSocialBroadcastService


def _user(
    user_id,
    name,
    *,
    status="active",
    channel="weixin:auto_one",
    social_user_id=None,
):
    return SimpleNamespace(
        id=user_id,
        name=name,
        status=status,
        channel=channel,
        social_user_id=social_user_id,
    )


class FakeRegistry:
    def __init__(self, users):
        self.users = users
        self.list_calls = 0

    async def list_users(self):
        self.list_calls += 1
        return list(self.users)


class FakeBroadcaster:
    def __init__(self, *, context_persisted=True):
        self.calls = []
        self.context_persisted = context_persisted

    async def broadcast(self, **kwargs):
        self.calls.append(kwargs)
        targets = kwargs["target_user_ids"]
        return {
            "status": "success",
            "success": True,
            "channels_sent": list(targets),
            "failed_user_ids": [],
            "delivery_results": [
                {
                    "social_user_id": social_user_id,
                    "sent": True,
                    "context_persisted": self.context_persisted,
                    "error": (
                        None if self.context_persisted else "context persist failed"
                    ),
                }
                for social_user_id in targets
            ],
            "media_sent": len(kwargs.get("media") or []),
            "summary": f"已广播给 {len(targets)} 个社交用户",
        }


@pytest.mark.asyncio
async def test_broadcast_resolves_unique_names_and_persists_context(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    registry = FakeRegistry([
        _user("admin-1", "周三成", social_user_id="weixin:auto:bot:wx-1"),
        _user("admin-2", "李四", social_user_id="weixin:auto:bot:wx-2"),
    ])
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(registry, broadcaster)

    result = await service.broadcast(
        message="运城告警",
        target_user_names=[" 周三成 ", "李四", "周三成"],
        media=[str(report)],
        context_metadata={"source": "assistant_tool"},
    )

    assert registry.list_calls == 1
    assert broadcaster.calls[0]["target_user_ids"] == [
        "weixin:auto:bot:wx-1",
        "weixin:auto:bot:wx-2",
    ]
    assert broadcaster.calls[0]["channels"] == ["weixin"]
    assert broadcaster.calls[0]["persist_context"] is True
    assert broadcaster.calls[0]["context_metadata"] == {
        "source": "assistant_tool"
    }
    assert [row["user_name"] for row in result["delivery_results"]] == [
        "周三成",
        "李四",
    ]
    assert [row["user_id"] for row in result["delivery_results"]] == [
        "admin-1",
        "admin-2",
    ]
    assert result["failed_user_names"] == []
    assert result["success"] is True


@pytest.mark.asyncio
async def test_broadcast_rejects_duplicate_and_invalid_names_without_guessing():
    registry = FakeRegistry([
        _user("valid", "唯一有效用户", social_user_id="weixin:auto:bot:valid"),
        _user("dup-1", "重名用户", social_user_id="weixin:auto:bot:dup-1"),
        _user("dup-2", "重名用户", social_user_id="weixin:auto:bot:dup-2"),
        _user(
            "disabled",
            "禁用用户",
            status="disabled",
            social_user_id="weixin:auto:bot:disabled",
        ),
        _user("unbound", "未绑定用户", social_user_id=None),
        _user(
            "other",
            "非微信用户",
            channel="dingtalk",
            social_user_id="dingtalk:bot:other",
        ),
        _user("unrequested", "未指定用户", social_user_id="weixin:auto:bot:no"),
    ])
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(registry, broadcaster)

    result = await service.broadcast(
        message="运城告警",
        target_user_names=[
            "唯一有效用户",
            "重名用户",
            "不存在用户",
            "禁用用户",
            "未绑定用户",
            "非微信用户",
        ],
    )

    assert broadcaster.calls[0]["target_user_ids"] == [
        "weixin:auto:bot:valid"
    ]
    assert result["success"] is True
    assert result["failed_user_names"] == [
        "重名用户",
        "不存在用户",
        "禁用用户",
        "未绑定用户",
        "非微信用户",
    ]
    rows = {row["user_name"]: row for row in result["delivery_results"]}
    assert rows["重名用户"]["error"] == "duplicate user name"
    assert rows["不存在用户"]["error"] == "user not found"
    assert rows["禁用用户"]["error"] == "user is not active"
    assert rows["未绑定用户"]["error"] == "user is not bound"
    assert rows["非微信用户"]["error"] == "user is not bound to WeChat"
    assert "未指定用户" not in rows


@pytest.mark.asyncio
async def test_broadcast_rejects_empty_target_names_without_sending():
    registry = FakeRegistry([])
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(registry, broadcaster)

    result = await service.broadcast(
        message="运城告警",
        target_user_names=["", "  "],
    )

    assert result["success"] is False
    assert result["summary"] == "必须指定目标用户名称"
    assert registry.list_calls == 0
    assert broadcaster.calls == []


@pytest.mark.asyncio
async def test_broadcast_rejects_names_sharing_one_social_binding():
    registry = FakeRegistry([
        _user("shared-1", "甲", social_user_id="weixin:auto:bot:shared"),
        _user("shared-2", "乙", social_user_id="weixin:auto:bot:shared"),
        _user("valid", "丙", social_user_id="weixin:auto:bot:valid"),
    ])
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(registry, broadcaster)

    result = await service.broadcast(
        message="运城告警",
        target_user_names=["甲", "乙", "丙"],
    )

    assert broadcaster.calls[0]["target_user_ids"] == [
        "weixin:auto:bot:valid"
    ]
    rows = {row["user_name"]: row for row in result["delivery_results"]}
    assert rows["甲"]["error"] == "duplicate social binding"
    assert rows["乙"]["error"] == "duplicate social binding"
    assert rows["丙"]["sent"] is True


@pytest.mark.asyncio
async def test_broadcast_does_not_report_success_when_context_is_not_persisted():
    registry = FakeRegistry([
        _user("admin-1", "周三成", social_user_id="weixin:auto:bot:wx-1"),
    ])
    broadcaster = FakeBroadcaster(context_persisted=False)
    service = TargetedSocialBroadcastService(registry, broadcaster)

    result = await service.broadcast(
        message="运城告警",
        target_user_names=["周三成"],
    )

    assert result["success"] is False
    assert result["failed_user_names"] == ["周三成"]
    assert result["delivery_results"][0]["sent"] is True
    assert result["delivery_results"][0]["context_persisted"] is False
