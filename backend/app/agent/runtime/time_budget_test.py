"""TimeBudget 决策器单测（v3：时间预算 + 原地续跑 + 空转熔断）。

场景依据 js_ops_risk_202610 失败复盘：alarm 域 10 轮做完取数+图后被轮次上限
截断（应有进展续跑）；rates 域取数完成后 8 轮纯文本零工具调用（应空转熔断）。
"""

from app.agent.runtime.time_budget import (
    TERMINATION_EXTENDED_TIMEOUT,
    TERMINATION_STALLED_NO_PROGRESS,
    TimeBudget,
    TimeBudgetSpec,
)

T0 = 100.0


def make_budget(**overrides) -> TimeBudget:
    params = dict(
        soft=420.0, hard=900.0, extend_step=180.0,
        finalize_margin=60.0, stall_prompt_turns=2,
        stall_seconds=60.0, finalize_window=90.0,
    )
    params.update(overrides)
    budget = TimeBudget(spec=TimeBudgetSpec(
        soft_seconds=params["soft"],
        hard_seconds=params["hard"],
        extend_step=params["extend_step"],
        finalize_margin=params["finalize_margin"],
        stall_prompt_turns=params["stall_prompt_turns"],
        stall_seconds=params["stall_seconds"],
        finalize_window=params["finalize_window"],
    ))
    budget.started_at = T0
    budget.deadline = T0 + params["soft"]
    budget.last_tool_at = T0
    return budget


def test_progressful_slow_task_extends_until_hard_cap_then_finalizes():
    budget = make_budget()
    decision = budget.check(T0 + 10)
    assert decision.action == "continue" and decision.prompt is None and not decision.extended

    for t in (100, 200, 300, 400):
        budget.on_turn_end(True, T0 + t)

    # 软预算到点、近期有工具调用 → 原地续跑（420 → 600 → 780 → 900 封顶）
    decision = budget.check(T0 + 425)
    assert decision.action == "continue" and decision.extended
    assert budget.deadline == T0 + 600.0
    budget.on_turn_end(True, T0 + 590)

    decision = budget.check(T0 + 610)
    assert decision.action == "continue" and decision.extended
    assert budget.deadline == T0 + 780.0
    budget.on_turn_end(True, T0 + 780)

    decision = budget.check(T0 + 790)
    assert decision.action == "continue" and decision.extended
    assert budget.deadline == T0 + 900.0  # 续跑不越过硬上限

    # 距硬上限不足 finalize_margin → 收尾提示（注入给模型），窗口内安静
    decision = budget.check(T0 + 850)
    assert decision.action == "continue" and decision.prompt and "停止" in decision.prompt
    decision = budget.check(T0 + 880)
    assert decision.action == "continue" and decision.prompt is None

    # 收尾窗口过完 → 终止，原因 extended_timeout
    decision = budget.check(T0 + 950)
    assert decision.action == "stop"
    assert decision.reason == TERMINATION_EXTENDED_TIMEOUT


def test_stalled_task_prompts_once_then_finalizes_as_stalled():
    budget = make_budget()
    budget.on_turn_end(False, T0 + 5)
    budget.on_turn_end(False, T0 + 10)

    # 连续 2 轮无工具调用 → 推进提示，且同一空转序列只提示一次
    decision = budget.check(T0 + 15)
    assert decision.action == "continue" and decision.prompt and "工具" in decision.prompt
    budget.on_turn_end(False, T0 + 20)
    decision = budget.check(T0 + 25)
    assert decision.action == "continue" and decision.prompt is None

    # 软预算到点且空转（last_tool_at 距今 ≥ stall_seconds）→ 空转收尾而非续跑
    decision = budget.check(T0 + 425)
    assert decision.action == "continue" and decision.prompt and "停止" in decision.prompt
    decision = budget.check(T0 + 520)
    assert decision.action == "stop"
    assert decision.reason == TERMINATION_STALLED_NO_PROGRESS


def test_tool_call_resets_stall_state():
    budget = make_budget()
    budget.on_turn_end(False, T0 + 5)
    budget.on_turn_end(False, T0 + 10)
    decision = budget.check(T0 + 15)
    assert decision.prompt is not None
    budget.on_turn_end(True, T0 + 20)  # 恢复工具调用
    decision = budget.check(T0 + 25)
    assert decision.prompt is None
    assert budget.consecutive_no_tool == 0


def test_from_runtime_metadata_parses_and_falls_back():
    budget = TimeBudget.from_runtime_metadata(
        {"time_budget": {"soft_seconds": 300, "hard_seconds": 800}}
    )
    assert budget is not None
    assert budget.spec.soft_seconds == 300 and budget.spec.hard_seconds == 800

    fallback = TimeBudget.from_runtime_metadata({"time_budget": {"soft_seconds": "bad"}})
    assert fallback.spec.soft_seconds == 420.0

    assert TimeBudget.from_runtime_metadata(None) is None
    assert TimeBudget.from_runtime_metadata({}) is None
    assert TimeBudget.from_runtime_metadata({"time_budget": None}) is None
