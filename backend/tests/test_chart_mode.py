"""
图表模式功能测试

测试场景：
1. 图表模式 ReAct 循环
2. read_data_registry 工具调用
3. execute_python 工具执行
4. 图表生成和缓存
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agent.react_agent import create_react_agent
from app.tools.utility.execute_python_tool import ExecutePythonTool


async def test_execute_python_tool():
    """测试 execute_python 工具基本功能"""
    print("\n" + "="*60)
    print("测试 1: execute_python 工具基本功能")
    print("="*60)

    tool = ExecutePythonTool()

    # 测试代码：生成简单图表
    test_code = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import time

# 生成测试数据
x = np.linspace(0, 10, 100)
y = np.sin(x)

# 绘图
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(x, y, label='sin(x)', linewidth=2)
ax.set_xlabel('X', fontsize=12)
ax.set_ylabel('Y', fontsize=12)
ax.set_title('Test Chart', fontsize=14)
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()

# 保存图表
path = '/home/xckj/suyuan/backend_data_registry/charts/test_chart_{}.png'.format(int(time.time()))
plt.savefig(path, dpi=150, bbox_inches='tight')
print('CHART_SAVED:{}'.format(path))
print('Test completed successfully')
"""

    result = await tool.execute(code=test_code, timeout=30)

    print(f"✅ 执行状态: {result['success']}")
    print(f"📄 摘要: {result.get('summary', 'N/A')}")

    if result['success']:
        print(f"📊 生成的文件:")
        for file_path in result['data'].get('files', []):
            print(f"   - {file_path}")

        if 'images' in result['data']:
            print(f"🖼️  缓存的图片:")
            for img in result['data']['images']:
                print(f"   - 路径: {img['path']}")
                print(f"   - URL: {img['url']}")

        print("\n✅ execute_python 工具测试通过")
        return True
    else:
        print(f"❌ 错误: {result.get('error', 'Unknown error')}")
        print("\n❌ execute_python 工具测试失败")
        return False


async def test_chart_mode_prompt():
    """测试图表模式提示词是否正确加载"""
    print("\n" + "="*60)
    print("测试 2: 图表模式提示词加载")
    print("="*60)

    try:
        from app.agent.prompts.prompt_builder import build_react_system_prompt

        # 获取图表模式提示词
        chart_prompt = build_react_system_prompt(mode="chart")

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
        print("\n✅ 图表模式提示词测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_registry():
    """测试工具注册表是否包含图表模式工具"""
    print("\n" + "="*60)
    print("测试 3: 图表模式工具注册表")
    print("="*60)

    try:
        from app.agent.prompts.tool_registry import CHART_TOOLS, get_tools_by_mode

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

        if set(CHART_TOOLS.keys()) != expected_tools:
            print(f"❌ 工具不匹配")
            print(f"   预期: {expected_tools}")
            print(f"   实际: {set(CHART_TOOLS.keys())}")
            return False

        print(f"✅ 工具数量正确: {len(CHART_TOOLS)} 个工具")

        # 验证工具列表获取
        chart_tools = get_tools_by_mode("chart")
        if len(chart_tools) != len(expected_tools):
            print(f"❌ get_tools_by_mode 返回数量不正确")
            return False

        print(f"✅ get_tools_by_mode 返回正确")

        # 打印工具列表
        print("\n📋 图表模式可用工具:")
        for tool_name, description in CHART_TOOLS.items():
            print(f"   - {tool_name}: {description}")

        print("\n✅ 工具注册表测试通过")
        return True

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_charts_directory():
    """测试 charts 目录是否正确配置"""
    print("\n" + "="*60)
    print("测试 4: Charts 目录配置")
    print("="*60)

    try:
        from app.tools.utility.execute_python_tool import ExecutePythonTool

        tool = ExecutePythonTool()

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


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("图表模式功能测试")
    print("="*60)

    tests = [
        ("Charts 目录配置", test_charts_directory),
        ("工具注册表", test_tool_registry),
        ("提示词加载", test_chart_mode_prompt),
        ("execute_python 工具", test_execute_python_tool),
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
        print("\n🎉 所有测试通过！图表模式功能正常。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，需要修复。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
