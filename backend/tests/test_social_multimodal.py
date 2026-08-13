from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.agent.memory_consolidator_factory import create_memory_consolidator_agent
from app.agent.core.planner import ReActPlanner
from app.agent.resources.resource_service import SessionResourceService
from app.agent.resources.resource_service import ResourceBatchResult, StoredResource
from app.agent.session import Session
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import (
    MEMORY_CONSOLIDATOR_TOOLS,
    SOCIAL_TOOL_NAMES,
    SOCIAL_TOOL_ORDER,
)
from app.agent.runtime.tool_coordinator import ToolCoordinator
from app.agent.runtime.multimodal import (
    build_anthropic_user_content,
    build_persisted_user_content,
    build_base64_user_content,
    extract_multimodal_attachments,
)
from app.agent.tool_adapter import get_tool_schemas
from app.services.llm_service import LLMService
from app.social.agent_bridge import AgentBridge
from app.social.events import InboundMessage
from app.social.message_bus import MessageBus
from app.tools.utility.read_file_tool import ReadFileTool


class RecordingSocialResourceService:
    def __init__(self):
        self.calls = []

    async def upsert_run_resources(
        self,
        session_id,
        run_id,
        resources,
        *,
        turn_sequence=0,
    ):
        self.calls.append((session_id, run_id, resources))
        stored = [
            StoredResource.from_declaration(
                session_id,
                run_id,
                resource,
                created_at=datetime.now(UTC),
                turn_sequence=turn_sequence,
            )
            for resource in resources
        ]
        return ResourceBatchResult(version=1, resources=stored)


def test_social_image_attachment_becomes_base64_anthropic_block(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = build_anthropic_user_content(
        "看下这张图",
        [{"type": "image", "name": "sample.png", "local_path": str(image_path), "mime_type": "image/png"}],
    )

    assert content[0] == {"type": "text", "text": "看下这张图"}
    assert content[1]["type"] == "image"
    assert content[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgo=",
    }


def test_social_image_attachment_uses_url_when_no_local_file():
    content = build_anthropic_user_content(
        "识别图片",
        [{"type": "image", "url": "https://example.com/a.webp", "mime_type": "image/webp"}],
    )

    assert content == [
        {"type": "text", "text": "识别图片"},
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.com/a.webp",
            },
        },
    ]


