"""
Unit Tests for Anthropic Format Migration

Phase 5.1: 测试 Anthropic 格式迁移的核心功能
"""

import pytest
from typing import Optional, Any, Dict
from app.agent.tool_adapter import convert_openai_to_anthropic_schema
from app.agent.events.error_classifier import ErrorClassifier, ErrorType
from app.scheduled_tasks.event_bus import EventBus
# 简单导入，不使用类型提示
from app.agent.events import tool_lifecycle
ToolState = tool_lifecycle.ToolState
ToolExecution = tool_lifecycle.ToolExecution


def test_schema_conversion():
    """测试 OpenAI → Anthropic schema 转换"""
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
    assert anthropic_schema["input_schema"]["properties"] == {"arg1": {"type": "string"}}
    assert anthropic_schema["input_schema"]["required"] == ["arg1"]


def test_error_classification():
    """测试错误分类"""
    classifier = ErrorClassifier()

    # 测试超时错误
    timeout_error = Exception("Request timeout")
    assert classifier.classify(timeout_error) == ErrorType.TIMEOUT

    # 测试网络错误
    network_error = Exception("Connection refused")
    assert classifier.classify(network_error) == ErrorType.NETWORK

    # 测试验证错误
    validation_error = Exception("Invalid parameter")
    assert classifier.classify(validation_error) == ErrorType.VALIDATION

    # 测试权限错误
    permission_error = Exception("Unauthorized access")
    assert classifier.classify(permission_error) == ErrorType.PERMISSION

    # 测试速率限制错误
    rate_limit_error = Exception("429 Rate limit exceeded")
    assert classifier.classify(rate_limit_error) == ErrorType.RATE_LIMIT

    # 测试未知错误
    unknown_error = Exception("Unknown error")
    assert classifier.classify(unknown_error) == ErrorType.UNKNOWN


def test_recovery_strategy():
    """测试恢复策略"""
    classifier = ErrorClassifier()

    # 测试超时错误策略
    timeout_strategy = classifier.get_recovery_strategy(ErrorType.TIMEOUT)
    assert timeout_strategy["action"] == "retry"
    assert timeout_strategy["max_retries"] == 3
    assert timeout_strategy["backoff"] == "exponential"

    # 测试网络错误策略
    network_strategy = classifier.get_recovery_strategy(ErrorType.NETWORK)
    assert network_strategy["action"] == "retry"
    assert network_strategy["max_retries"] == 2
    assert network_strategy["backoff"] == "linear"

    # 测试权限错误策略
    permission_strategy = classifier.get_recovery_strategy(ErrorType.PERMISSION)
    assert permission_strategy["action"] == "fail"


def test_event_bus_integration():
    """测试事件总线集成"""
    bus = EventBus()
    events_received = []

    def handler(data):
        events_received.append(data)

    bus.subscribe("test_event", handler)
    bus.emit_internal("test_event", {"test": "data"})

    assert len(events_received) == 1
    assert events_received[0]["test"] == "data"


def test_tool_lifecycle():
    """测试工具生命周期状态机"""
    execution = ToolExecution(
        tool_call_id="test_123",
        tool_name="test_tool",
        args={"arg1": "value1"}
    )

    # 初始状态
    assert execution.state == ToolState.QUEUED

    # 转换到运行状态
    execution.transition_to(ToolState.RUNNING)
    assert execution.state == ToolState.RUNNING

    # 转换到完成状态
    execution.transition_to(ToolState.COMPLETED)
    assert execution.state == ToolState.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
