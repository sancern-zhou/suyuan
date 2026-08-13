#!/usr/bin/env python
"""
Anthropic Format Integration Test

测试端到端流程：Planner V3 + 工具生命周期事件
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from config.settings import settings


async def test_planner_v3_basic():
    """测试 V3 规划器基本功能"""
    print("=" * 60)
    print("Anthropic V3 规划器集成测试")
    print("=" * 60)

    # 验证配置
    print("\n[1] 验证配置")
    assert settings.use_anthropic_format == True
    print("✅ USE_ANTHROPIC_FORMAT = True")

    # 测试 schema 转换
    print("\n[2] 测试 Schema 转换")
    from app.agent.tool_adapter import convert_openai_to_anthropic_schema

    # 模拟 loop.py 中的工具格式
    tool_schema = {
        "name": "test_tool",
        "description": "Test tool description",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }

    converted = convert_openai_to_anthropic_schema(tool_schema)
    assert converted == tool_schema  # 应该直接返回
    print("✅ Anthropic格式工具直接返回")

    # 测试OpenAI格式转换
    openai_tool = {
        "name": "openai_tool",
        "description": "OpenAI format tool",
        "parameters": {
            "type": "object",
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"]
        }
    }

    converted_openai = convert_openai_to_anthropic_schema(openai_tool)
    assert "input_schema" in converted_openai
    assert converted_openai["input_schema"]["type"] == "object"
    print("✅ OpenAI格式工具转换成功")

    # 测试错误分类
    print("\n[3] 测试错误分类")
    from app.agent.events.error_classifier import ErrorClassifier, ErrorType

    classifier = ErrorClassifier()
    error_type = classifier.classify(Exception("Request timeout"))
    assert error_type == ErrorType.TIMEOUT

    strategy = classifier.get_recovery_strategy(ErrorType.TIMEOUT)
    assert strategy["action"] == "retry"
    assert strategy["max_retries"] == 3
    print("✅ 错误分类和恢复策略正确")

    # 测试工具生命周期状态机
    print("\n[4] 测试工具生命周期状态机")
    from app.agent.events.tool_lifecycle import ToolExecution, ToolState

    execution = ToolExecution(
        tool_call_id="test_123",
        tool_name="test_tool",
        args={"arg1": "value1"}
    )

    assert execution.state == ToolState.QUEUED
    execution.transition_to(ToolState.RUNNING)
    assert execution.state == ToolState.RUNNING
    execution.transition_to(ToolState.COMPLETED)
    assert execution.state == ToolState.COMPLETED
    print("✅ 状态机转换正确")

    print("\n" + "=" * 60)
    print("✅ 所有集成测试通过！")
    print("=" * 60)


async def test_event_bus_integration():
    """测试 EventBus 集成"""
    print("\n[5] 测试 EventBus 内部订阅")

    from app.scheduled_tasks.event_bus import EventBus

    bus = EventBus()
    events_received = []

    def handler(data):
        events_received.append(data)

    bus.subscribe("test_event", handler)
    bus.emit_internal("test_event", {"test": "data"})

    assert len(events_received) == 1
    assert events_received[0]["test"] == "data"
    print("✅ EventBus 内部订阅成功")


if __name__ == "__main__":
    try:
        asyncio.run(test_planner_v3_basic())
        asyncio.run(test_event_bus_integration())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
