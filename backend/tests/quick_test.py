#!/usr/bin/env python
"""
Quick Test for Anthropic Format Migration

只测试核心功能，不加载整个工具注册表
"""

import sys
import os

# 确保可以导入项目模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def test_core_features():
    """测试核心功能"""
    print("=" * 60)
    print("Anthropic 格式迁移 - 核心功能测试")
    print("=" * 60)

    # 测试 1: Schema 转换
    print("\n[测试 1] Schema 转换")
    from app.agent.tool_adapter import convert_openai_to_anthropic_schema

    openai_schema = {
        "name": "test_tool",
        "description": "Test tool",
        "parameters": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string"}
            },
            "required": ["arg1"]
        }
    }

    anthropic_schema = convert_openai_to_anthropic_schema(openai_schema)

    assert anthropic_schema["name"] == "test_tool"
    assert "input_schema" in anthropic_schema
    assert anthropic_schema["input_schema"]["type"] == "object"
    assert anthropic_schema["input_schema"]["required"] == ["arg1"]
    print("✅ PASSED")

    # 测试 2: 错误分类
    print("\n[测试 2] 错误分类")
    from app.agent.events.error_classifier import ErrorClassifier, ErrorType

    classifier = ErrorClassifier()

    tests = [
        (Exception("Request timeout"), ErrorType.TIMEOUT),
        (Exception("Connection refused"), ErrorType.NETWORK),
        (Exception("Invalid parameter"), ErrorType.VALIDATION),
        (Exception("Unauthorized access"), ErrorType.PERMISSION),
        (Exception("429 Rate limit"), ErrorType.RATE_LIMIT),
    ]

    for error, expected_type in tests:
        result = classifier.classify(error)
        assert result == expected_type, f"Expected {expected_type}, got {result}"
        print(f"  ✓ {expected_type.value} 错误分类正确")

    print("✅ PASSED")

    # 测试 3: 恢复策略
    print("\n[测试 3] 恢复策略")
    timeout_strategy = classifier.get_recovery_strategy(ErrorType.TIMEOUT)
    assert timeout_strategy["action"] == "retry"
    assert timeout_strategy["max_retries"] == 3
    assert timeout_strategy["backoff"] == "exponential"
    print("  ✓ 超时错误策略正确")

    network_strategy = classifier.get_recovery_strategy(ErrorType.NETWORK)
    assert network_strategy["action"] == "retry"
    assert network_strategy["max_retries"] == 2
    assert network_strategy["backoff"] == "linear"
    print("  ✓ 网络错误策略正确")

    permission_strategy = classifier.get_recovery_strategy(ErrorType.PERMISSION)
    assert permission_strategy["action"] == "fail"
    print("  ✓ 权限错误策略正确")
    print("✅ PASSED")

    # 测试 4: EventBus (跳过，需要 fastapi)
    print("\n[测试 4] EventBus 内部订阅")
    print("  ⚠️  跳过（需要 fastapi，在完整环境中可用）")
    print("✅ SKIPPED")
    # 测试 4: EventBus
    print("\n[测试 4] EventBus 内部订阅")
    from app.scheduled_tasks.event_bus import EventBus

    bus = EventBus()
    events_received = []

    def handler(data):
        events_received.append(data)

    bus.subscribe("test_event", handler)
    bus.emit_internal("test_event", {"test": "data"})

    assert len(events_received) == 1
    assert events_received[0]["test"] == "data"
    print("✅ PASSED")

    # 测试 5: 工具生命周期
    print("\n[测试 5] 工具生命周期状态机")
    from app.agent.events.tool_lifecycle import ToolState, ToolExecution

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
    print("✅ PASSED")

    print("\n" + "=" * 60)
    print("所有核心功能测试通过！✅")
    print("=" * 60)

    # 测试 6: 配置验证
    print("\n[测试 6] 配置验证")
    from config.settings import settings

    print(f"  USE_ANTHROPIC_FORMAT: {settings.use_anthropic_format}")
    print(f"  ENABLE_TOOL_LIFECYCLE_EVENTS: {settings.enable_tool_lifecycle_events}")
    print(f"  ENABLE_INTELLIGENT_RETRY: {settings.enable_intelligent_retry}")
    print(f"  LLM_PROVIDER: {settings.llm_provider}")
    print(f"  DEEPSEEK_MODEL: {settings.deepseek_model}")

    assert settings.use_anthropic_format == True
    assert settings.enable_tool_lifecycle_events == True
    assert settings.enable_intelligent_retry == True
    print("✅ PASSED")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！系统已成功启用 Anthropic 格式迁移")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_core_features()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
