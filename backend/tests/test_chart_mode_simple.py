"""
图表模式功能测试（简化版）

只测试核心功能，避免导入有问题的模块
"""

import asyncio
import sys
import os
import importlib.util

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def test_charts_directory():
    """测试 charts 目录是否正确配置"""
    print("\n" + "="*60)
    print("测试 1: Charts 目录配置")
    print("="*60)

    try:
        # 动态导入模块，避免导入时的依赖问题
        spec = importlib.util.spec_from_file_location(
            "execute_python_tool",
            "/home/xckj/suyuan/backend/app/tools/utility/execute_python_tool.py"
        )
        module = importlib.util.module_from_spec(spec)

        # 设置必要的模块
        sys.modules['app.tools.base.tool_interface'] = importlib.import_module('app.tools.base.tool_interface')

        spec.loader.exec_module(module)

        tool_class = module.ExecutePythonTool
        tool = tool_class()

        # 验证目录路径
        expected_path = "/home/xckj/suyuan/backend_data_registry/charts"
        if tool.CHARTS_DIR != expected_path:
            print(f"❌ CHARTS_DIR 路径不正确")
            print(f"   预期: {expected_path}")
            print(f"   实际: {tool.CHARTS_DIR}")
            return False

        print(f"✅ CHARTS_DIR 路径正确: {tool.CHARTS_DIR}")

        # 验证目录存在
        if not os.path.exists(tool.CHARTS_DIR):
            print(f"❌ CHARTS_DIR 目录不存在")
            return False

        print(f"✅ CHARTS_DIR 目录存在")

        # 验证目录权限
        if not os.access(tool.CHARTS_DIR, os.W_OK):
            print(f"❌ CHARTS_DIR 目录不可写")
            return False

        print(f"✅ CHARTS_DIR 目录可写")

        print("\n✅ Charts 目录配置测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_registry():
    """测试工具注册表是否包含图表模式工具"""
    print("\n" + "="*60)
    print("测试 2: 图表模式工具注册表")
    print("="*60)

    try:
        # 动态导入 tool_registry
        spec = importlib.util.spec_from_file_location(
            "tool_registry",
            "/home/xckj/suyuan/backend/app/agent/prompts/tool_registry.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 验证 CHART_TOOLS 存在
        if not hasattr(module, 'CHART_TOOLS'):
            print(f"❌ CHART_TOOLS 不存在")
            return False

        chart_tools = module.CHART_TOOLS

        # 验证工具数量
        expected_tools = {
            "query_gd_suncere_city_hour",
            "query_gd_suncere_city_day_new",
            "query_new_standard_report",
            "query_old_standard_report",
            "compare_standard_reports",
            "read_data_registry",
            "read_file",
            "write_file",
            "list_directory",
            "execute_python",
            "TodoWrite",
            "call_sub_agent"
        }

        if set(chart_tools.keys()) != expected_tools:
            print(f"❌ 工具不匹配")
            print(f"   预期: {expected_tools}")
            print(f"   实际: {set(chart_tools.keys())}")
            return False

        print(f"✅ 工具数量正确: {len(chart_tools)} 个工具")

        # 打印工具列表
        print("\n📋 图表模式可用工具:")
        for tool_name, description in chart_tools.items():
            print(f"   - {tool_name}: {description}")

        print("\n✅ 工具注册表测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_chart_prompt():
    """测试图表模式提示词"""
    print("\n" + "="*60)
    print("测试 3: 图表模式提示词")
    print("="*60)

    try:
        # 动态导入 chart_prompt
        spec = importlib.util.spec_from_file_location(
            "chart_prompt",
            "/home/xckj/suyuan/backend/app/agent/prompts/chart_prompt.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 调用 build_chart_prompt
        chart_prompt = module.build_chart_prompt(["execute_python", "read_data_registry"])

        # 验证关键内容
        required_keywords = [
            "数据可视化专家",
            "read_data_registry",
            "execute_python",
            "CHART_SAVED",
            "matplotlib.use('Agg')",
            "FINAL_ANSWER"
        ]

        missing_keywords = []
        for keyword in required_keywords:
            if keyword not in chart_prompt:
                missing_keywords.append(keyword)

        if missing_keywords:
            print(f"❌ 提示词缺少关键词: {missing_keywords}")
            return False

        print("✅ 提示词包含所有必需关键词")
        print(f"📄 提示词长度: {len(chart_prompt)} 字符")

        # 显示提示词片段
        print("\n📝 提示词片段（前500字符）:")
        print(chart_prompt[:500] + "...")

        print("\n✅ 图表模式提示词测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_prompt_builder():
    """测试 prompt_builder 是否支持图表模式"""
    print("\n" + "="*60)
    print("测试 4: Prompt Builder 图表模式支持")
    print("="*60)

    try:
        # 动态导入 prompt_builder
        spec = importlib.util.spec_from_file_location(
            "prompt_builder",
            "/home/xckj/suyuan/backend/app/agent/prompts/prompt_builder.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 验证 AgentMode 包含 chart
        if not hasattr(module, 'AgentMode'):
            print(f"❌ AgentMode 不存在")
            return False

        agent_mode = module.AgentMode
        if 'chart' not in agent_mode.__args__:
            print(f"❌ AgentMode 不包含 'chart'")
            return False

        print(f"✅ AgentMode 包含 'chart'")

        # 验证 build_react_system_prompt 支持 chart 模式
        try:
            prompt = module.build_react_system_prompt(mode="chart")
            if not prompt or "数据可视化专家" not in prompt:
                print(f"❌ build_react_system_prompt('chart') 返回不正确")
                return False
            print(f"✅ build_react_system_prompt 支持 chart 模式")
        except Exception as e:
            print(f"❌ build_react_system_prompt('chart') 调用失败: {e}")
            return False

        print("\n✅ Prompt Builder 测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_execute_python_basic():
    """测试 execute_python 工具基本功能（不运行完整工具）"""
    print("\n" + "="*60)
    print("测试 5: ExecutePython 工具基本配置")
    print("="*60)

    try:
        # 动态导入模块
        spec = importlib.util.spec_from_file_location(
            "execute_python_tool",
            "/home/xckj/suyuan/backend/app/tools/utility/execute_python_tool.py"
        )
        module = importlib.util.module_from_spec(spec)

        # 设置必要的模块
        sys.modules['app.tools.base.tool_interface'] = importlib.import_module('app.tools.base.tool_interface')

        spec.loader.exec_module(module)

        tool_class = module.ExecutePythonTool

        # 验证工具元数据
        tool = tool_class()

        if tool.name != "execute_python":
            print(f"❌ 工具名称不正确: {tool.name}")
            return False

        print(f"✅ 工具名称正确: {tool.name}")

        if "matplotlib" not in tool.description.lower():
            print(f"❌ 工具描述未提及 matplotlib")
            return False

        print(f"✅ 工具描述包含 matplotlib")

        # 验证 CHARTS_DIR 在描述中
        if tool.CHARTS_DIR not in tool.description:
            print(f"❌ 工具描述未包含 CHARTS_DIR 路径")
            return False

        print(f"✅ 工具描述包含 CHARTS_DIR 路径")

        print("\n✅ ExecutePython 工具基本配置测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("图表模式功能测试（简化版）")
    print("="*60)

    tests = [
        ("Charts 目录配置", test_charts_directory),
        ("工具注册表", test_tool_registry),
        ("图表模式提示词", test_chart_prompt),
        ("Prompt Builder 支持", test_prompt_builder),
        ("ExecutePython 配置", test_execute_python_basic),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = await test_func()
        except Exception as e:
            print(f"\n❌ {test_name} 测试异常: {str(e)}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")

    total = len(results)
    passed = sum(results.values())
    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！图表模式配置正确。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，需要检查。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
