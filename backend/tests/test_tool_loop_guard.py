"""ToolLoopGuard unit tests（对齐 ZCode：只观察+提醒注入，从不拦截）。"""

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


def test_warning_fires_only_at_threshold_point():
    """每连击仅在阈值点（第 3 次）触发一次，第 4、5 次不再触发。"""
    guard = ToolLoopGuard()
    args = {"path": "/tmp/a"}
    assert guard.before_call("read_file", args) is None
    assert guard.before_call("read_file", args) is None
    warning = guard.before_call("read_file", args)
    assert warning is not None
    assert warning["severity"] == "warning"
    assert warning["repeated"] == 3
    assert warning["reminder_injected"] is True
    assert guard.before_call("read_file", args) is None
    assert guard.before_call("read_file", args) is None


def test_never_blocks_any_tool():
    """任何工具、任意次数的重复调用都不产生 block——工具照常执行。"""
    guard = ToolLoopGuard()
    args = {"url": "https://example.com"}
    for _ in range(20):
        outcome = guard.before_call("browser", args)
        assert outcome is None or outcome["severity"] == "warning"


def test_alternating_calls_do_not_accumulate_streak():
    """连击制：不同调用穿插时计数重置，不应触发警告。"""
    guard = ToolLoopGuard()
    a = {"path": "/tmp/a"}
    b = {"path": "/tmp/b"}
    for _ in range(6):
        assert guard.before_call("read_file", a) is None
        assert guard.before_call("read_file", b) is None


def test_reset_clears_streak_after_user_input():
    """用户 steer 后 reset：明确指示下的重试不受罚（注入预算不重置）。"""
    guard = ToolLoopGuard()
    args = {"path": "/tmp/a"}
    guard.before_call("read_file", args)
    guard.before_call("read_file", args)
    guard.reset()
    assert guard.before_call("read_file", args) is None
    assert guard.before_call("read_file", args) is None


def test_drain_pending_reminders_returns_and_clears():
    guard = ToolLoopGuard()
    args = {"station": "A001"}
    for _ in range(3):
        guard.before_call("query_noise", args)
    reminders = guard.drain_pending_reminders()
    assert len(reminders) == 1
    assert "query_noise" in reminders[0]
    assert "完全相同的参数连续调用 3 次" in reminders[0]
    assert "不要再次发起完全相同的调用" in reminders[0]
    assert guard.drain_pending_reminders() == []


def test_injection_budget_per_turn():
    """每回合最多注入 3 条提醒：第 4 个连击只记日志（reminder_injected=False）。"""
    guard = ToolLoopGuard()
    for i in range(4):
        args = {"index": i}
        guard.before_call("read_file", args)  # 第 1 次（建签名）
        guard.before_call("read_file", args)
        warning = guard.before_call("read_file", args)
        assert warning is not None
        expected_injected = i < 3
        assert warning["reminder_injected"] is expected_injected
    assert len(guard.drain_pending_reminders()) == 3


def test_reminder_carries_redirection_hint():
    """改道指引随提醒注入（委派轮询场景）。"""
    guard = ToolLoopGuard()
    args = {"action": "get", "run_id": "g1"}
    for _ in range(3):
        guard.before_call("manage_assistant_runs", args)
    (reminder,) = guard.drain_pending_reminders()
    assert "wait_seconds" in reminder
    assert "改道" in reminder
