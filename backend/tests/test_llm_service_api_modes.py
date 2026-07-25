import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from PIL import Image

from app.agent.react_agent import ReActAgent
from app.agent.runtime.mode_capabilities import supports_native_multimodal
from app.services import bailian_multimodal
from app.services.llm_service import LLMService
from config.settings import Settings, settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mimo_anthropic_client_uses_sdk_api_key_authentication(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mimo")
    monkeypatch.setattr(settings, "mimo_api_mode", "anthropic_messages")
    monkeypatch.setattr(
        settings,
        "mimo_base_url",
        "https://api.xiaomimimo.com/anthropic",
    )
    monkeypatch.setattr(settings, "mimo_api_key", "mimo-key")
    monkeypatch.setattr(settings, "mimo_model", "mimo-v2.5")

    captured = {}

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeAsyncAnthropic)

    service = LLMService()

    assert service.anthropic_client is not None
    assert captured["api_key"] == "mimo-key"
    assert captured["auth_token"] is None
    assert captured["base_url"] == "https://api.xiaomimimo.com/anthropic"
    assert "default_headers" not in captured


def test_deepseek_api_mode_setting_exists():
    assert settings.deepseek_api_mode in {"anthropic_messages", "chat_completions"}


def test_bailian_settings_replace_all_qwen_settings():
    assert not hasattr(settings, "qwen_api_key")
    assert not hasattr(settings, "qwen_base_url")
    assert not hasattr(settings, "qwen_model")
    assert not hasattr(settings, "qwen_api_mode")
    assert not hasattr(settings, "qwen_vl_api_key")
    assert not hasattr(settings, "qwen_vl_base_url")
    assert not hasattr(settings, "qwen_vl_model")
    assert not hasattr(settings, "qwen_vision_model")
    assert settings.bailian_base_url == (
        "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic"
    )
    assert settings.bailian_model == "qwen3.8-max-preview"
    assert not hasattr(settings, "bailian_vision_model")


@pytest.mark.parametrize("provider", ["qwen", "qwen_vl"])
def test_llm_service_rejects_retired_qwen_providers(monkeypatch, provider):
    monkeypatch.setattr(settings, "llm_provider", provider)

    with pytest.raises(ValueError, match=f"Unsupported LLM provider: {provider}"):
        LLMService()


def test_llm_service_loads_bailian_anthropic_config(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "bailian")
    monkeypatch.setattr(settings, "bailian_api_key", "bailian-key")
    monkeypatch.setattr(
        settings,
        "bailian_base_url",
        "https://bailian.example/apps/anthropic",
    )
    monkeypatch.setattr(settings, "bailian_model", "qwen3.8-max-preview")

    service = LLMService()

    assert service.provider == "bailian"
    assert service.api_mode == "anthropic_messages"
    assert service.api_key == "bailian-key"
    assert service.base_url == "https://bailian.example/apps/anthropic"
    assert service.model == "qwen3.8-max-preview"
    assert service.anthropic_client is not None


