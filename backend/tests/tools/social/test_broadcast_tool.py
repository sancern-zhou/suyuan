import httpx
import pytest

from app.core.social_broadcast_worker_client import (
    SocialBroadcastWorkerClient,
    SocialBroadcastWorkerUnavailable,
)
from app.tools.social.broadcast.tool import BroadcastSocialUsersTool


class FakeWorkerClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def broadcast(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {
            "status": "success",
            "success": True,
            "channels_sent": ["weixin:auto:bot:user"],
            "failed_user_names": [],
            "delivery_results": [{
                "user_name": "周三成",
                "user_id": "admin-1",
                "social_user_id": "weixin:auto:bot:user",
                "sent": True,
                "context_persisted": True,
                "error": None,
            }],
            "media_sent": 1,
            "summary": "已广播给 1 个目标用户",
        }


@pytest.mark.asyncio
async def test_worker_client_posts_payload_with_internal_token(monkeypatch):
    captured = {}

    async def fake_post(_client, url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={"success": True, "delivery_results": []},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = SocialBroadcastWorkerClient(
        base_url="http://worker:8011/",
        token="secret",
    )

    result = await client.broadcast(
        message="运城告警",
        target_user_names=["周三成"],
        media=["/tmp/report.docx"],
        context_metadata={"source": "assistant_tool"},
    )

    assert result["success"] is True
    assert captured["url"] == "http://worker:8011/internal/social/broadcast"
    assert captured["headers"] == {"x-social-worker-token": "secret"}
    assert captured["json"]["target_user_names"] == ["周三成"]


@pytest.mark.asyncio
async def test_worker_client_converts_non_2xx_to_unavailable(monkeypatch):
    async def fake_post(_client, url, **kwargs):
        return httpx.Response(
            503,
            json={"detail": "worker unavailable"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = SocialBroadcastWorkerClient(base_url="http://worker:8011")

    with pytest.raises(SocialBroadcastWorkerUnavailable, match="503"):
        await client.broadcast(
            message="运城告警",
            target_user_names=["周三成"],
        )


def test_broadcast_tool_schema_requires_explicit_user_names():
    tool = BroadcastSocialUsersTool(worker_client=FakeWorkerClient())

    schema = tool.get_function_schema()
    properties = schema["parameters"]["properties"]

    assert schema["parameters"]["required"] == [
        "message",
        "target_user_names",
    ]
    assert properties["target_user_names"]["minItems"] == 1
    assert "channels" not in properties


@pytest.mark.asyncio
async def test_broadcast_tool_rejects_empty_names_without_worker_call():
    client = FakeWorkerClient()
    tool = BroadcastSocialUsersTool(worker_client=client)

    result = await tool.execute(
        message="运城告警",
        target_user_names=["", "  "],
    )

    assert result["success"] is False
    assert result["summary"] == "必须指定目标用户名称"
    assert client.calls == []


@pytest.mark.asyncio
async def test_broadcast_tool_forwards_names_media_and_source_metadata():
    client = FakeWorkerClient()
    tool = BroadcastSocialUsersTool(worker_client=client)

    result = await tool.execute(
        message="运城告警",
        target_user_names=["周三成"],
        media=["/tmp/report.docx"],
    )

    assert result["success"] is True
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["message"] == "运城告警"
    assert call["target_user_names"] == ["周三成"]
    assert call["media"] == ["/tmp/report.docx"]
    metadata = call["context_metadata"]
    assert metadata["source"] == "assistant_tool"
    assert metadata["tool_name"] == "broadcast_social_users"
    assert metadata["task_id"] == "assistant_broadcast"
    assert metadata["event_type"] == "assistant.broadcast"
    assert metadata["event_id"].startswith("assistant-broadcast-")
    assert metadata["execution_id"] == metadata["event_id"]


@pytest.mark.asyncio
async def test_broadcast_tool_returns_structured_worker_unavailable_error():
    client = FakeWorkerClient(
        SocialBroadcastWorkerUnavailable("connection refused")
    )
    tool = BroadcastSocialUsersTool(worker_client=client)

    result = await tool.execute(
        message="运城告警",
        target_user_names=["周三成"],
    )

    assert result["status"] == "failed"
    assert result["success"] is False
    assert result["summary"] == "社交 Worker 不可用，请稍后重试"


@pytest.mark.asyncio
async def test_broadcast_tool_hides_unexpected_internal_errors():
    client = FakeWorkerClient(RuntimeError("http://internal-worker:8011 secret"))
    tool = BroadcastSocialUsersTool(worker_client=client)

    result = await tool.execute(
        message="运城告警",
        target_user_names=["周三成"],
    )

    assert result["success"] is False
    assert result["summary"] == "广播失败，请联系管理员"
    assert "internal-worker" not in result["summary"]
