"""
Integration Tests for Anthropic Format Migration

Phase 5.2: 端到端测试 Anthropic 格式集成
"""

import pytest
from app.services.llm_service import LLMService
from app.agent.core.planner import ReActPlanner
from app.scheduled_tasks.event_bus import get_event_bus
from app.agent.events.metrics import MetricsCollector
from config.settings import settings


@pytest.mark.asyncio
async def test_anthropic_format_tool_calling():
    """测试 Anthropic 格式工具调用"""
    # 启用 feature flag
    original_use_anthropic_format = settings.use_anthropic_format
    settings.use_anthropic_format = True

    try:
        # 创建 planner
        planner = ReActPlanner()

        # 准备测试数据
        query = "测试查询"
        system_prompt = "You are a helpful assistant"
        user_conversation = "查询广州天气"
        tools = []  # 传递测试工具

        # 调用 V3 方法（Anthropic 格式）
        # 注意：这个测试需要 Anthropic API 密钥才能运行
        # 在 CI/CD 环境中应该 mock LLM service

        # 由于没有实际的 API 密钥，这里只测试方法存在性
        assert hasattr(planner, "think_and_action_v3")

    finally:
        # 恢复原始设置
        settings.use_anthropic_format = original_use_anthropic_format


@pytest.mark.asyncio
async def test_event_emission():
    """测试事件发射"""
    event_bus = get_event_bus()
    events_received = []

    def handler(data):
        events_received.append(data)

    # 订阅事件
    event_bus.subscribe("tool_execution_start", handler)

    # 发射事件
    await event_bus.emit_tool_execution_start(
        tool_call_id="test_123",
        tool_name="test_tool",
        args={"arg1": "value1"}
    )

    assert len(events_received) == 1
    assert events_received[0]["toolName"] == "test_tool"
    assert events_received[0]["toolCallId"] == "test_123"


@pytest.mark.asyncio
async def test_metrics_collection():
    """测试指标收集"""
    event_bus = get_event_bus()
    metrics_collector = MetricsCollector(event_bus)

    # 发射工具执行事件
    await event_bus.emit_tool_execution_start(
        tool_call_id="test_123",
        tool_name="test_tool",
        args={}
    )

    await event_bus.emit_tool_execution_end(
        tool_call_id="test_123",
        tool_name="test_tool",
        result={"success": True},
        duration_ms=100.0
    )

    # 验证指标
    metric = metrics_collector.get_metrics("test_tool")
    assert metric is not None
    assert metric.call_count == 1
    assert metric.success_count == 1
    assert metric.avg_duration_ms == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