def test_multimodal_auto_profile_uses_bailian_qwen(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(
        settings,
        "llm_multimodal_models",
        "bailian/qwen3.8-max-preview,mimo/mimo-v2.5",
    )

    service = LLMService()

    with service.use_auto_profile("multimodal"):
        assert service.provider == "bailian"
        assert service.model == "qwen3.8-max-preview"
        assert service.request_fallbacks == "mimo/mimo-v2.5"


@pytest.mark.parametrize(
    "mode",
    [
        "assistant",
        "expert",
        "query",
        "report",
        "ops",
        "graph",
        "custom",
        "memory_consolidator",
        "deliberation_monitoring",
        "future_mode",
        "",
        None,
    ],
)
def test_every_agent_mode_uses_native_multimodal(mode):
    assert supports_native_multimodal(mode) is True
    assert ReActAgent._select_auto_profile(mode) == "multimodal"


@pytest.mark.parametrize("tier", ["flash", "pro"])
def test_multimodal_profile_takes_priority_over_model_tier(monkeypatch, tier):
    service = LLMService()
    monkeypatch.setattr(
        settings,
        f"llm_{tier}_models",
        "deepseek/deepseek-v4-flash",
    )
    monkeypatch.setattr(
        settings,
        "llm_multimodal_models",
        "bailian/qwen3.8-max-preview,mimo/mimo-v2.5",
    )

    with service.use_model_tier(tier):
        assert service.provider == "deepseek"
        with service.use_auto_profile("multimodal"):
            assert service.provider == "bailian"
            assert service.model == "qwen3.8-max-preview"
            assert service.request_fallbacks == "mimo/mimo-v2.5"

        assert service.provider == "deepseek"


def test_multimodal_profile_closes_temporary_client_on_exit(monkeypatch):
    service = LLMService()
    original_client = service.anthropic_client
    scheduled_to_close = []
    monkeypatch.setattr(
        settings,
        "llm_multimodal_models",
        "bailian/qwen3.8-max-preview",
    )
    monkeypatch.setattr(
        service,
        "_schedule_anthropic_client_close",
        scheduled_to_close.append,
    )

    with service.use_auto_profile("multimodal"):
        temporary_client = service.anthropic_client
        assert temporary_client is not original_client

    assert scheduled_to_close == [temporary_client]
    assert service.anthropic_client is original_client


def test_multimodal_profile_closes_temporary_client_on_exception(monkeypatch):
    service = LLMService()
    original_client = service.anthropic_client
    scheduled_to_close = []
    monkeypatch.setattr(
        settings,
        "llm_multimodal_models",
        "bailian/qwen3.8-max-preview",
    )
    monkeypatch.setattr(
        service,
        "_schedule_anthropic_client_close",
        scheduled_to_close.append,
    )

    with pytest.raises(RuntimeError, match="planner failed"):
        with service.use_auto_profile("multimodal"):
            temporary_client = service.anthropic_client
            raise RuntimeError("planner failed")

    assert scheduled_to_close == [temporary_client]
    assert service.anthropic_client is original_client


def test_ocr_configuration_follows_global_bailian_model(monkeypatch):
    from app.services.ops_audit.semantic import ocr_adapter

    monkeypatch.setenv("BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setenv("BAILIAN_VISION_MODEL", "retired-vision-model")
    monkeypatch.setattr(settings, "bailian_model", "global-auto-model")

    assert ocr_adapter._resolve_bailian_api_key() == "bailian-key"
    assert ocr_adapter._resolve_bailian_model("flow_visual") == "global-auto-model"


def test_visual_runtimes_use_global_bailian_model_only():
    runtime_files = [
        "backend/app/knowledge_base/document_processor.py",
        "backend/app/services/ops_audit/semantic/ocr_adapter.py",
        "backend/app/tools/query/get_weather_situation_map/tool.py",
        "backend/app/tools/utility/analyze_image_tool.py",
        "backend/app/tools/utility/parse_pdf_tool.py",
    ]

    for relative_path in runtime_files:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "bailian_vision_model" not in source, relative_path
        assert "BAILIAN_VISION_MODEL" not in source, relative_path
        assert "bailian_model" in source, relative_path


def test_obsolete_batch_ozone_report_script_is_removed():
    assert not (REPO_ROOT / "backend/scripts/batch_ozone_report_processor.py").exists()


def test_ocr_adapter_keeps_mimo_on_openai_protocol(tmp_path, monkeypatch):
    from app.services.ops_audit.semantic import ocr_adapter

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-bytes")
    captured = {}

    def fake_openai_call(**kwargs):
        captured.update(kwargs)
        return "Mimo结果", {"choices": [{"message": {"content": "Mimo结果"}}]}

    monkeypatch.setattr(ocr_adapter, "_call_openai_vision_sync", fake_openai_call)

    result = ocr_adapter._call_vision_model(
        str(image_path),
        target={
            "provider": "mimo",
            "model": "mimo-v2.5",
            "base_url": "https://mimo.example/v1",
            "api_key": "mimo-key",
        },
        mode="flow_visual",
        prompt="识别图片",
        task="flow",
    )

    assert result["status"] == "success"
    assert result["text"] == "Mimo结果"
    assert captured["base_url"] == "https://mimo.example/v1"


@pytest.mark.parametrize(
    ("tier", "chain", "expected_model"),
    [
        ("pro", "bailian/deepseek-v4-pro,minimax/MiniMax-M3", "deepseek-v4-pro"),
        ("flash", "bailian/qwen3.6-flash,minimax/MiniMax-M3", "qwen3.6-flash"),
    ],
)
def test_model_tiers_select_bailian_first(monkeypatch, tier, chain, expected_model):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "bailian_api_key", "bailian-key")
    monkeypatch.setattr(settings, f"llm_{tier}_models", chain)

    service = LLMService()

    with service.use_model_tier(tier):
        assert service.provider == "bailian"
        assert service.model == expected_model
        assert service.request_fallbacks == "minimax/MiniMax-M3"


def test_bailian_multimodal_uses_native_anthropic_image_blocks(monkeypatch):
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="识别结果")],
                model_dump=lambda: {"content": [{"type": "text", "text": "识别结果"}]},
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.messages = FakeMessages()

        def close(self):
            return None

    monkeypatch.setattr(bailian_multimodal, "Anthropic", FakeAnthropic)

    text, _ = bailian_multimodal.call_bailian_vision_sync(
        image_url="data:image/png;base64,YWJj",
        prompt="识别文字",
        api_key="secret",
        base_url="https://bailian.example/apps/anthropic",
        model="qwen3.8-max-preview",
        timeout=30,
    )

    assert text == "识别结果"
    assert captured["request"]["messages"][0]["content"][0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "YWJj"},
    }


