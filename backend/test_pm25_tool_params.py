"""
测试PM2.5组分查询工具的参数生成
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.agent.core.expert_plan_generator import ExpertPlanGenerator
from app.agent.core.structured_query_parser import StructuredQuery


def test_pm25_tool_params():
    """测试PM2.5工具参数生成"""

    print("=" * 60)
    print("测试PM2.5组分查询工具参数生成")
    print("=" * 60)

    # 创建规划器
    generator = ExpertPlanGenerator()

    # 创建测试查询
    query = StructuredQuery(
        location="深圳市",
        lat=22.5431,
        lon=114.0579,
        start_time="2026-02-01 00:00:00",
        end_time="2026-02-01 23:59:59",
        pollutants=["PM2.5"],
        analysis_type="tracing",
        time_granularity="hourly"  # 修复：使用字符串类型
    )

    # 构建上下文
    context = {
        "location": query.location,
        "lat": query.lat,
        "lon": query.lon,
        "start_time": query.start_time,
        "end_time": query.end_time,
        "pollutants": query.pollutants,
        "analysis_type": query.analysis_type,
        "time_granularity": query.time_granularity,
        "expert_type": "component"
    }

    # 测试3个工具的参数生成
    tools = ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal"]

    for tool_name in tools:
        print(f"\n测试工具: {tool_name}")
        print("-" * 60)

        try:
            params = generator._generate_structured_params_sync(
                tool_name=tool_name,
                context=context,
                upstream_data_ids=[]
            )

            print(f"  生成的参数:")
            for key, value in params.items():
                print(f"    {key}: {value}")

            # 检查必需参数
            if "locations" in params:
                print(f"  [OK] locations 参数已生成: {params['locations']}")
            else:
                print(f"  [FAIL] locations 参数缺失")

            if "start_time" in params and "end_time" in params:
                print(f"  [OK] 时间参数已生成")
            else:
                print(f"  [FAIL] 时间参数缺失")

        except Exception as e:
            print(f"  [ERROR] 参数生成失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_pm25_tool_params()
