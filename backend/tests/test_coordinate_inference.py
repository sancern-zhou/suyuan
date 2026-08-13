"""
测试坐标推断功能

验证 Input Adapter 的城市坐标推断功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.agent.input_adapter import InputAdapterEngine


def test_coordinate_inference():
    """测试坐标推断功能"""

    print("=" * 80)
    print("测试坐标推断功能")
    print("=" * 80)

    # 初始化 Input Adapter Engine
    engine = InputAdapterEngine()

    # 测试用例
    test_cases = [
        {
            "name": "广东省21个地级市",
            "tool_name": "meteorological_trajectory_analysis",
            "cities": [
                "广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆",
                "江门", "茂名", "惠州", "梅州", "汕尾", "河源", "阳江", "清远",
                "东莞", "中山", "潮州", "揭阳", "云浮"
            ]
        },
        {
            "name": "济宁市及辖区县",
            "tool_name": "meteorological_trajectory_analysis",
            "cities": [
                "济宁", "任城区", "兖州区", "微山县", "鱼台县", "金乡县",
                "嘉祥县", "汶上县", "泗水县", "梁山县"
            ]
        }
    ]

    for test_group in test_cases:
        print(f"\n{test_group['name']}:")
        print("-" * 80)

        tool_name = test_group["tool_name"]
        cities = test_group["cities"]

        success_count = 0
        fail_count = 0

        for city in cities:
            # 模拟 LLM 只提供 location_name 的情况（修复后：使用hours而非end_time）
            raw_args = {
                "location_name": city,
                "hours": 72,
                "direction": "Backward"
            }

            try:
                normalized_args, report = engine.normalize(tool_name, raw_args)

                # 检查是否成功推断出经纬度
                if "lat" in normalized_args and "lon" in normalized_args:
                    lat = normalized_args["lat"]
                    lon = normalized_args["lon"]
                    print(f"  {city:8s}: lat={lat:6.2f}, lon={lon:7.2f}")
                    success_count += 1
                else:
                    print(f"  {city:8s}: FAILED - 无法推断经纬度")
                    fail_count += 1

            except Exception as e:
                print(f"  {city:8s}: ERROR - {str(e)}")
                fail_count += 1

        print(f"\n统计: 成功 {success_count}/{len(cities)}, 失败 {fail_count}/{len(cities)}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


def test_field_mapping():
    """测试字段映射功能"""
    print("\n" + "=" * 80)
    print("测试字段映射功能")
    print("=" * 80)

    engine = InputAdapterEngine()

    # 测试中文参数映射
    test_cases = [
        {
            "name": "中文参数（经度/纬度/小时数）",
            "raw_args": {
                "纬度": 23.13,
                "经度": 113.26,
                "小时数": 72,
                "方向": "Backward"
            }
        },
        {
            "name": "英文别名（latitude/longitude）",
            "raw_args": {
                "latitude": 23.13,
                "longitude": 113.26,
                "hours": 72,
                "direction": "Backward"
            }
        },
        {
            "name": "混合参数",
            "raw_args": {
                "lat": 23.13,
                "经度": 113.26,  # 混用中英文
                "hours": 72,
                "轨迹方向": "Backward"
            }
        },
        {
            "name": "最简参数（仅经纬度）",
            "raw_args": {
                "lat": 23.13,
                "lon": 113.26
            }
        }
    ]

    for test_case in test_cases:
        print(f"\n{test_case['name']}:")
        print("-" * 80)

        try:
            normalized_args, report = engine.normalize(
                "meteorological_trajectory_analysis",
                test_case["raw_args"]
            )

            print(f"  原始参数: {test_case['raw_args']}")
            print(f"  规范化后: {normalized_args}")

            # 验证必需字段（修复后：只需要lat和lon）
            required = ["lat", "lon"]
            missing = [field for field in required if field not in normalized_args]

            if not missing:
                print(f"  结果: SUCCESS - 所有必需字段齐全")
            else:
                print(f"  结果: FAILED - 缺少字段: {missing}")

        except Exception as e:
            print(f"  结果: ERROR - {str(e)}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_coordinate_inference()
    test_field_mapping()