def test_bailian_multimodal_normalizes_jpg_and_bmp_media_types():
    jpg = bailian_multimodal.build_anthropic_image_block(
        "data:image/jpg;base64,YWJj"
    )
    assert jpg["source"]["media_type"] == "image/jpeg"

    image = Image.new("RGB", (2, 2), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    bmp_data = base64.b64encode(buffer.getvalue()).decode("ascii")

    bmp = bailian_multimodal.build_anthropic_image_block(
        f"data:image/bmp;base64,{bmp_data}"
    )

    assert bmp["source"]["media_type"] == "image/png"
    assert base64.b64decode(bmp["source"]["data"]).startswith(b"\x89PNG")


def test_default_multimodal_chain_keeps_existing_fallbacks_after_bailian(monkeypatch):
    monkeypatch.delenv("LLM_MULTIMODAL_MODELS", raising=False)
    defaults = Settings(_env_file=None)

    assert defaults.llm_multimodal_models == (
        "bailian/qwen3.8-max-preview,mimo/mimo-v2-pro,"
        "agnes/agnes-2.0-flash,minimax/MiniMax-M3"
    )


@pytest.mark.asyncio
async def test_document_processor_routes_online_text_to_bailian(monkeypatch):
    from app.knowledge_base import document_processor

    captured = {}

    class FakeLLMService:
        async def chat_anthropic(self, **kwargs):
            captured.update(kwargs)
            return {
                "content": [SimpleNamespace(type="text", text='[{"title":"片段"}]')]
            }

    monkeypatch.setattr(document_processor, "ONLINE_LLM_PROVIDER", "bailian")
    monkeypatch.setattr(document_processor, "llm_service", FakeLLMService())
    processor = document_processor.DocumentProcessor.__new__(
        document_processor.DocumentProcessor
    )

    result = await processor._call_online_llm("请分块")

    assert result == '[{"title":"片段"}]'
    assert captured["messages"] == [{"role": "user", "content": "请分块"}]
    assert captured["system"] == "你是文档分析助手。直接返回JSON，不要解释。"


def test_all_qwen_visual_runtimes_are_migrated_to_bailian():
    runtime_files = [
        "backend/app/fetchers/quick_trace/quick_trace_fetcher.py",
        "backend/app/knowledge_base/document_processor.py",
        "backend/app/services/tenders/llm.py",
        "backend/app/tools/query/get_weather_situation_map/tool.py",
        "backend/app/tools/utility/analyze_image_tool.py",
        "backend/app/tools/utility/parse_pdf_tool.py",
    ]
    for relative_path in runtime_files:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "QWEN_" not in source, relative_path
        assert "qwen_vl" not in source.lower(), relative_path
        assert "qwen-vl" not in source.lower(), relative_path
        assert "dashscope.aliyuncs.com/compatible-mode" not in source, relative_path

    for relative_path in runtime_files[1:]:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "BAILIAN_" in source or "bailian" in source.lower(), relative_path


def test_env_templates_document_bailian_mode_priorities():
    for relative_path in [
        "backend/.env.example",
        "backend/.env.template",
        "backend/.env.production.template",
    ]:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "LLM_PROVIDER=bailian" in source
        assert "BAILIAN_MODEL=qwen3.8-max-preview" in source
        assert "LLM_FLASH_MODELS=bailian/qwen3.6-flash" in source
        assert "LLM_PRO_MODELS=bailian/deepseek-v4-pro" in source
        assert "LLM_MULTIMODAL_MODELS=bailian/qwen3.8-max-preview" in source
        assert "QWEN_VL_API_KEY" not in source


def test_legacy_text_qwen_runtime_branches_are_removed():
    backend_root = Path(__file__).resolve().parents[1]
    for relative_path in [
        "app/routers/knowledge_qa.py",
        "app/agent/core/planner.py",
    ]:
        source = (backend_root / relative_path).read_text(encoding="utf-8")
        assert 'provider == "qwen"' not in source

    proxy_source = (backend_root / "app/proxy_server.py").read_text(
        encoding="utf-8"
    )
    assert "API_BASE_URL" not in proxy_source
    assert "chat/completions" not in proxy_source


def test_llm_service_loads_deepseek_api_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    service = LLMService()

    assert service.provider == "deepseek"
    assert service.api_mode == "chat_completions"
    assert service.anthropic_client is None
    assert service.base_url == "http://ds.local.ai:30080/compatible-mode/v1"


@pytest.mark.asyncio
async def test_chat_anthropic_uses_chat_completions_when_api_mode_enabled(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "DeepSeek-V4-Flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "reasoning_content": "fast reasoning",
                            "content": "你好",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "你好"}],
        tools=None,
        temperature=0.2,
        system="你是助手",
    )

    assert captured["url"] == (
        "http://ds.local.ai:30080/compatible-mode/v1/chat/completions"
    )
    assert captured["authorization"] == "Bearer api-key"
    assert captured["json"]["model"] == "DeepSeek-V4-Flash"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert captured["json"]["stream"] is False
    assert result["content"] == [
        {"type": "thinking", "thinking": "fast reasoning"},
        {"type": "text", "text": "你好"},
    ]
    assert result["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_chat_anthropic_streaming_uses_chat_completions_events(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    captured = {}
    stream_body = (
        'data: {"choices":[{"delta":{"reasoning_content":"Need"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"你好"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":4}}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, content=stream_body.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    events = [
        event
        async for event in service.chat_anthropic_streaming(
            messages=[{"role": "user", "content": "你好"}],
            tools=None,
            temperature=0.2,
            system="你是助手",
        )
    ]

    assert captured["url"] == (
        "http://ds.local.ai:30080/compatible-mode/v1/chat/completions"
    )
    assert captured["json"]["stream"] is True
    assert captured["json"]["stream_options"] == {"include_usage": True}
    assert events[0]["type"] == "message_start"
    assert any(event["type"] == "content_block_delta" for event in events)
    assert events[-2] == {
        "type": "message_delta",
        "data": {"stop_reason": "end_turn", "usage": {"output_tokens": 4}},
    }
    assert events[-1] == {"type": "message_stop", "data": {}}


def test_env_example_documents_deepseek_v4_chat_completions():
    env_example = (REPO_ROOT / "backend/.env.example").read_text(encoding="utf-8")

    assert "DEEPSEEK_API_MODE=chat_completions" in env_example
    assert "DEEPSEEK_BASE_URL=http://ds.local.ai:30080/compatible-mode/v1" in env_example
    assert "DEEPSEEK_MODEL=DeepSeek-V4-Flash" in env_example
    assert "MDDEEPSEEK25FF2F3E5E17" in env_example


def test_chat_completions_payload_uses_tool_choice_without_prompt_guardrails(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "glm_api_key", "api-key")
    monkeypatch.setattr(settings, "glm_model", "glm-4.7")

    service = LLMService()
    payload = service._build_chat_completions_payload(
        messages=[{"role": "user", "content": "生成图表"}],
        tools=[
            {
                "name": "create_report_chart",
                "description": "Create a chart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["title", "data"],
                },
            }
        ],
        max_tokens=1024,
        temperature=0.2,
        system="你是助手",
        stream=True,
    )

    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["function"]["name"] == "create_report_chart"
    assert payload["messages"][0] == {"role": "system", "content": "你是助手"}


