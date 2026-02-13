"""
测试ComponentExecutor中新工具的集成
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_component_executor_tools():
    """测试ComponentExecutor加载的工具"""
    print("=" * 80)
    print("ComponentExecutor工具加载测试")
    print("=" * 80)

    from app.agent.experts.component_executor import ComponentExecutor

    executor = ComponentExecutor()
    tools = executor._load_tools()

    print(f"\n已加载工具数量: {len(tools)}")
    print("\n工具列表:")

    # 按类别分组
    query_tools = []
    analysis_tools = []
    visualization_tools = []

    for tool_name in sorted(tools.keys()):
        if tool_name.startswith("get_"):
            query_tools.append(tool_name)
        elif tool_name.startswith("calculate_") or tool_name.startswith("smart_chart"):
            analysis_tools.append(tool_name)
        else:
            visualization_tools.append(tool_name)

    print("\n【数据查询工具】")
    for tool in query_tools:
        marker = ""
        if tool == "get_particulate_components":
            marker = " ⭐ 新版（推荐）"
        elif tool == "get_particulate_data":
            marker = " （备用）"
        print(f"  - {tool}{marker}")

    print(f"\n【数据分析工具】({len(analysis_tools)}个)")
    for tool in analysis_tools:
        print(f"  - {tool}")

    print(f"\n【可视化工具】({len(visualization_tools)}个)")
    for tool in visualization_tools:
        print(f"  - {tool}")

    # 验证新工具是否正确加载
    print("\n" + "=" * 80)
    print("新工具验证")
    print("=" * 80)

    if "get_particulate_components" in tools:
        print("✓ get_particulate_components 已成功加载")
        tool = tools["get_particulate_components"]
        print(f"  工具类型: {type(tool).__name__}")
        print(f"  工具描述: {tool.description[:100]}...")
        print(f"  需要上下文: {tool.requires_context}")
        print(f"  分类: {tool.category}")
    else:
        print("✗ get_particulate_components 未加载")

    if "get_particulate_data" in tools:
        print("\n✓ get_particulate_data（备用）已成功加载")
    else:
        print("\n✗ get_particulate_data（备用）未加载")

    # 检查工具schema
    if "get_particulate_components" in tools:
        print("\n" + "=" * 80)
        print("get_particulate_components 参数schema")
        print("=" * 80)
        schema = tools["get_particulate_components"].function_schema
        print(f"名称: {schema['name']}")
        print(f"描述: {schema['description']}")
        print(f"必需参数: {schema['parameters']['required']}")
        print(f"可选参数: {[p for p in schema['parameters']['properties'] if p not in schema['parameters']['required']]}")


def test_tool_execution():
    """测试工具执行"""
    print("\n" + "=" * 80)
    print("工具执行测试")
    print("=" * 80)

    import asyncio
    from app.agent.context.execution_context import ExecutionContext

    async def run_test():
        from app.agent.experts.component_executor import ComponentExecutor

        executor = ComponentExecutor()
        tools = executor._load_tools()

        if "get_particulate_components" not in tools:
            print("✗ 工具未加载，跳过执行测试")
            return

        tool = tools["get_particulate_components"]
        context = ExecutionContext()

        print("\n执行 get_particulate_components...")
        result = await tool.execute(
            context=context,
            station="东莞",
            code="1037b",
            start_time="2024-12-24 00:00:00",
            end_time="2024-12-24 23:59:59",
            component_type="ions",
            time_type="Hour"
        )

        print(f"执行成功: {result.get('success')}")
        print(f"返回记录数: {result.get('count', 0)}")
        print(f"data_id: {result.get('data_id', 'N/A')}")

        if result.get('quality_report'):
            qr = result['quality_report']
            print(f"\n数据质量:")
            print(f"  总记录数: {qr.get('total_records', 0)}")
            print(f"  组分字段数: {qr.get('component_fields', 0)}")
            if 'field_names' in qr:
                print(f"  字段列表（前10个）: {qr['field_names'][:10]}")

    asyncio.run(run_test())


if __name__ == "__main__":
    print("ComponentExecutor集成测试")
    print("=" * 80)

    # 测试1: 工具加载
    test_component_executor_tools()

    # 测试2: 工具执行（可选，需要网络连接）
    print("\n\n是否测试工具执行？（需要连接API）")
    print("输入 y 继续测试，其他键跳过")
    # choice = input("> ")
    choice = "n"  # 默认跳过，避免在加载时自动执行

    if choice.lower() == 'y':
        test_tool_execution()
    else:
        print("\n已跳过执行测试")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
