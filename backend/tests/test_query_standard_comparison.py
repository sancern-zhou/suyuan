"""
新旧标准对比查询工具测试

测试内容：
1. 工具导入和注册
2. 新标准IAQI计算
3. 综合指数计算
4. 工具基本功能
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta

# 设置控制台输出编码为UTF-8（避免Windows GBK编码问题）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class TestNewStandardCalculations:
    """测试新标准计算函数"""

    def test_import_calculations(self):
        """测试导入计算函数"""
        from app.tools.query.query_gd_suncere.tool import (
            calculate_new_iaqi,
            calculate_new_composite_index,
            NEW_STANDARD_BREAKPOINTS,
            IAQI_VALUES,
            NEW_WEIGHTS
        )

        # 验证断点配置
        assert 'PM2_5' in NEW_STANDARD_BREAKPOINTS
        assert 'PM10' in NEW_STANDARD_BREAKPOINTS
        assert NEW_STANDARD_BREAKPOINTS['PM2_5'][1] == 30  # IAQI=50时
        assert NEW_STANDARD_BREAKPOINTS['PM2_5'][2] == 60  # IAQI=100时
        assert NEW_STANDARD_BREAKPOINTS['PM10'][2] == 120  # IAQI=100时

        # 验证权重配置
        assert NEW_WEIGHTS['PM2_5'] == 3
        assert NEW_WEIGHTS['O3'] == 2
        assert NEW_WEIGHTS['NO2'] == 2
        assert NEW_WEIGHTS['SO2'] == 1

        print("✓ 计算函数导入成功，配置验证通过")

    def test_calculate_new_iaqi_pm25(self):
        """测试PM2.5新标准IAQI计算"""
        from app.tools.query.query_gd_suncere.tool import calculate_new_iaqi

        # 测试新标准断点
        assert calculate_new_iaqi(30, 'PM2_5') == 50.0  # 新标准IAQI=50的断点
        assert calculate_new_iaqi(60, 'PM2_5') == 100.0  # 新标准IAQI=100的断点

        # 测试线性插值
        result = calculate_new_iaqi(45, 'PM2_5')
        assert 50 < result < 100  # 在两个断点之间

        # 测试边界值
        assert calculate_new_iaqi(0, 'PM2_5') == 0.0
        assert calculate_new_iaqi(500, 'PM2_5') == 500.0

        print("✓ PM2.5新标准IAQI计算测试通过")

    def test_calculate_new_iaqi_pm10(self):
        """测试PM10新标准IAQI计算"""
        from app.tools.query.query_gd_suncere.tool import calculate_new_iaqi

        # 测试新标准断点
        assert calculate_new_iaqi(50, 'PM10') == 50.0  # IAQI=50的断点
        assert calculate_new_iaqi(120, 'PM10') == 100.0  # 新标准IAQI=100的断点

        # 测试线性插值
        result = calculate_new_iaqi(85, 'PM10')
        assert 50 < result < 100

        print("✓ PM10新标准IAQI计算测试通过")

    def test_calculate_new_composite_index(self):
        """测试新标准综合指数计算"""
        from app.tools.query.query_gd_suncere.tool import calculate_new_composite_index

        # 测试权重计算
        iaqi_values = {
            'PM2_5_IAQI': 75,
            'PM10_IAQI': 60,
            'O3_8h_IAQI': 80,
            'NO2_IAQI': 40,
            'SO2_IAQI': 30,
            'CO_IAQI': 20
        }

        result = calculate_new_composite_index(iaqi_values)

        # 综合指数 = max(单项最大IAQI, 加权IAQI之和)
        # 加权之和 = 75*3 + 60*1 + 80*2 + 40*2 + 30*1 + 20*1 = 225 + 60 + 160 + 80 + 30 + 20 = 575
        # 单项最大 = 80
        # 综合指数 = max(80, 575) = 575
        expected_weighted_sum = 75*3 + 60*1 + 80*2 + 40*2 + 30*1 + 20*1  # = 575
        expected_max_iaqi = 80
        expected_result = max(expected_max_iaqi, expected_weighted_sum)

        assert result == expected_result, f"期望 {expected_result}，实际 {result}"
        assert isinstance(result, (int, float)), f"结果类型应该是数字，实际是 {type(result)}"

        print(f"✓ 新标准综合指数计算测试通过，结果: {result}，类型: {type(result).__name__}")


class TestToolRegistration:
    """测试工具注册"""

    def test_tool_import(self):
        """测试工具导入"""
        from app.tools.query.query_gd_suncere import QueryStandardComparisonTool

        tool = QueryStandardComparisonTool()
        assert tool.name == "query_standard_comparison"
        assert tool.requires_context == True

        print("✓ 工具导入测试通过")

    def test_tool_registration(self):
        """测试工具注册"""
        from app.tools import create_global_tool_registry

        registry = create_global_tool_registry()
        tools = registry.list_tools()

        assert "query_standard_comparison" in tools

        tool = registry.get_tool("query_standard_comparison")
        assert tool is not None
        assert tool.name == "query_standard_comparison"

        print("✓ 工具注册测试通过")


class TestToolSchema:
    """测试工具Schema"""

    def test_function_schema(self):
        """测试函数Schema"""
        from app.tools.query.query_gd_suncere import QueryStandardComparisonTool

        tool = QueryStandardComparisonTool()
        schema = tool.function_schema

        assert schema["name"] == "query_standard_comparison"
        assert "description" in schema
        assert "parameters" in schema

        params = schema["parameters"]
        assert params["type"] == "object"
        assert "properties" in params

        properties = params["properties"]
        assert "cities" in properties
        assert "start_date" in properties
        assert "end_date" in properties

        # 检查必需参数
        required = params.get("required", [])
        assert "cities" in required
        assert "start_date" in required
        assert "end_date" in required

        print("✓ 函数Schema测试通过")


class TestToolDescription:
    """测试工具描述"""

    def test_description_content(self):
        """测试描述内容"""
        from app.tools.query.query_gd_suncere import QueryStandardComparisonTool

        tool = QueryStandardComparisonTool()
        description = tool.function_schema["description"]

        # 验证描述包含关键信息
        assert "新标准" in description or "新旧标准" in description
        assert "PM2.5" in description or "PM2_5" in description
        assert "综合指数" in description

        print("✓ 工具描述内容测试通过")


class TestIntegration:
    """集成测试"""

    def test_tool_context_requirement(self):
        """测试工具上下文要求"""
        from app.tools.query.query_gd_suncere import QueryStandardComparisonTool

        tool = QueryStandardComparisonTool()
        assert tool.requires_context == True

        print("✓ 工具上下文要求测试通过")

    def test_export_in_module(self):
        """测试模块导出"""
        from app.tools.query.query_gd_suncere import (
            QueryStandardComparisonTool,
            execute_query_standard_comparison
        )

        assert QueryStandardComparisonTool is not None
        assert execute_query_standard_comparison is not None

        print("✓ 模块导出测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("新旧标准对比查询工具测试")
    print("=" * 60)

    test_classes = [
        TestNewStandardCalculations,
        TestToolRegistration,
        TestToolSchema,
        TestToolDescription,
        TestIntegration
    ]

    total_tests = 0
    passed_tests = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 60)

        instance = test_class()

        # 获取所有测试方法
        test_methods = [method for method in dir(instance) if method.startswith("test_")]

        for method_name in test_methods:
            total_tests += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed_tests += 1
            except Exception as e:
                print(f"✗ {method_name} 失败: {str(e)}")

    print("\n" + "=" * 60)
    print(f"测试完成: {passed_tests}/{total_tests} 通过")
    print("=" * 60)

    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
