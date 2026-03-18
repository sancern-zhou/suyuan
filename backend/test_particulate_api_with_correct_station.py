"""
测试颗粒物API客户端 - 使用正确的站点名称和编码

关键发现：
- Code "1037b" 对应的站点是 "东莞"，不是 "揭阳"
- 网页端测试使用 station="东莞", code="1037b" 成功返回了23条离子数据
"""

import sys
import os
from datetime import datetime

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.particulate_api_client import get_particulate_api_client


def test_ionic_analysis_correct_station():
    """使用正确的站点名称测试水溶性离子"""
    print("\n" + "=" * 80)
    print("测试: 水溶性离子数据（正确站点: 东莞 1037b）")
    print("=" * 80)

    client = get_particulate_api_client()

    # 使用网页端测试相同的参数
    response = client.get_ionic_analysis(
        station="东莞",  # 修正：1037b对应的是东莞
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59",
        time_type="Hour"
    )

    print(f"Success: {response.get('success')}")
    print(f"Status Code: {response.get('status_code')}")

    if response.get("success"):
        api_response = response.get("api_response")

        # 提取记录
        data = api_response
        if isinstance(data, dict):
            result = data.get("data", {}).get("result", {})
            records = result.get("resultOne", [])

            print(f"Records Count: {len(records)}")

            if records:
                first = records[0]
                print(f"\nFirst Record Keys: {list(first.keys())[:20]}")
                print(f"\nFirst Record Sample:")
                for key, value in list(first.items())[:15]:
                    print(f"  {key}: {value}")

                # 检查PMF核心组分
                pmf_components = ["SO4", "NO3", "NH4"]
                found_components = []
                component_values = {}

                for comp in pmf_components:
                    for field in first.keys():
                        normalized = field.replace("⁻", "").replace("⁺", "").replace("^", "").replace("_", "").replace("²", "")
                        if comp in normalized:
                            value = first.get(field)
                            if value not in ["—", "", None]:
                                found_components.append(comp)
                                component_values[comp] = value
                            break

                print(f"\nPMF Core Components Found: {found_components}")
                print(f"Component Values: {component_values}")

                # 检查数据完整性
                empty_count = sum(1 for v in first.values() if v in ["—", "", None])
                valid_count = len(first) - empty_count
                print(f"\nData Quality: {valid_count} valid, {empty_count} empty fields")

                return len(records), found_components
    else:
        print(f"Error: {response.get('error')}")
        return 0, []


def test_multiple_stations():
    """测试多个站点找到有数据的"""
    print("\n" + "=" * 80)
    print("测试: 多个站点对比")
    print("=" * 80)

    client = get_particulate_api_client()

    # 常见站点列表（根据之前的数据推测）
    stations = [
        {"name": "东莞", "code": "1037b"},
        {"name": "新兴", "code": "1042b"},
    ]

    results = []

    for station_info in stations:
        print(f"\n--- 测试站点: {station_info['name']} ({station_info['code']}) ---")

        response = client.get_ionic_analysis(
            station=station_info["name"],
            code=station_info["code"],
            start_time="2024-12-24 00:00:00",
            end_time="2024-12-24 23:59:59",
            time_type="Hour"
        )

        if response.get("success"):
            api_response = response.get("api_response")
            if isinstance(api_response, dict):
                result = api_response.get("data", {}).get("result", {})
                records = result.get("resultOne", [])
                record_count = len(records)

                # 检查数据质量
                if records:
                    first = records[0]
                    valid_values = [v for v in first.values() if v not in ["—", "", None]]
                    empty_values = [v for v in first.values() if v in ["—", "", None]]

                    print(f"Records: {record_count}")
                    print(f"Data Quality: {len(valid_values)} valid, {len(empty_values)} empty")

                    # 检查PMF核心组分
                    has_pmf_data = False
                    for comp in ["SO4", "NO3", "NH4"]:
                        for field in first.keys():
                            if comp in field.replace("⁻", "").replace("⁺", "").replace("^", ""):
                                if first.get(field) not in ["—", "", None]:
                                    has_pmf_data = True
                                    break

                    results.append({
                        "station": station_info["name"],
                        "code": station_info["code"],
                        "records": record_count,
                        "valid_fields": len(valid_values),
                        "empty_fields": len(empty_values),
                        "has_pmf_data": has_pmf_data
                    })

                    if has_pmf_data:
                        print(f"*** 站点 {station_info['name']} 有PMF有效数据！ ***")
        else:
            print(f"Failed: {response.get('error')}")

    # 汇总
    print("\n" + "=" * 80)
    print("站点对比汇总")
    print("=" * 80)
    print(f"{'站点':<10} {'编码':<10} {'记录数':<8} {'有效字段':<10} {'空字段':<10} {'有PMF数据'}")
    print("-" * 70)
    for r in results:
        has_data = "是" if r['has_pmf_data'] else "否"
        print(f"{r['station']:<10} {r['code']:<10} {r['records']:<8} {r['valid_fields']:<10} {r['empty_fields']:<10} {has_data}")

    return results


def main():
    print("=" * 80)
    print("颗粒物API客户端测试 - 正确站点匹配")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 测试1: 使用正确的站点名称
        record_count, components = test_ionic_analysis_correct_station()

        # 测试2: 对比多个站点
        results = test_multiple_stations()

        print("\n" + "=" * 80)
        print("结论")
        print("=" * 80)
        if record_count >= 20 and len(components) >= 3:
            print("✓ 找到满足PMF要求的数据：≥20条记录，≥3个核心组分")
        else:
            print(f"✗ 数据不满足PMF要求：{record_count}条记录，{len(components)}个核心组分")
            print("  需求：≥20条记录，≥3个核心组分（SO4, NO3, NH4, OC, EC中至少3个）")

    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
