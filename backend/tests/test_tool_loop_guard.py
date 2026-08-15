"""ToolLoopGuard unit tests."""

import importlib.util
import sys


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_guard_path = "/home/xckj/suyuan/backend/app/agent/runtime/tool_loop_guard.py"
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
