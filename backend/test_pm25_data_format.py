"""
诊断PM2.5工具返回的原始数据格式
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

import asyncio
from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool
from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool
from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool
from app.agent.context.execution_context import ExecutionContext
from app.agent.context.data_context_manager import DataContextManager
from app.agent.memory.hybrid_manager import HybridMemoryManager


async def test_pm25_data_format():
    """测试PM2.5工具返回的原始数据格式"""

    print("=" * 80)
    print("PM2.5工具原始数据格式诊断")
    print("=" * 80)

    # 创建执行上下文
    memory_manager = HybridMemoryManager(session_id="test_session")
    data_manager = DataContextManager(memory_manager)
    context = ExecutionContext(
        session_id="test_session",
        iteration=1,
        data_manager=data_manager
    )

    # 测试参数
    params = {
        "start_time": "2026-02-01 00:00:00",
        "end_time": "2026-02-01 23:59:59",
        "time_granularity": "hourly",
        "locations": ["深圳"]
    }

    tools = [
        ("get_pm25_ionic", GetPM25IonicTool()),
        ("get_pm25_carbon", GetPM25CarbonTool()),
        ("get_pm25_crustal", GetPM25CrustalTool())
    ]

    for tool_name, tool_instance in tools:
        print(f"\n{'=' * 80}")
        print(f"测试工具: {tool_name}")
        print("=" * 80)

        try:
            # 执行工具
            result = await tool_instance.execute(
                context=context,
                start_time=params["start_time"],
                end_time=params["end_time"],
                time_granularity=params["time_granularity"],
                locations=params["locations"]
            )

            print(f"\n结果状态: {result.get('status')}")
            print(f"成功: {result.get('success')}")

            # 检查数据
            if result.get("success") and result.get("data"):
                data = result["data"]
                print(f"\n数据记录数: {len(data)}")

                if len(data) > 0:
                    first_record = data[0]
                    print(f"\n第一条记录的字段:")
                    for key in sorted(first_record.keys()):
                        value = first_record[key]
                        if isinstance(value, (int, float)):
                            print(f"  {key}: {value} (数值)")
                        elif isinstance(value, dict):
                            print(f"  {key}: {value} (字典)")
                        else:
                            print(f"  {key}: {type(value).__name__}")

                    # 检查是否有 components 字段
                    if "components" in first_record:
                        print(f"\ncomponents 字段内容:")
                        components = first_record["components"]
                        if isinstance(components, dict):
                            for key, value in components.items():
                                print(f"  {key}: {value}")
                        else:
                            print(f"  类型: {type(components).__name__}")
                    else:
                        print("\n未找到 components 字段")

                        # 列出所有数值型字段（可能是组分）
                        numeric_fields = {k: v for k, v in first_record.items()
                                        if isinstance(v, (int, float))}
                        if numeric_fields:
                            print(f"\n所有数值型字段 (可能是组分):")
                            for key, value in sorted(numeric_fields.items()):
                                print(f"  {key}: {value}")
            else:
                print(f"\n错误: {result.get('error', '未知错误')}")

        except Exception as e:
            print(f"\n执行失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("诊断完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_pm25_data_format())
