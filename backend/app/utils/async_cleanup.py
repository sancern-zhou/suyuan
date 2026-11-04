"""异步清理链路的 Context 安全工具。

后台兜底清理（run 超时、客户端断开、生成器被 GC）常常发生在与创建时不同的
Context 里：新 asyncio Task 会拿到复制后的 Context，async generator 的
finalizer 也运行在事件循环的 Context 中。此时 ``ContextVar.reset(token)`` 会
抛出 ``ValueError: ... was created in a different Context``，中断整个清理流程，
并把真实错误（如运行超时）掩盖成内部异常。
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any

import structlog

logger = structlog.get_logger()

# 仅此一种 ValueError 可以跳过：token 绑定的 Context 与当前 Context 不同
# （生成器被复制 Context 里的新任务或 GC finalizer 关闭）。
# token 属于别的 ContextVar、或已被消费（RuntimeError）都是调用方 bug，照常抛出。
_FOREIGN_CONTEXT_MARKER = "in a different Context"


def reset_context_var(var: ContextVar, token: Any) -> None:
    """复位 ContextVar；token 属于其他 Context 时跳过并记 debug 日志。

    跨 Context 复位是兜底关闭下的预期场景：旧值随该上下文一起失效，
    不会泄漏到当前上下文。跳过必须留痕，避免把作用域泄漏伪装成正常清理。
    """
    try:
        var.reset(token)
    except ValueError as exc:
        if _FOREIGN_CONTEXT_MARKER not in str(exc):
            raise
        logger.debug(
            "context_var_reset_skipped",
            context_var=var.name,
            reason="token_bound_to_other_context",
            error=str(exc),
        )


async def close_async_generator(gen: Any, *, attempts: int = 3) -> None:
    """在当前 Context 关闭异步生成器，并吸收关闭过程中的再次取消。

    不能把 ``gen.aclose()`` 放进 ``asyncio.create_task``：新任务的 Context 是
    复制出来的，生成器 ``with`` 块里 set 的 ContextVar token 无法在那里复位。
    """
    for attempt in range(attempts):
        try:
            await gen.aclose()
            return
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if (
                current is None
                or not hasattr(current, "uncancel")
                or not current.cancelling()
                or attempt == attempts - 1
            ):
                raise
            while current.cancelling():
                current.uncancel()
