"""无步数上限模式的压缩收敛保障。

- `_enforce_compact_floor`：LLM 摘要后仍超阈值时确定性丢弃中段，保证收敛；
- `force_compact_history`：provider 溢出续跑路径的公开入口，返回是否实际缩减。
"""

from types import SimpleNamespace

import pytest

from app.agent.context.context_builder import SimplifiedContextBuilder


def _builder_with_estimate(estimate):
    builder = object.__new__(SimplifiedContextBuilder)
    builder.max_context_tokens = 100_000
    builder.compression_threshold = 0.8  # max_allowed = 80_000
    builder.memory = SimpleNamespace(session_id="s")
    builder._estimate_messages_tokens = estimate
    return builder


def test_compact_floor_returns_messages_unchanged_when_under_threshold():
    messages = [{"role": "user", "content": "hi"}]
    builder = _builder_with_estimate(lambda msgs: 10)

    assert builder._enforce_compact_floor(messages) is messages


def test_compact_floor_trims_middle_until_under_threshold():
    messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    # 模拟"摘要本身膨胀"：全量 100k 超限；保留首条 + 尾部 3 条以内才回到阈值下
    def estimate(msgs):
        if len(msgs) <= 4:
            return 50_000
        return 100_000

    builder = _builder_with_estimate(estimate)

    trimmed = builder._enforce_compact_floor(messages)

    assert trimmed[0] is messages[0]  # 首条（compact_memory/锚点）保留
    assert trimmed[-3:] == messages[-3:]  # 最近尾部保留
    assert len(trimmed) == 4


def test_compact_floor_stops_at_hard_floor_of_two_messages():
    messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]

    def estimate(msgs):
        return 100_000  # 永远超限：任何裁剪都救不回来

    builder = _builder_with_estimate(estimate)

    trimmed = builder._enforce_compact_floor(messages)

    # 硬下限 2 条：不再无限收缩，交由上层判定"无可压缩空间"
    assert len(trimmed) == 2
    assert trimmed[0] is messages[0]
    assert trimmed[-1] is messages[-1]


@pytest.mark.asyncio
async def test_force_compact_history_reports_whether_history_shrank(monkeypatch):
    builder = object.__new__(SimplifiedContextBuilder)
    original = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    builder.memory = SimpleNamespace(
        session_id="s",
        session=SimpleNamespace(get_messages_for_llm=lambda: list(original)),
    )

    async def compressing(history, *, force_reason):
        assert force_reason == "provider_context_overflow"
        return history[:1]

    builder._compress_and_persist_history = compressing
    assert await builder.force_compact_history() is True

    async def no_shrink(history, *, force_reason):
        return list(history)

    builder._compress_and_persist_history = no_shrink
    assert await builder.force_compact_history() is False

    builder.memory.session = SimpleNamespace(get_messages_for_llm=lambda: [])
    assert await builder.force_compact_history() is False
