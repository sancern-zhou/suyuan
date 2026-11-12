"""子 Agent 墙钟时间预算与原地续跑决策器（2026-11-12 v3 方案）。

设计（projects/jiangsu-ops/docs/operations-analysis-dag-fix-plan-20261112.md）：
- 轮次不是工作量单位（同样 10 轮实测 115-290s），自由 agent 节点取消轮次硬限，
  只保留墙钟时间预算；token 由时间约束（LLM 每轮有物理耗时下限）。
- 预算耗尽 ≠ 失败：时间到且有进展 → 原地续跑（同实例、上下文不动、延长 deadline），
  只有真失败（异常/校验失败）才走重试路径。
- 空转是主要浪费源（rates 域 8 轮纯文本零工具调用），时间预算之外加无进展熔断：
  连续多轮无工具调用先提示，持续无产物则强制收尾交付（salvage 语义）。

决策器是纯同步逻辑、无 IO，便于单测；由 AgentRuntime 主循环在两轮之间调用，
不打断进行中的工具调用（原地续跑的前提）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

# 终态原因：写进 complete 事件 reason 与子 Agent 返回 metadata，
# coordinator 据此区分"预算耗尽（不重试）"与"真失败（可重试）"。
TERMINATION_EXTENDED_TIMEOUT = "extended_timeout"
TERMINATION_STALLED_NO_PROGRESS = "stalled_no_progress"
NON_RETRYABLE_TERMINATIONS = frozenset({TERMINATION_EXTENDED_TIMEOUT, TERMINATION_STALLED_NO_PROGRESS})

STALL_PROMPT = (
    "进度提醒：已连续多轮未调用任何工具。请立即执行下一步工具操作"
    "（取数、execute_python 落盘统计表/图表，或交付）。不要输出纯分析文本空转。"
)
FINALIZE_PROMPT = (
    "时间预算即将用尽：立即停止新的取数与展开性分析，"
    "用已取得的全部数据完成统计表与图表落盘，并以最终回复交付结论与文件路径清单。"
    "未完成部分如实标注，不要重新查询已有来源。"
)


@dataclass(frozen=True)
class TimeBudgetSpec:
    """时间预算配置（由工作流执行器按节点计算，经 runtime_metadata 下发）。"""

    soft_seconds: float = 420.0      # 首段预算；到点后有进展则续跑
    hard_seconds: float = 900.0      # 节点墙钟总上限（含全部续跑）
    extend_step: float = 180.0       # 每次续跑延长
    finalize_margin: float = 60.0    # 距硬上限剩多少时进入收尾
    stall_prompt_turns: int = 2      # 连续无工具调用多少轮后提示
    stall_seconds: float = 60.0      # 无工具调用持续多久判空转
    finalize_window: float = 90.0    # 收尾提示后的交付窗口

    @classmethod
    def from_config(cls, config: Any) -> Optional["TimeBudgetSpec"]:
        if not isinstance(config, dict) or not config:
            return None

        def _num(key: str, default: float) -> float:
            try:
                value = float(config.get(key))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        return cls(
            soft_seconds=_num("soft_seconds", 420.0),
            hard_seconds=_num("hard_seconds", 900.0),
            extend_step=_num("extend_step", 180.0),
            finalize_margin=_num("finalize_margin", 60.0),
            stall_prompt_turns=max(1, int(_num("stall_prompt_turns", 2.0))),
            stall_seconds=_num("stall_seconds", 60.0),
            finalize_window=_num("finalize_window", 90.0),
        )


@dataclass
class BudgetDecision:
    action: str = "continue"                 # continue | stop
    reason: Optional[str] = None             # stop 时的终态原因
    prompt: Optional[str] = None             # continue 时需要注入的用户侧提示
    extended: bool = False                   # 本轮是否发生了续跑（遥测）


@dataclass
class TimeBudget:
    """按墙钟时间管理自由 agent 节点的运行；check() 在每轮开始前调用。"""

    spec: TimeBudgetSpec
    started_at: float = field(default_factory=time.monotonic)
    deadline: float = 0.0
    extensions: int = 0
    last_tool_at: float = 0.0
    consecutive_no_tool: int = 0
    stall_prompted: bool = False
    finalizing: bool = False
    finalize_deadline: float = 0.0
    finalize_reason: Optional[str] = None
    termination: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.deadline:
            self.deadline = self.started_at + self.spec.soft_seconds
        if not self.last_tool_at:
            self.last_tool_at = self.started_at

    @classmethod
    def from_runtime_metadata(cls, metadata: Any) -> Optional["TimeBudget"]:
        spec = TimeBudgetSpec.from_config(
            (metadata or {}).get("time_budget") if isinstance(metadata, dict) else None
        )
        return cls(spec=spec) if spec else None

    def check(self, now=None):
        """每轮开始前的预算检查：返回是否继续、终止原因与需注入的提示。"""
        now = time.monotonic() if now is None else now
        if self.termination:
            return BudgetDecision(action="stop", reason=self.termination)

        # 收尾窗口中：窗口内继续（等模型交付），窗口过完即终止。
        if self.finalizing:
            if now >= self.finalize_deadline:
                self.termination = self.finalize_reason or TERMINATION_EXTENDED_TIMEOUT
                logger.info(
                    "time_budget_finalized",
                    termination=self.termination,
                    extensions=self.extensions,
                    elapsed_seconds=round(now - self.started_at, 1),
                )
                return BudgetDecision(action="stop", reason=self.termination)
            return BudgetDecision(action="continue")

        hard_deadline = self.started_at + self.spec.hard_seconds

        # 临近硬上限：无条件进入收尾（续跑不允许越过 hard - margin）。
        if hard_deadline - now <= self.spec.finalize_margin:
            return self._enter_finalize(now, TERMINATION_EXTENDED_TIMEOUT)

        # 软预算到点：有进展续跑，空转则直接收尾。
        if now >= self.deadline:
            if self._is_stalled(now):
                return self._enter_finalize(now, TERMINATION_STALLED_NO_PROGRESS)
            if self.deadline < hard_deadline:
                self.deadline = min(self.deadline + self.spec.extend_step, hard_deadline)
                self.extensions += 1
                logger.info(
                    "time_budget_extended_continue",
                    extensions=self.extensions,
                    deadline_offset=round(self.deadline - self.started_at, 1),
                )
                return BudgetDecision(action="continue", extended=True)
            return self._enter_finalize(now, TERMINATION_EXTENDED_TIMEOUT)

        # 空转提示：连续无工具调用达到阈值时提示一次（每轮序列只提示一次）。
        if self.consecutive_no_tool >= self.spec.stall_prompt_turns and not self.stall_prompted:
            self.stall_prompted = True
            return BudgetDecision(action="continue", prompt=STALL_PROMPT)

        return BudgetDecision(action="continue")

    def on_turn_end(self, had_tool_call: bool, now: Optional[float] = None) -> None:
        """每轮结束后记录工具调用情况（空转检测的输入）。"""
        now = time.monotonic() if now is None else now
        if had_tool_call:
            self.last_tool_at = now
            self.consecutive_no_tool = 0
            self.stall_prompted = False
        else:
            self.consecutive_no_tool += 1

    def _is_stalled(self, now: float) -> bool:
        return (
            now - self.last_tool_at >= self.spec.stall_seconds
            or self.consecutive_no_tool >= self.spec.stall_prompt_turns
            and now - self.last_tool_at >= self.spec.stall_seconds
        )

    def _enter_finalize(self, now: float, reason: str) -> BudgetDecision:
        self.finalizing = True
        self.finalize_reason = reason
        self.finalize_deadline = now + self.spec.finalize_window
        logger.info(
            "time_budget_finalize_entered",
            reason=reason,
            extensions=self.extensions,
            elapsed_seconds=round(now - self.started_at, 1),
            finalize_window=self.spec.finalize_window,
        )
        return BudgetDecision(action="continue", prompt=FINALIZE_PROMPT)
