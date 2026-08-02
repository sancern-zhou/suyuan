import asyncio
from unittest.mock import Mock, patch

import pytest

from app.agent.context.context_builder import (
    MESSAGE_CONTEXT_LAYER_ORDER,
    SYSTEM_CONTEXT_LAYER_ORDER,
    SimplifiedContextBuilder,
)
from app.agent.context.context_diagnostics import ContextDiagnostics
from app.agent.memory.context_compressor import ContextCompressor


def _layer_position(prompt: str, name: str) -> int:
    return prompt.index(f'<context_layer name="{name}"')


def test_system_context_uses_one_explicit_precedence_order():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "assistant"
    builder.selected_skill_context = "skill-marker"
    builder.fixed_policy_context = "policy-marker"
    builder.acceptance_context = "acceptance-marker"
    builder.session_resource_context = "resource-marker"
    builder.memory_context = "memory-marker"

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ) as build_mode_prompt:
        prompt = builder._build_system_prompt()

    present_layers = list(SYSTEM_CONTEXT_LAYER_ORDER)
    assert [_layer_position(prompt, name) for name in present_layers] == sorted(
        _layer_position(prompt, name) for name in present_layers
    )
    for marker in (
        "mode-marker",
        "skill-marker",
        "policy-marker",
        "acceptance-marker",
        "resource-marker",
        "memory-marker",
    ):
        assert prompt.count(marker) == 1

    kwargs = build_mode_prompt.call_args.kwargs
    assert kwargs["memory_context"] is None
    assert kwargs["user_context"] is None
    assert kwargs["heartbeat_context"] is None
    assert kwargs["board_context"] is None
    assert [item["name"] for item in builder.last_context_layers] == list(
        SYSTEM_CONTEXT_LAYER_ORDER
    )


def test_board_state_is_only_in_the_session_resources_layer():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "board"
    builder.board_context = {"current_xml": "board-state-marker"}

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ) as build_mode_prompt:
        prompt = builder._build_system_prompt()

    assert prompt.count("board-state-marker") == 1
    assert _layer_position(prompt, "mode_policy") < _layer_position(prompt, "session_resources")
    assert build_mode_prompt.call_args.kwargs["board_context"] is None


def test_social_profile_and_memory_are_not_hidden_in_mode_prompt():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "social"
    builder.user_context = "user-profile-marker"
    builder.memory_context = "memory-marker"

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ) as build_mode_prompt:
        prompt = builder._build_system_prompt()

    assert prompt.count("user-profile-marker") == 1
    assert prompt.count("memory-marker") == 1
    assert _layer_position(prompt, "mode_policy") < _layer_position(prompt, "long_term_memory")
    assert build_mode_prompt.call_args.kwargs["user_context"] is None
    assert build_mode_prompt.call_args.kwargs["memory_context"] is None


@pytest.mark.parametrize("mode", [
    "assistant",
    "ppt",
    "expert",
    "query",
    "report",
    "social",
    "chart",
    "board",
    "ops",
    "graph",
    "custom",
    "memory_consolidator",
    "deliberation_meteorology",
    "deliberation_monitoring",
    "deliberation_chemistry",
    "deliberation_reviewer",
])
def test_long_term_memory_uses_the_same_layer_in_every_mode(mode):
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = mode
    builder.memory_context = "cross-mode-memory-marker"

    prompt = builder._build_system_prompt()

    assert prompt.count("cross-mode-memory-marker") == 1
    assert _layer_position(prompt, "mode_policy") < _layer_position(
        prompt, "long_term_memory"
    )


def test_compacted_history_places_summary_before_anchor_and_recent_messages():
    llm_client = Mock()

    async def _chat(**_kwargs):
        return "summary-marker"

    llm_client.chat = _chat
    compressor = ContextCompressor(llm_client)
    messages = []
    for index in range(6):
        messages.extend([
            {"type": "user", "role": "user", "content": f"user-{index}"},
            {"type": "assistant", "role": "assistant", "content": f"assistant-{index}"},
        ])
    anchor = [{"type": "user", "role": "user", "content": "anchor-marker"}]

    result = asyncio.run(compressor._harness_compact(
        messages_to_compress=messages,
        protected_messages=[],
        anchor_messages=anchor,
        original_count=len(messages),
    ))

    assert result[0]["type"] == "compact_memory"
    assert "summary-marker" in result[0]["content"]
    assert result[1]["content"] == "anchor-marker"


def test_fallback_compaction_boundary_precedes_anchor_and_recent_messages():
    compressor = ContextCompressor(Mock())
    anchor = [{"type": "user", "role": "user", "content": "anchor-marker"}]
    messages = [
        {"type": "user", "role": "user", "content": f"user-{index}"}
        for index in range(8)
    ]

    result = compressor._fallback_compact(
        messages=messages,
        anchor_messages=anchor,
        original_count=len(messages),
        error=RuntimeError("forced"),
    )

    assert result[0]["type"] == "system"
    assert result[1]["content"] == "anchor-marker"


def test_context_diagnostics_reports_layer_metadata_without_bodies():
    layers = [{"name": "platform_policy", "priority": 1, "chars": 120, "tokens": 30}]
    report = ContextDiagnostics().build_report(
        mode="assistant",
        iteration=1,
        context_tokens={"total": 10},
        tool_schemas=[],
        conversation_history=[],
        context_layers=layers,
    )

    assert report["context_layers"] == layers


def test_context_result_reports_summary_then_recent_messages_then_current_turn():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    history = [
        {
            "type": "compact_memory",
            "role": "user",
            "content": "summary",
            "metadata": {"compact_memory": True},
        },
        {"type": "assistant", "role": "assistant", "content": "recent"},
    ]

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ):
        result = asyncio.run(builder.build_for_thought_action(
            query="current",
            iteration=1,
            conversation_history=history,
            mode="assistant",
        ))

    message_layers = [
        item for item in result["context_layers"] if item["scope"] == "messages"
    ]
    assert [item["name"] for item in message_layers] == list(MESSAGE_CONTEXT_LAYER_ORDER)
    assert all(item["active"] for item in message_layers)


def test_first_planner_turn_keeps_query_and_current_turn_attachment_facts():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_turn_resource_context = (
        "1. index (1).html\n"
        "   资源 ID: html-resource\n"
        "   类型: text/html\n"
        "   路径: backend_data_registry/uploads/index.html"
    )

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ):
        result = asyncio.run(builder.build_for_thought_action(
            query="阅读",
            iteration=1,
            conversation_history=[
                {"type": "assistant", "role": "assistant", "content": "older turn"},
            ],
            mode="assistant",
        ))

    conversation = result["user_conversation"]
    assert "## 当前进行的任务\n阅读" in conversation
    assert "## 本轮用户附件" in conversation
    assert "index (1).html" in conversation
    assert "html-resource" in conversation


def test_later_planner_iterations_do_not_repeat_current_turn_attachment_facts():
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_turn_resource_context = "1. index (1).html"

    with patch(
        "app.agent.prompts.prompt_builder.build_react_system_prompt",
        return_value="mode-marker",
    ):
        result = asyncio.run(builder.build_for_thought_action(
            query="阅读",
            iteration=2,
            conversation_history=[
                {"type": "user", "role": "user", "content": "阅读"},
            ],
            mode="assistant",
        ))

    assert "本轮用户附件" not in result["user_conversation"]
    assert "index (1).html" not in result["user_conversation"]
