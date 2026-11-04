"""跨 Context 清理回归测试。

detached run 超时/取消后，生成器的兜底关闭曾经通过 ``asyncio.create_task``
执行：新任务拿到复制出来的 Context，生成器 ``with`` 块里 set 的 ContextVar
token 无法复位，于是清理链路抛出
``ValueError: ... was created in a different Context``，并把真实错误掩盖成
内部异常。
"""

import asyncio
from contextvars import ContextVar

import pytest
from structlog.testing import capture_logs

from app.api.agent import _finish_detached_run
from app.services.llm_service import LLMService
from app.services.llm_thinking_policy import get_request_tier
from app.utils.async_cleanup import close_async_generator, reset_context_var


class _FakeStream:
    def __init__(self):
        self.closed = []

    async def close(self, stream_id: str) -> None:
        self.closed.append(stream_id)


def _flash_service() -> LLMService:
    service = LLMService.__new__(LLMService)
    service.provider = "go"
    service.model = "deepseek-v4.1-flash"
    service.request_fallbacks = None
    service.anthropic_client = None
    return service


async def test_reset_context_var_skips_token_from_copied_context():
    var: ContextVar = ContextVar("_copied_context_token", default=None)

    async def child():
        return var.set("inner")

    outer_token = var.set("outer")
    try:
        copied_token = await asyncio.create_task(child())
        # 子任务拿到的 token 绑定在复制出的 Context 上，直接 reset 会失败。
        with pytest.raises(ValueError):
            var.reset(copied_token)
        with capture_logs() as logs:
            reset_context_var(var, copied_token)
        skipped = [e for e in logs if e["event"] == "context_var_reset_skipped"]
        assert skipped, "跨 Context 跳过必须留痕"
        assert skipped[0]["context_var"] == "_copied_context_token"
        assert skipped[0]["reason"] == "token_bound_to_other_context"
        assert var.get() == "outer"
    finally:
        var.reset(outer_token)


def test_reset_context_var_does_not_hide_real_misuse():
    var: ContextVar = ContextVar("_owner_scope", default=None)
    other: ContextVar = ContextVar("_other_scope", default=None)

    # token 属于另一个 ContextVar：是调用方 bug，不能当成跨 Context 吞掉。
    wrong_var_token = var.set("value")
    try:
        with pytest.raises(ValueError, match="different ContextVar"):
            reset_context_var(other, wrong_var_token)
    finally:
        var.reset(wrong_var_token)

    # 已消费的 token：RuntimeError 同样必须抛出。
    used_token = var.set("once")
    var.reset(used_token)
    with pytest.raises(RuntimeError):
        reset_context_var(var, used_token)


async def test_close_async_generator_keeps_current_context():
    var: ContextVar = ContextVar("_scoped_value", default=None)
    released = []

    async def stream():
        token = var.set("scoped")
        try:
            yield "chunk"
        finally:
            released.append(var.get())
            var.reset(token)

    gen = stream()
    assert await gen.__anext__() == "chunk"
    await close_async_generator(gen)
    assert released == ["scoped"]
    assert var.get() is None


async def test_close_async_generator_releases_llm_scopes():
    service = _flash_service()

    async def stream():
        with service.use_model_tier("flash"), service.use_opencode_session("sess"):
            yield "chunk"

    gen = stream()
    assert await gen.__anext__() == "chunk"
    await close_async_generator(gen)
    assert get_request_tier() is None


async def test_finish_detached_run_closes_generator_in_calling_task():
    service = _flash_service()
    caller_task = asyncio.current_task()
    closed_in: list = []

    async def stream():
        with service.use_model_tier("pro"), service.use_opencode_session("sess"):
            try:
                yield "chunk"
            finally:
                closed_in.append(asyncio.current_task())

    gen = stream()
    assert await gen.__anext__() == "chunk"
    stream_mirror = _FakeStream()
    await _finish_detached_run(gen, stream_mirror, "stream-1")

    assert closed_in == [caller_task]
    assert stream_mirror.closed == ["stream-1"]
    assert get_request_tier() is None


async def test_finish_detached_run_survives_active_cancellation():
    """模拟 publish 挂起点被取消：finally 仍需关闭生成器并写完 stream_closed。"""
    service = _flash_service()
    stream_mirror = _FakeStream()

    async def stream():
        with service.use_model_tier("flash"), service.use_opencode_session("sess"):
            yield "chunk"

    gen = stream()

    async def driver():
        try:
            async for _ in gen:
                await asyncio.sleep(10)
        finally:
            await _finish_detached_run(gen, stream_mirror, "stream-2")

    task = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream_mirror.closed == ["stream-2"]
    assert get_request_tier() is None
