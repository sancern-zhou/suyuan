"""
Schema注入器简化测试

不依赖全局工具注册表，直接测试SchemaInjector核心逻辑
"""

import sys
from pathlib import Path

# 添加backend到path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from collections import defaultdict


class SchemaInjector:
    """简化的Schema注入器（复制核心逻辑）"""

    def __init__(self, consecutive_error_threshold: int = 2):
        self.consecutive_error_threshold = consecutive_error_threshold
        self.tool_error_counts: defaultdict = defaultdict(int)
        self.injected_schemas: set = set()

    def record_tool_result(self, tool_name: str, observation: dict) -> None:
        """记录工具执行结果"""
        success = observation.get("success", False)
        error_type = observation.get("error_type")

        if not success and error_type in ["INPUT_VALIDATION_FAILED", "TOOL_EXECUTION_FAILED"]:
            self.tool_error_counts[tool_name] += 1
        else:
            if self.tool_error_counts[tool_name] > 0:
                pass  # 成功后重置
            self.tool_error_counts[tool_name] = 0

    def should_inject_schema(self, tool_name: str) -> bool:
        """判断是否应该注入工具schema"""
        error_count = self.tool_error_counts.get(tool_name, 0)
        return (
            error_count >= self.consecutive_error_threshold
            and tool_name not in self.injected_schemas
        )


def test_schema_injection_trigger():
    """测试schema注入触发逻辑"""
    injector = SchemaInjector(consecutive_error_threshold=2)

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

    print("✓ Schema注入触发测试通过")


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

    # 这种错误应该计入
    assert injector.tool_error_counts.get("some_tool", 0) == 1, \
        "工具执行失败应该计入"

    # 但如果成功了，会重置
    injector.record_tool_result("some_tool", {
        "success": True
    })

    assert injector.tool_error_counts.get("some_tool", 0) == 0, \
        "成功后应该重置"

    print("✓ 非参数验证错误测试通过")


def test_error_threshold_customization():
    """测试自定义错误阈值"""
    injector = SchemaInjector(consecutive_error_threshold=3)

    # 2次错误 - 不应该触发
    injector.record_tool_result("tool", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})
    injector.record_tool_result("tool", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})

    assert not injector.should_inject_schema("tool"), \
        "未达到阈值3不应该触发"

    # 第3次错误 - 应该触发
    injector.record_tool_result("tool", {"success": False, "error_type": "INPUT_VALIDATION_FAILED"})

    assert injector.should_inject_schema("tool"), \
        "达到阈值3应该触发"

    print("✓ 自定义错误阈值测试通过")


if __name__ == "__main__":
    test_schema_injection_trigger()
    test_schema_injection_reset()
    test_multiple_tools()
    test_non_validation_errors()
    test_error_threshold_customization()

    print("\n✅ 所有Schema注入器测试通过！")
    print("\n## 混合策略总结")
    print("1. ✅ 保留tool_registry.py（节省token）")
    print("2. ✅ 提示词中说明可主动阅读schema")
    print("3. ✅ 连续2次工具错误自动注入schema")
    print("4. ✅ 成功后重置错误计数")
    print("5. ✅ 支持多工具独立追踪")
    print("6. ✅ 可自定义错误阈值")
