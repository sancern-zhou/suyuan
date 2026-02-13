"""
测试新的3个颗粒物查询工具
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_component_executor_new_tools():
    """测试ComponentExecutor中新工具的加载"""
    print("=" * 80)
    print("ComponentExecutor新工具集成测试")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()
    tools = executor._load_tools()

    print(f"\n已加载工具数量: {len(tools)}")

    # 检查新工具
    new_tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    print("\n【新工具验证】")
    for tool_name in new_tools:
        if tool_name in tools:
            print(f"✓ {tool_name} 已成功加载")
            tool = tools[tool_name]
            print(f"  Schema名称: {tool.function_schema['name']}")
            print(f"  必需参数: {tool.function_schema['parameters']['required']}")
            print(f"  可选参数: {list(tool.function_schema['parameters']['properties'].keys() - set(tool.function_schema['parameters']['required']))}")
        else:
            print(f"✗ {tool_name} 未加载")

    # 检查旧工具是否已删除
    print("\n【旧工具清理验证】")
    if "get_particulate_data" in tools:
        print("✗ get_particulate_data 仍然存在（应该删除）")
    else:
        print("✓ get_particulate_data 已成功删除")

    if "get_particulate_components" in tools:
        print("✗ get_particulate_components 仍然存在（应该删除）")
    else:
        print("✓ get_particulate_components 已成功删除")

    # 统计颗粒物相关工具
    print("\n【颗粒物相关工具统计】")
    particulate_tools = [t for t in tools.keys() if "pm25" in t.lower() or "particulate" in t.lower()]
    for tool in sorted(particulate_tools):
        print(f"  - {tool}")

    return tools


def test_tool_execution():
    """测试工具执行"""
    print("\n" + "=" * 80)
    print("工具执行测试（水溶性离子）")
    print("=" * 80)

    import asyncio
    from app.agent.context.execution_context import ExecutionContext

    async def run_test():
        from app.agent.experts.component_executor import ComponentExecutor

        executor = ComponentExecutor()
        tools = executor._load_tools()

        if "get_pm25_ionic" not in tools:
            print("✗ 工具未加载，跳过执行测试")
            return

        tool = tools["get_pm25_ionic"]
        context = ExecutionContext()

        print("\n执行 get_pm25_ionic...")
        result = await tool.execute(
            context=context,
            station="东莞",
            code="1037b",
            start_time="2024-12-24 00:00:00",
            end_time="2024-12-24 23:59:59",
            data_type=0,
            time_granularity=1
        )

        print(f"执行成功: {result.get('success')}")
        print(f"返回记录数: {result.get('count', 0)}")
        print(f"data_id: {result.get('data_id', 'N/A')}")

        if result.get('quality_report'):
            qr = result['quality_report']
            print(f"\n数据质量:")
            print(f"  总记录数: {qr.get('total_records', 0)}")
            print(f"  离子字段数: {qr.get('ionic_fields', 0)}")
            if 'pmf_components' in qr:
                print(f"  PMF核心组分:")
                for comp, info in qr['pmf_components'].items():
                    print(f"    {comp}: {info['valid_count']}/{info['total']} ({info['completeness']*100:.1f}%)")

    asyncio.run(run_test())


if __name__ == "__main__":
    print("ComponentExecutor新工具测试")
    print("=" * 80)

    # 测试1: 工具加载
    tools = test_component_executor_new_tools()

    # 测试2: 工具执行（需要网络）
    print("\n\n是否测试工具执行？（需要连接API）")
    print("输入 y 继续测试，其他键跳过")
    choice = "n"  # 默认跳过

    if choice.lower() == 'y':
        test_tool_execution()
    else:
        print("\n已跳过执行测试")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
