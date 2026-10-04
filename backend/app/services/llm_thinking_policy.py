"""思考模式策略：按模型档位与调用方类型决定网关请求是否关闭思考。

档位规则：
- flash 档模型（模型名含 flash）：思考默认关闭
- PRO 档模型：思考默认开启（不传 thinking 参数，网关默认）
- 调用方叠加：子 agent（call_sub_agent，含工作流节点）一律关闭思考，
  与模型档位无关——问数/专家子节点的轮间慢思考会击穿节点墙钟预算。
"""

from __future__ import annotations

from contextvars import ContextVar

_caller_tier_var: ContextVar[str | None] = ContextVar("llm_caller_tier", default=None)

SUBAGENT_TIER = "subagent"


def set_agent_caller_tier(tier: str):
    """标记当前上下文的调用方档位（如 subagent）；返回 token 供 reset。"""
    return _caller_tier_var.set(tier)


def reset_agent_caller_tier(token) -> None:
    _caller_tier_var.reset(token)


def get_agent_caller_tier() -> str | None:
    return _caller_tier_var.get()


def model_tier(model: str) -> str:
    """模型档位：名称含 flash 为 flash 档，其余为 pro 档。"""
    return "flash" if "flash" in str(model or "").lower() else "pro"


def should_disable_thinking(model: str, master_switch: bool) -> tuple[bool, str]:
    """返回 (是否关闭思考, 原因标签)。供 SCNET 和 Go/Go2 网关复用。"""
    if not master_switch:
        return False, "master_switch_off"
    tier = model_tier(model)
    if tier == "flash":
        return True, "flash_tier"
    if get_agent_caller_tier() == SUBAGENT_TIER:
        return True, "subagent_auto"
    return False, "pro_tier"
