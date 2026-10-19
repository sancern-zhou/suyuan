"""DSML tool-call markup must never reach the user-facing answer."""

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
