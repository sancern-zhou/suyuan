import pytest

from app.social.targeted_broadcast_service import TargetedSocialBroadcastService


@pytest.fixture(autouse=True)
def _no_app_accounts(monkeypatch):
    """测试池只含夹具用户；真实 APP_ACCOUNTS_JSON 会与夹具撞名。"""
    monkeypatch.setattr(
        "app.social.targeted_broadcast_service._accounts", lambda: {}
    )


def _accounts_fixture(monkeypatch, accounts):
    monkeypatch.setattr(
        "app.social.targeted_broadcast_service._accounts", lambda: accounts
    )


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
async def test_broadcast_resolves_unique_names_and_persists_context(
    tmp_path, monkeypatch
):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    _accounts_fixture(monkeypatch, {
        "admin-1": {"name": "周三成", "status": "active"},
        "admin-2": {"name": "李四", "status": "active"},
    })
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=[" 周三成 ", "李四", "周三成"],
        media=[str(report)],
        context_metadata={"source": "assistant_tool"},
    )

    assert broadcaster.calls[0]["target_user_ids"] == [
        "app:android:admin-1",
        "app:android:admin-2",
    ]
    assert broadcaster.calls[0]["channels"] == ["app"]
    assert broadcaster.calls[0]["persist_context"] is True
    assert broadcaster.calls[0]["context_metadata"] == {
        "source": "assistant_tool"
    }
    assert [row["user_name"] for row in result["delivery_results"]] == [
        "周三成",
        "李四",
    ]
    assert [row["user_id"] for row in result["delivery_results"]] == [
        "app:android:admin-1",
        "app:android:admin-2",
    ]
    assert result["failed_user_names"] == []
    assert result["success"] is True


@pytest.mark.asyncio
async def test_broadcast_resolves_app_account_whose_alias_equals_name(monkeypatch):
    # App accounts use the account id as sender_id; when the id equals the
    # display name the alias pass used to duplicate the pool entry and every
    # broadcast to that name failed with "duplicate user name".
    _accounts_fixture(monkeypatch, {
        "周三成": {"name": "周三成", "status": "active"},
    })
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=["周三成"],
    )

    assert result["failed_user_names"] == []
    assert result["success"] is True
    assert broadcaster.calls[0]["target_user_ids"] == ["app:android:周三成"]
    assert broadcaster.calls[0]["channels"] == ["app"]


@pytest.mark.asyncio
async def test_broadcast_rejects_duplicate_and_invalid_names_without_guessing(
    monkeypatch,
):
    _accounts_fixture(monkeypatch, {
        "valid": {"name": "唯一有效用户", "status": "active"},
        "dup-1": {"name": "重名用户", "status": "active"},
        "dup-2": {"name": "重名用户", "status": "active"},
        "disabled": {"name": "禁用用户", "status": "disabled"},
        "unrequested": {"name": "未指定用户", "status": "active"},
    })
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=[
            "唯一有效用户",
            "重名用户",
            "不存在用户",
            "禁用用户",
        ],
    )

    assert broadcaster.calls[0]["target_user_ids"] == [
        "app:android:valid"
    ]
    assert result["success"] is True
    assert result["failed_user_names"] == [
        "重名用户",
        "不存在用户",
        "禁用用户",
    ]
    rows = {row["user_name"]: row for row in result["delivery_results"]}
    assert rows["重名用户"]["error"] == "duplicate user name"
    assert rows["不存在用户"]["error"] == "user not found"
    # 非 active 账号在池构建阶段即被剔除，与不存在同口径
    assert rows["禁用用户"]["error"] == "user not found"
    assert "未指定用户" not in rows


@pytest.mark.asyncio
async def test_broadcast_rejects_empty_target_names_without_sending(monkeypatch):
    _accounts_fixture(monkeypatch, {})
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=["", "  "],
    )

    assert result["success"] is False
    assert result["summary"] == "必须指定目标用户名称"
    assert broadcaster.calls == []


@pytest.mark.asyncio
async def test_broadcast_rejects_names_sharing_one_social_binding(monkeypatch):
    # 账号 b 的显示名是 "X"：按名 "X" 与按账号别名 "b" 指向同一 social_user_id，
    # 两个名字都命中同一收件人时按 duplicate social binding 拒绝整组。
    _accounts_fixture(monkeypatch, {
        "b": {"name": "X", "status": "active"},
        "c": {"name": "丙", "status": "active"},
    })
    broadcaster = FakeBroadcaster()
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=["X", "b", "丙"],
    )

    assert broadcaster.calls[0]["target_user_ids"] == [
        "app:android:c"
    ]
    rows = {row["user_name"]: row for row in result["delivery_results"]}
    assert rows["X"]["error"] == "duplicate social binding"
    assert rows["b"]["error"] == "duplicate social binding"
    assert rows["丙"]["sent"] is True


@pytest.mark.asyncio
async def test_broadcast_does_not_report_success_when_context_is_not_persisted(
    monkeypatch,
):
    _accounts_fixture(monkeypatch, {
        "admin-1": {"name": "周三成", "status": "active"},
    })
    broadcaster = FakeBroadcaster(context_persisted=False)
    service = TargetedSocialBroadcastService(broadcaster)

    result = await service.broadcast(
        message="许昌告警",
        target_user_names=["周三成"],
    )

    assert result["success"] is False
    assert result["failed_user_names"] == ["周三成"]
    assert result["delivery_results"][0]["sent"] is True
    assert result["delivery_results"][0]["context_persisted"] is False
