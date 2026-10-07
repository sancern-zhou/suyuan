"""思考模式策略：按请求挡位与调用方类型决定网关请求是否关闭思考。

挡位规则（方案B，与具体模型名无关——两挡共用同一模型链）：
- 用户挡位 flash（快速模式）：思考关闭
- 用户挡位 pro（深度思考）：思考保持（不传 thinking 参数，网关默认）
- 挡位 auto / 未设置：主 agent 保持思考；子 agent（call_sub_agent，
  含工作流节点）一律关闭——固定流程节点求快，轮间慢思考会击穿节点墙钟预算。
"""

from __future__ import annotations

from contextvars import ContextVar

_caller_tier_var: ContextVar[str | None] = ContextVar("llm_caller_tier", default=None)
_request_tier_var: ContextVar[str | None] = ContextVar("llm_request_tier", default=None)

SUBAGENT_TIER = "subagent"
FLASH_TIER = "flash"
PRO_TIER = "pro"


def set_agent_caller_tier(tier: str):
    """标记当前上下文的调用方档位（如 subagent）；返回 token 供 reset。"""
    return _caller_tier_var.set(tier)


def reset_agent_caller_tier(token) -> None:
    _caller_tier_var.reset(token)


def get_agent_caller_tier() -> str | None:
    return _caller_tier_var.get()


def set_request_tier(tier: str | None):
    """绑定当前请求的模型挡位（flash/pro/auto）；返回 token 供 reset。"""
    normalized = (tier or "").strip().lower() or None
    return _request_tier_var.set(normalized)


def reset_request_tier(token) -> None:
    _request_tier_var.reset(token)


def get_request_tier() -> str | None:
    return _request_tier_var.get()


def should_disable_thinking(
    master_switch: bool,
    request_tier: str | None = None,
    caller_tier: str | None = None,
) -> tuple[bool, str]:
    """返回 (是否关闭思考, 原因标签)。挡位决定开关，与具体模型名无关。"""
    if not master_switch:
        return False, "master_switch_off"
    if (caller_tier or "").strip().lower() == SUBAGENT_TIER:
        return True, "subagent_auto"
    tier = (request_tier or "").strip().lower()
    if tier == FLASH_TIER:
        return True, "flash_tier"
    if tier == PRO_TIER:
        return False, "pro_tier"
    # auto / 未设置：主 agent 保持思考（网关默认），由网关侧预算兜底
    return False, "auto_tier"
