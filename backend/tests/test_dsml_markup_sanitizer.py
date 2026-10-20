"""DSML tool-call markup must never reach the user-facing answer."""

from types import SimpleNamespace

import pytest

from app.agent.markup_sanitizer import (
    DSML_TOOL_CALL_BLOCKED_NOTICE,
    strip_dsml_tool_call_markup,
)


def test_strip_removes_full_invoke_block():
    text = (
        "结论先行。\n\n<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name=\"execute_python\">\n"
        "<｜｜DSML｜｜ parameter name=\"input_files\" string=\"false\">"
        "$$\"/tmp/weather.json\"$$</｜｜DSML｜｜ parameter>\n"
        "<｜｜DSML｜｜ parameter name=\"code\" string=\"true\">$$import json$$"
        "</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>"
    )
    cleaned, changed = strip_dsml_tool_call_markup(text)
    assert changed
    assert "DSML" not in cleaned
    assert "import json" not in cleaned
    assert "weather.json" not in cleaned
    assert "结论先行。" in cleaned


def test_strip_pure_markup_falls_back_to_notice():
    text = (
        "<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name=\"execute_python\">\n"
        "</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>"
    )
    cleaned, changed = strip_dsml_tool_call_markup(text)
    assert changed
    assert cleaned == ""
    assert DSML_TOOL_CALL_BLOCKED_NOTICE


def test_normal_answer_is_untouched():
    text = "未来三天许昌以晴为主，最高气温 22℃。<｜table｜>"
    cleaned, changed = strip_dsml_tool_call_markup(text)
    assert not changed
    assert cleaned == text


def test_empty_and_none_inputs():
    assert strip_dsml_tool_call_markup("") == ("", False)
    assert strip_dsml_tool_call_markup(None) == (None, False)


@pytest.mark.parametrize("tail", [
    '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="execute_python"><｜｜DSML｜｜ parameter name="code">PRIVATE_CODE',
    '<｜｜DSML｜｜ invoke name="execute_python">PRIVATE_CODE',
    '<｜｜DSML｜｜ parameter name="code">PRIVATE_CODE',
    '<｜｜DSML｜｜ invoke name="execute_python"',
    '<｜｜DS',
])
def test_truncated_tool_calls_drop_payload_and_partial_marker(tail):
    assert strip_dsml_tool_call_markup("结论。" + tail) == ("结论。", True)


@pytest.mark.parametrize("text", ["", "   ", "DSML is a format\n\n\n", "a < b", "<p>正文</p>", "<｜table｜>"])
def test_unrelated_text_is_unchanged(text):
    assert strip_dsml_tool_call_markup(text) == (text, False)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("text", ["", '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>'])
def test_planner_empty_reply_and_pure_tool_markup(streaming, text):
    from app.agent.core.planner import ReActPlanner

    planner = ReActPlanner.__new__(ReActPlanner)
    if streaming:
        result = planner._parse_accumulated_blocks([{"type": "text", "text": text}])
    else:
        result = planner._parse_anthropic_response({"content": [SimpleNamespace(type="text", text=text)]})
    assert result["action"]["answer"] == (DSML_TOOL_CALL_BLOCKED_NOTICE if text else "")


@pytest.mark.parametrize("opening,closing", [("<", ">"), ("＜", "＞")])
@pytest.mark.parametrize("truncated", [False, True])
def test_runtime_stream_filters_every_chunk_boundary(opening, closing, truncated):
    from app.agent.runtime.assistant_stream_buffer import AssistantStreamBuffer

    text = (f'前文。{opening}｜｜DSML｜｜ calls{closing}'
            f'{opening}｜｜DSML｜｜ invoke name="execute_python"{closing}'
            f'{opening}｜｜DSML｜｜ parameter name="code"{closing}PRIVATE_CODE')
    if not truncated:
        text += (f'{opening}/｜｜DSML｜｜ parameter{closing}'
                 f'{opening}/｜｜DSML｜｜ invoke{closing}'
                 f'{opening}/｜｜DSML｜｜ calls{closing}后文。')
    expected = "前文。" if truncated else "前文。后文。"
    chunkings = [[text[:i], text[i:]] for i in range(len(text) + 1)] + [list(text)]
    for chunks in chunkings:
        buffer = AssistantStreamBuffer()
        visible = "".join(buffer.append(chunk) for chunk in chunks) + buffer.flush()
        assert visible == expected
        assert buffer.visible_text == expected
        assert buffer.final_text() == expected


def test_runtime_stream_preserves_html_and_stops_after_real_tool_use():
    from app.agent.runtime.assistant_stream_buffer import AssistantStreamBuffer

    buffer = AssistantStreamBuffer()
    assert buffer.append("普通 <") == "普通 "
    assert buffer.append("b>文本</b>") == "<b>文本</b>"
    assert buffer.append(" <") == " "
    assert buffer.flush() == "<"
    buffer.note_tool_use()
    assert buffer.append("internal tool plan") == ""
    assert buffer.flush() == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", "已有结论。"])
async def test_finalizer_persists_and_emits_only_clean_answer(monkeypatch, prefix):
    from app.agent.runtime import finalizer as module
    from app.agent.runtime.event_bus import RuntimeEventBus
    from app.agent.runtime.types import RunState

    async def identity(text, session_id):
        return text

    monkeypatch.setattr(module, "normalize_chart_placeholders", identity)
    if hasattr(module, "resolve_chart_alias_markers"):
        monkeypatch.setattr(module, "resolve_chart_alias_markers", identity)
    written = []
    writer = SimpleNamespace(add_final_assistant_message=lambda state, *args, **kwargs: written.append(state.response_text))
    finalizer = module.Finalizer(writer, RuntimeEventBus())
    state = RunState(session_id="session-test", user_query="test", mode="assistant")
    events = [event async for event in finalizer.complete(
        state, prefix + '<｜｜DSML｜｜ invoke name="execute_python">PRIVATE_CODE',
    )]
    expected = prefix or DSML_TOOL_CALL_BLOCKED_NOTICE
    assert written == [expected]
    assert state.response_text == expected
    assert "".join(event["data"].get("chunk", "") for event in events if event["type"] == "streaming_text") == expected
    assert events[-1]["type"] == "complete"