def test_social_image_attachment_prefers_local_base64_over_remote_url(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = build_anthropic_user_content(
        "识别图片",
        [
            {
                "type": "image",
                "name": "sample.png",
                "local_path": str(image_path),
                "url": "https://public.example.com/signed/sample.png",
                "mime_type": "image/png",
            }
        ],
    )

    assert content[0] == {"type": "text", "text": "识别图片"}
    assert content[1]["type"] == "image"
    assert content[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgo=",
    }


def test_social_image_attachment_can_force_base64_fallback(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = build_base64_user_content(
        "识别图片",
        [
            {
                "type": "image",
                "name": "sample.png",
                "local_path": str(image_path),
                "url": "https://public.example.com/signed/sample.png",
                "mime_type": "image/png",
            }
        ],
    )

    assert content[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgo=",
    }


def test_persisted_social_image_content_never_contains_base64(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    persisted = build_persisted_user_content(
        "看下这张图",
        [
            {
                "type": "image",
                "name": "sample.png",
                "local_path": str(image_path),
                "url": "https://public.example.com/signed/sample.png",
                "mime_type": "image/png",
            }
        ],
    )

    serialized = str(persisted)
    assert persisted == [
        {"type": "text", "text": "看下这张图"},
        {
            "type": "text",
            "text": "[用户发送了一张图片：sample.png，image/png，已在当前轮以原生多模态方式提供。]",
        },
    ]
    assert "base64" not in serialized
    assert "iVBOR" not in serialized
    assert str(image_path) not in serialized


def test_social_mode_does_not_expose_analyze_image_tool():
    assert "analyze_image" not in SOCIAL_TOOL_NAMES


def test_social_tool_order_does_not_reference_analyze_image():
    assert "analyze_image" not in SOCIAL_TOOL_ORDER


def test_social_mode_does_not_expose_memory_mutation_tools():
    schemas = get_tool_schemas(mode="social")
    names = {schema["name"] for schema in schemas}

    hidden_tools = {"remember_fact", "replace_memory", "remove_memory", "TodoWrite"}
    assert names.isdisjoint(hidden_tools)
    assert set(SOCIAL_TOOL_NAMES).isdisjoint(hidden_tools)
    assert hidden_tools.isdisjoint(SOCIAL_TOOL_ORDER)


def test_memory_consolidator_still_exposes_memory_mutation_tools():
    schemas = get_tool_schemas(mode="memory_consolidator")
    names = {schema["name"] for schema in schemas}

    assert {"remember_fact", "replace_memory", "remove_memory"}.issubset(names)


def test_memory_consolidator_agent_registers_only_memory_tools():
    agent = create_memory_consolidator_agent()

    actual_tools = set(agent.executor.tool_registry)

    assert actual_tools == set(MEMORY_CONSOLIDATOR_TOOLS)
    assert "create_pptx_with_ppt_master" not in actual_tools
    assert "execute_python" not in actual_tools


def test_memory_consolidator_prompt_filters_available_tools():
    prompt = build_react_system_prompt(
        mode="memory_consolidator",
        available_tools=[
            "read_file",
            "grep",
            "remember_fact",
            "replace_memory",
            "remove_memory",
            "execute_python",
            "create_pptx_with_ppt_master",
        ],
    )

    assert "工具（5个）" in prompt


def test_social_read_file_schema_does_not_advertise_image_analysis():
    schemas = get_tool_schemas(mode="social")
    read_file_schema = next(schema for schema in schemas if schema["name"] == "read_file")

    serialized = str(read_file_schema)
    assert "图片分析" not in serialized
    assert "是否自动分析图片" not in serialized
    assert "图片分析类型" not in serialized
    assert "auto_analyze" not in read_file_schema["parameters"]["properties"]
    assert "analysis_type" not in read_file_schema["parameters"]["properties"]


def test_social_read_file_schema_exposes_multimodal_attachment_for_images():
    schemas = get_tool_schemas(mode="social")
    read_file_schema = next(schema for schema in schemas if schema["name"] == "read_file")

    properties = read_file_schema["parameters"]["properties"]
    assert "as_multimodal_attachment" in properties
    assert properties["as_multimodal_attachment"]["default"] is False
    assert "multimodal_attachment" in str(read_file_schema)


def test_non_social_read_file_schema_exposes_opt_in_multimodal_attachment():
    schemas = get_tool_schemas(mode="expert")
    read_file_schema = next(schema for schema in schemas if schema["name"] == "read_file")

    properties = read_file_schema["parameters"]["properties"]
    assert properties["as_multimodal_attachment"]["default"] is False
    assert "multimodal_attachment" in str(read_file_schema)


def test_read_file_input_never_implicitly_enables_multimodal_attachment():
    coordinator = ToolCoordinator(tool_executor=object())

    social_args = coordinator.normalize_tool_input("read_file", {"path": "/tmp/a.png"}, mode="social")
    expert_args = coordinator.normalize_tool_input("read_file", {"path": "/tmp/a.png"}, mode="expert")

    assert "as_multimodal_attachment" not in social_args
    assert "as_multimodal_attachment" not in expert_args


@pytest.mark.asyncio
async def test_read_file_image_can_return_multimodal_attachment(tmp_path: Path):
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    result = await ReadFileTool().execute(
        path=str(image_path),
        as_multimodal_attachment=True,
    )

    assert result["success"] is True
    assert result["type"] == "multimodal_attachment"
    assert result["data"]["type"] == "multimodal_attachment"
    assert result["attachments"] == [
        {
            "type": "image",
            "name": "screen.png",
            "local_path": str(image_path),
            "mime_type": "image/png",
        }
    ]
    assert "base64" not in str(result)
    assert "analysis" not in result["data"]


def test_extract_multimodal_attachments_from_tool_observation():
    observation = {
        "success": True,
        "tool_results": [
            {
                "tool_name": "read_file",
                "result": {
                    "type": "multimodal_attachment",
                    "attachments": [
                        {
                            "type": "image",
                            "name": "screen.png",
                            "local_path": "/tmp/screen.png",
                            "mime_type": "image/png",
                        }
                    ],
                },
            }
        ],
    }

    assert extract_multimodal_attachments(observation) == [
        {
            "type": "image",
            "name": "screen.png",
            "local_path": "/tmp/screen.png",
            "mime_type": "image/png",
        }
    ]


@pytest.mark.asyncio
async def test_social_media_is_registered_as_a_session_attachment_resource(tmp_path: Path):
    image_path = tmp_path / "meal.jpg"
    image_path.write_bytes(b"jpg")
    resource_service = RecordingSocialResourceService()
    bridge = AgentBridge(
        message_bus=MessageBus(),
        agent=object(),
        session_mapper=object(),
        mode="social",
        enable_heartbeat=False,
        enable_memory=False,
        resource_service=resource_service,
        resource_storage_root=tmp_path / "resources",
    )

    attachments = await bridge._prepare_social_attachments(
        session_id="social-session-resource",
        channel="weixin:account-1",
        media=[str(image_path)],
    )

    session_id, run_id, declarations = resource_service.calls[0]
    assert session_id == "social-session-resource"
    assert run_id.startswith("social-inbound:")
    assert declarations[0].role.value == "attachment"
    assert Path(declarations[0].locator.path).read_bytes() == b"jpg"
    assert Path(declarations[0].locator.path) != image_path.resolve()
    assert declarations[0].metadata["source"] == "social_inbound"
    assert attachments[0]["resource_id"]
    assert attachments[0]["ref_id"] == attachments[0]["resource_id"]
    assert "url" not in attachments[0]


@pytest.mark.asyncio
async def test_social_transcript_persists_resource_attachment(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "meal.jpg"
    image_path.write_bytes(b"jpg")
    resource_service = RecordingSocialResourceService()

    class RecordingAgent:
        def __init__(self):
            self._session_store = {}

        async def analyze(self, **_kwargs):
            yield {"type": "complete", "data": {"answer": "这是烧鸭饭"}}

    async def no_disk_write(*_args, **_kwargs):
        return True

    monkeypatch.setattr("app.social.agent_bridge.append_session_transcript_for_mode", no_disk_write)
    bridge = AgentBridge(
        message_bus=MessageBus(),
        agent=RecordingAgent(),
        session_mapper=object(),
        mode="social",
        enable_heartbeat=False,
        enable_memory=False,
        resource_service=resource_service,
        resource_storage_root=tmp_path / "resources",
    )
    attachments = await bridge._prepare_social_attachments(
        session_id="social-session-transcript",
        channel="weixin:account-1",
        media=[str(image_path)],
    )
    session = Session(session_id="social-session-transcript", query="[image]")

    await bridge._aggregate_agent_events(
        content="[image]",
        session_id=session.session_id,
        chat_id="chat-1",
        channel="weixin:account-1",
        attachments=attachments,
        session=session,
    )

    user_message = session.conversation_history[0]
    assert user_message["attachments"][0]["resource_id"] == attachments[0]["resource_id"]
    assert user_message["attachments"][0]["url"].endswith(
        f"/{attachments[0]['resource_id']}/content"
    )
    assert str(image_path) not in str(user_message)


@pytest.mark.asyncio
async def test_social_bridge_passes_media_as_attachments_and_hides_local_paths(tmp_path: Path):
    image_path = tmp_path / "rash.jpg"
    image_path.write_bytes(b"jpg")

    class RecordingAgent:
        def __init__(self):
            self.calls = []

        async def analyze(self, **kwargs):
            self.calls.append(kwargs)
            yield {"type": "complete", "data": {"response": "看到了"}}

    class SessionMapper:
        async def get_or_create_session(self, social_user_id, mode="social"):
            return "social-session"

    agent = RecordingAgent()
    bridge = AgentBridge(
        message_bus=MessageBus(),
        agent=agent,
        session_mapper=SessionMapper(),
        mode="social",
        enable_heartbeat=False,
        enable_memory=False,
        resource_service=SessionResourceService.in_memory(),
        resource_storage_root=tmp_path / "resources",
    )

    msg = InboundMessage(
        channel="weixin:test",
        sender_id="user-1",
        chat_id="chat-1",
        content="[image]",
        media=[str(image_path)],
    )

    await bridge._process_message(
        msg,
        bot_account="bot-1",
        social_user_id="weixin:test:bot-1:user-1",
        session_id="social-session",
    )

    assert agent.calls
    call = agent.calls[0]
    assert call["user_query"] == "[image]"
    assert str(image_path) not in call["user_query"]
    [attachment] = call["attachments"]
    assert attachment["type"] == "image"
    assert attachment["name"] == "rash.jpg"
    assert Path(attachment["local_path"]).read_bytes() == b"jpg"
    assert Path(attachment["local_path"]) != image_path.resolve()
    assert attachment["mime_type"] == "image/jpeg"
    assert attachment["resource_id"]
    assert attachment["ref_id"] == attachment["resource_id"]
    assert "url" not in attachment


@pytest.mark.asyncio
async def test_social_bridge_keeps_local_images_off_the_transient_url_path(tmp_path: Path):
    image_path = tmp_path / "rash.jpg"
    image_path.write_bytes(b"jpg")

    bridge = AgentBridge(
        message_bus=MessageBus(),
        agent=object(),
        session_mapper=object(),
        mode="social",
        enable_heartbeat=False,
        enable_memory=False,
    )

    assert bridge._build_agent_attachments([str(image_path)]) == [
        {
            "type": "image",
            "name": "rash.jpg",
            "local_path": str(image_path),
            "mime_type": "image/jpeg",
        }
    ]


@pytest.mark.asyncio
async def test_planner_passes_provider_model_override_to_llm_service():
    class FakeLLMService:
        def __init__(self):
            self.calls = []

        async def chat_anthropic_streaming(self, **kwargs):
            self.calls.append(kwargs)
            yield {"type": "message_stop", "data": {}}

    fake_llm = FakeLLMService()
    planner = ReActPlanner(llm_client=fake_llm)

    async for _ in planner.think_and_action_streaming(
        query="看图",
        system_prompt="system",
        user_conversation="user",
        tools=[],
        iteration=1,
        mode="social",
        llm_provider="minimax",
        llm_model="MiniMax-M3",
    ):
        pass

    assert fake_llm.calls
    assert fake_llm.calls[0]["provider"] == "minimax"
    assert fake_llm.calls[0]["model"] == "MiniMax-M3"


@pytest.mark.asyncio
async def test_planner_retries_minimax_fetch_url_failure_with_base64(tmp_path: Path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeLLMService:
        def __init__(self):
            self.calls = []

        async def chat_anthropic_streaming(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RuntimeError("invalid param: fetch url failed: i/o timeout")

            class Block:
                type = "text"
                text = "看到了"

            yield {"type": "content_block_start", "data": {"index": 0, "block": Block()}}

            class Delta:
                type = "text_delta"
                text = "看到了"

            yield {"type": "content_block_delta", "data": {"index": 0, "delta": Delta()}}
            yield {"type": "content_block_stop", "data": {"index": 0}}
            yield {"type": "message_stop", "data": {}}

        async def chat_anthropic(self, **kwargs):
            self.calls.append(kwargs)

            class TextBlock:
                type = "text"
                text = "看到了"

            return {
                "content": [TextBlock()],
                "model": kwargs["model"],
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "stop_reason": "end_turn",
            }

    fake_llm = FakeLLMService()
    planner = ReActPlanner(llm_client=fake_llm)

    events = []
    user_content = build_anthropic_user_content(
        "看图",
        [
            {
                "type": "image",
                "name": "sample.png",
                "local_path": str(image_path),
                "url": "https://object.example.com/sample.png?sig=1",
                "mime_type": "image/png",
            }
        ],
    )
    async for event in planner.think_and_action_streaming(
        query="看图",
        system_prompt="system",
        user_conversation="user",
        tools=[],
        iteration=1,
        mode="social",
        user_content=user_content,
        attachments=[
            {
                "type": "image",
                "name": "sample.png",
                "local_path": str(image_path),
                "url": "https://object.example.com/sample.png?sig=1",
                "mime_type": "image/png",
            }
        ],
        llm_provider="minimax",
        llm_model="MiniMax-M3",
    ):
        events.append(event)

    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[0]["provider"] == "minimax"
    assert fake_llm.calls[1]["provider"] == "minimax"
    retry_content = fake_llm.calls[1]["messages"][-1]["content"]
    assert retry_content[1]["source"]["type"] == "base64"
    assert retry_content[1]["source"]["data"] == "iVBORw0KGgo="
    assert any(event["type"] == "action" for event in events)


def test_provider_override_service_disables_fallbacks():
    service = LLMService()

    override = service._create_provider_override_service("minimax", "MiniMax-M3")

    assert override is not None
    assert override.provider == "minimax"
    assert override.model == "MiniMax-M3"
    assert override.request_fallbacks == ""
