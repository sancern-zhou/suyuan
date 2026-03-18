"""
最终验证：测试修复后的颗粒物API客户端
使用正确的站点（东莞 1037b）和参数
"""

import sys
import os
from datetime import datetime

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.particulate_api_client import get_particulate_api_client


def main():
    print("=" * 80)
    print("颗粒物API客户端最终验证")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    client = get_particulate_api_client()

    # 测试水溶性离子（东莞站点，与网页端一致）
    print("\n【测试】水溶性离子数据（东莞 1037b）")
    print("-" * 80)

    response = client.get_ionic_analysis(
        station="东莞",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59",
        time_type="Hour"  # 现在会自动转换为 dateType=3
    )

    print(f"API调用成功: {response.get('success')}")

    if response.get("success"):
        api_response = response.get("api_response")
        result = api_response.get("data", {}).get("result", {})
        records = result.get("resultOne", [])

        print(f"返回记录数: {len(records)}")

        if records:
            first = records[0]
            print(f"\n第一条记录时间: {first.get('TimePoint')}")
            print(f"站点名称: {first.get('StationName')}")

            # 检查PMF核心组分
            print(f"\nPMF核心组分值:")
            pmf_components = {
                "SO4²⁻": "SO4",
                "NO₃⁻": "NO3",
                "NH₄⁺": "NH4"
            }

            found_count = 0
            for field, comp_name in pmf_components.items():
                if field in first:
                    value = first.get(field)
                    is_valid = value not in ["—", "", None]
                    status = "✓" if is_valid else "✗"
                    print(f"  {status} {field} ({comp_name}): {value}")
                    if is_valid:
                        found_count += 1

            # 数据完整性统计
            print(f"\n数据完整性统计（基于{len(records)}条记录）:")
            for field, comp_name in pmf_components.items():
                if field in records[0]:
                    valid_count = sum(1 for r in records if r.get(field) not in ["—", "", None])
                    completeness = valid_count / len(records) * 100
                    print(f"  {field} ({comp_name}): {valid_count}/{len(records)} ({completeness:.1f}%) 有效")

            print(f"\n【PMF数据评估】")
            if len(records) >= 20:
                print(f"  ✓ 样本数满足要求: {len(records)} >= 20")
            else:
                print(f"  ✗ 样本数不足: {len(records)} < 20")

            if found_count >= 3:
                print(f"  ✓ 核心组分满足要求: {found_count} >= 3")
            else:
                print(f"  ✗ 核心组分不足: {found_count} < 3")

            if len(records) >= 20 and found_count >= 3:
                print(f"\n【结论】✓ 数据满足PMF源解析要求！")
                return True
            else:
                print(f"\n【结论】✗ 数据不满足PMF源解析要求")
                return False
        else:
            print("未返回任何记录")
            return False
    else:
        print(f"API调用失败: {response.get('error')}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