@pytest.mark.asyncio
async def test_chat_completions_retries_malformed_tool_arguments_with_named_tool_choice(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "glm_base_url", "https://open.bigmodel.cn/api/coding/paas/v4")
    monkeypatch.setattr(settings, "glm_api_key", "api-key")
    monkeypatch.setattr(settings, "glm_model", "glm-4.7")

    captured_payloads = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured_payloads.append(payload)
        if len(captured_payloads) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "glm-4.7",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "call_bad",
                                        "type": "function",
                                        "function": {
                                            "name": "create_report_chart",
                                            "arguments": "{",
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "glm-4.7",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_ok",
                                    "type": "function",
                                    "function": {
                                        "name": "create_report_chart",
                                        "arguments": '{"title":"AQI","data":{}}',
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6},
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "生成图表"}],
        tools=[
            {
                "name": "create_report_chart",
                "description": "Create a chart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["title", "data"],
                },
            }
        ],
        temperature=0.2,
        system="你是助手",
    )

    assert len(captured_payloads) == 2
    assert captured_payloads[0]["tool_choice"] == "auto"
    assert captured_payloads[0]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert captured_payloads[1]["tool_choice"] == {
        "type": "function",
        "function": {"name": "create_report_chart"},
    }
    assert captured_payloads[1]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert result["stop_reason"] == "tool_use"
    assert result["content"][0].type == "tool_use"
    assert result["content"][0].input == {"title": "AQI", "data": {}}
