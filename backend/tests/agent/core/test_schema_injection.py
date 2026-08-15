"""
Schema注入器测试

测试连续工具错误时的自动schema注入机制
"""

import pytest
from app.agent.core.schema_injection import SchemaInjector


def test_schema_injection_trigger():
    """测试schema注入触发逻辑"""
    injector = SchemaInjector(consecutive_error_threshold=2)

    # 模拟工具注册表
    class MockTool:
        def _build_schema(self):
            return {
                "type": "object",
                "description": "记住重要事实到长期记忆",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "要记住的事实"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["用户偏好", "领域知识", "历史结论", "环境信息"],
                        "description": "事实类别"
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "default": 3,
                        "description": "优先级"
                    }
                },
                "required": ["fact", "category"]
            }

    tool_registry = {
        "remember_fact": MockTool()
    }

    # 第1次错误 - 不应该触发注入
    injector.record_tool_result("remember_fact", {
        "success": False,
        "error_type": "INPUT_VALIDATION_FAILED"
    })

    assert not injector.should_inject_schema("remember_fact"), \
        "第1次错误不应该触发schema注入"

    # 第2次错误 - 应该触发注入
    injector.record_tool_result("remember_fact", {
        "success": False,
        "error_type": "INPUT_VALIDATION_FAILED"
    })

    assert injector.should_inject_schema("remember_fact"), \
        "第2次错误应该触发schema注入"

    # 获取schema
    schema_text = injector.get_tool_schema("remember_fact", tool_registry)
    assert schema_text is not None, "应该成功获取schema"
    assert "remember_fact" in schema_text, "schema应该包含工具名"
    assert "用户偏好" in schema_text, "schema应该包含enum值"
    assert "1-5" in schema_text, "schema应该包含数值范围"
    assert "[必需]" in schema_text, "schema应该标记必需参数"

    print("✓ Schema注入触发测试通过")
    print("\n生成的Schema文本:")
    print(schema_text)


def test_schema_injection_reset():
    """测试成功调用后重置错误计数"""
    injector = SchemaInjector(consecutive_error_threshold=2)

    # 第1次错误
    injector.record_tool_result("remember_fact", {
        "success": False,
        "error_type": "INPUT_VALIDATION_FAILED"
    })

    assert injector.tool_error_counts["remember_fact"] == 1

    # 成功调用 - 应该重置计数
    injector.record_tool_result("remember_fact", {
        "success": True
    })

    assert injector.tool_error_counts["remember_fact"] == 0, \
        "成功调用后应该重置错误计数"

    print("✓ Schema注入重置测试通过")


def test_schema_formatting():
    """测试schema格式化"""
    injector = SchemaInjector(consecutive_error_threshold=2)

    schema = {
        "type": "object",
        "description": "测试工具",
        "properties": {
            "name": {
                "type": "string",
                "description": "名称"
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "数量"
            },
            "enabled": {
                "type": "boolean",
                "default": True,
                "description": "是否启用"
            }
        },
        "required": ["name"]
    }

    formatted = injector._format_schema("test_tool", schema)

    assert "test_tool" in formatted
    assert "name (string) **[必需]**" in formatted
    assert "count (integer, range: 1-100)" in formatted
    assert "enabled (boolean)" in formatted
    assert "默认值: `True`" in formatted

    print("✓ Schema格式化测试通过")


def test_multiple_tools():
    """测试多个工具的错误追踪"""
    injector = SchemaInjector(consecutive_error_threshold=2)

    # 工具A出错2次
    injector.record_tool_result("tool_a", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})
    injector.record_tool_result("tool_a", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})

    # 工具B出错1次
    injector.record_tool_result("tool_b", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})

    assert injector.should_inject_schema("tool_a"), "工具A应该触发注入"
    assert not injector.should_inject_schema("tool_b"), "工具B不应该触发注入"

    print("✓ 多工具错误追踪测试通过")


def test_non_validation_errors():
    """测试非参数验证错误不影响注入"""
    injector = SchemaInjector(consecutive_error_threshold=2)

    # 工具执行失败（非参数错误）
    injector.record_tool_result("some_tool", {
        "success": False,
        "error_type": "TOOL_EXECUTION_FAILED"
    })

    # 这种错误不应该计入参数错误
    assert injector.tool_error_counts.get("some_tool", 0) == 1, \
        "工具执行失败应该计入"

    # 但如果成功了，会重置
    injector.record_tool_result("some_tool", {
        "success": True
    })

    assert injector.tool_error_counts.get("some_tool", 0) == 0, \
        "成功后应该重置"

    print("✓ 非参数验证错误测试通过")


if __name__ == "__main__":
    test_schema_injection_trigger()
    test_schema_injection_reset()
    test_schema_formatting()
    test_multiple_tools()
    test_non_validation_errors()

    print("\n✅ 所有Schema注入器测试通过！")
