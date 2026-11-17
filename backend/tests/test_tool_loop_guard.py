"""ToolLoopGuard unit tests."""

import importlib.util
from pathlib import Path
import sys


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_guard_path = str(Path(__file__).resolve().parents[1] / "app/agent/runtime/tool_loop_guard.py")
_guard = _load_module("tool_loop_guard", _guard_path)

ToolLoopGuard = _guard.ToolLoopGuard


def test_first_repeated_call_is_allowed():
    guard = ToolLoopGuard()
    assert guard.before_call("read_file", {"path": "/tmp/a"}) is None
    assert guard.before_call("read_file", {"path": "/tmp/a"}) is None


def test_soft_browser_tools_only_warn():
    guard = ToolLoopGuard()
    assert guard.before_call("snapshot", {"format": "ai"}) is None
    assert guard.before_call("snapshot", {"format": "ai"}) is None
    result = guard.before_call("snapshot", {"format": "ai"})
    assert result["severity"] == "warning"
    assert result["loop_guard"] is True
    assert result["success"] is False


def test_hard_tools_eventually_block():
    guard = ToolLoopGuard()
    assert guard.before_call("navigate", {"url": "https://example.com"}) is None
    assert guard.before_call("navigate", {"url": "https://example.com"}) is None
    result = None
    for _ in range(4):
        result = guard.before_call("navigate", {"url": "https://example.com"})
        if result is not None:
            break
    assert result is not None
    assert result["severity"] in {"warning", "block"}

    while result and result["severity"] != "block":
        result = guard.before_call("navigate", {"url": "https://example.com"})
    assert result["severity"] == "block"
    assert result["loop_guard"] is True


def test_normal_tool_warns_at_3_blocks_at_5():
    guard = ToolLoopGuard()
    args = {"station": "A001"}
    assert guard.before_call("query_noise", args) is None
    assert guard.before_call("query_noise", args) is None
    assert guard.before_call("query_noise", args)["severity"] == "warning"
    assert guard.before_call("query_noise", args)["severity"] == "warning"
    assert guard.before_call("query_noise", args)["severity"] == "block"


def test_alternating_calls_do_not_accumulate_streak():
    """连击制：不同调用穿插时计数重置，不应触发警告（对齐 ZCode 语义）。"""
    guard = ToolLoopGuard()
    a = {"path": "/tmp/a"}
    b = {"path": "/tmp/b"}
    for _ in range(6):
        assert guard.before_call("read_file", a) is None
        assert guard.before_call("read_file", b) is None


def test_reset_clears_streak_after_user_input():
    """用户 steer 后 reset：明确指示下的重试不受罚。"""
    guard = ToolLoopGuard()
    args = {"path": "/tmp/a"}
    guard.before_call("read_file", args)
    guard.before_call("read_file", args)
    guard.reset()
    assert guard.before_call("read_file", args) is None
    assert guard.before_call("read_file", args) is None
    # reset 只清连击，不清结果缓存
    assert guard._last_results == {}


def test_block_includes_last_result_excerpt_and_guidance():
    """block 附带上次真实结果摘要与行动指引，避免错误结果诱发原样重试。"""
    guard = ToolLoopGuard()
    args = {"station": "A001"}
    guard.before_call("query_noise", args)
    guard.record_result("query_noise", args, {"success": True, "rows": 42, "data": "x" * 3000})
    for _ in range(4):
        guard.before_call("query_noise", args)
    blocked = guard.before_call("query_noise", args)
    assert blocked["severity"] == "block"
    assert blocked["last_result_excerpt"] is not None
    assert "rows" in blocked["last_result_excerpt"]
    # 超长结果被截断
    assert len(blocked["last_result_excerpt"]) <= _guard.LAST_RESULT_EXCERPT_LIMIT + 20
    # 行动指引：禁止原样重试 + 三选一去向
    summary = blocked["summary"]
    assert "请勿重试" in summary or "禁止" in summary
    assert "last_result_excerpt" in summary
    assert "向用户" in summary


def test_block_without_recorded_result_still_guides():
    guard = ToolLoopGuard()
    args = {"path": "/tmp/a"}
    for _ in range(5):
        guard.before_call("read_file", args)
    blocked = guard.before_call("read_file", args)
    assert blocked["severity"] == "block"
    assert blocked["last_result_excerpt"] is None
    assert "更换参数" in blocked["summary"]
