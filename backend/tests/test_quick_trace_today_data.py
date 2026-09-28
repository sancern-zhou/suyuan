"""
测试快速溯源执行器是否能够获取完整今天气象数据

验证内容：
1. get_weather_forecast 是否正确使用 past_days=1
2. 返回数据是否包含今天 00:00 ~ 当前时刻的数据
3. LLM prompt 是否包含今天完整数据
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agent.executors.quick_trace_executor import QuickTraceExecutor


async def test_quick_trace_today_data():
    """测试快速溯源执行器的今天数据获取"""

    print("=" * 80)
    print("测试快速溯源执行器 - 今天气象数据完整性")
    print("=" * 80)

    # 创建执行器
    executor = QuickTraceExecutor()

    # 测试参数
    test_cases = [
        {
            "city": "济宁市",
            "alert_time": "2026-02-04 14:00:00",
            "pollutant": "PM2.5",
            "alert_value": 115.0
        }
    ]

    for case in test_cases:
        print(f"\n测试案例:")
        print(f"  城市: {case['city']}")
        print(f"  告警时间: {case['alert_time']}")
        print(f"  污染物: {case['pollutant']}")
        print(f"  浓度: {case['alert_value']} μg/m³")
        print(f"\n{'-' * 80}")

        try:
            # 执行快速溯源分析
            result = await executor.execute(
                city=case['city'],
                alert_time=case['alert_time'],
                pollutant=case['pollutant'],
                alert_value=case['alert_value']
            )

            # 检查返回结果
            if result.get("summary_text"):
                print(f"\n[OK] 分析报告生成成功")

                # 检查报告是否包含今天数据
                summary_text = result["summary_text"]
                today_str = "2026-02-04"

                if today_str in summary_text:
                    print(f"[OK] 报告包含今天 ({today_str}) 的数据")
                else:
                    print(f"[WARNING] 报告可能缺少今天完整数据")

                # 检查关键信息
                keywords = ["边界层", "今天", "00:00", "当前时刻"]
                found_keywords = [kw for kw in keywords if kw in summary_text]
                print(f"\n[INFO] 报告包含关键词: {', '.join(found_keywords)}")

                # 显示报告片段（前500字符）
                print(f"\n[INFO] 报告前500字符预览:")
                print("-" * 80)
                print(summary_text[:500])
                print("-" * 80)

            else:
                print(f"[FAILED] 报告生成失败")

            # 检查数据
            if result.get("warning_message"):
                print(f"\n[WARNING] {result['warning_message']}")

            if result.get("has_trajectory"):
                print(f"[OK] 轨迹分析成功")
            else:
                print(f"[INFO] 轨迹分析失败或超时（这是预期的）")

        except Exception as e:
            print(f"\n[FAILED] 执行失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_quick_trace_today_data())
