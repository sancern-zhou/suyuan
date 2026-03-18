"""
测试颗粒物API客户端（UQP版本）
"""

import sys
import os
from datetime import datetime

# 设置UTF-8编码输出（Windows兼容）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
else:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.particulate_api_client import get_particulate_api_client


def test_ionic_analysis():
    """测试水溶性离子数据查询"""
    print("\n" + "=" * 80)
    print("测试1: 水溶性离子数据查询")
    print("=" * 80)

    client = get_particulate_api_client()

    response = client.get_ionic_analysis(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59",
        time_type="Hour"
    )

    print(f"Success: {response.get('success')}")
    print(f"Status Code: {response.get('status_code')}")

    if response.get("success"):
        api_response = response.get("api_response")
        print(f"Response Keys: {list(api_response.keys()) if api_response else 'None'}")

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
                for key, value in list(first.items())[:10]:
                    print(f"  {key}: {value}")

                # 检查PMF核心组分
                pmf_components = ["SO4", "NO3", "NH4"]
                found_components = []
                for comp in pmf_components:
                    # 检查各种可能的字段名
                    for field in first.keys():
                        if comp in field.replace("⁻", "").replace("⁺", "").replace("^", "").replace("_", ""):
                            found_components.append(comp)
                            break

                print(f"\nPMF Core Components Found: {found_components}")
    else:
        print(f"Error: {response.get('error')}")


def test_carbon_components():
    """测试碳组分数据查询"""
    print("\n" + "=" * 80)
    print("测试2: 碳组分数据查询 (OC, EC)")
    print("=" * 80)

    client = get_particulate_api_client()

    response = client.get_carbon_components(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )

    print(f"Success: {response.get('success')}")
    print(f"Status Code: {response.get('status_code')}")

    if response.get("success"):
        api_response = response.get("api_response")

        # 提取记录
        data = api_response
        if isinstance(data, dict):
            result = data.get("data", {}).get("result", {})
            records = result.get("resultData", [])

            print(f"Records Count: {len(records)}")

            if records:
                first = records[0]
                print(f"\nFirst Record Keys: {list(first.keys())[:20]}")
                print(f"\nFirst Record Sample:")
                for key, value in list(first.items())[:10]:
                    print(f"  {key}: {value}")

                # 检查OC/EC字段
                oc_fields = [k for k in first.keys() if "OC" in k]
                ec_fields = [k for k in first.keys() if "EC" in k]

                print(f"\nOC Fields: {oc_fields}")
                print(f"EC Fields: {ec_fields}")
    else:
        print(f"Error: {response.get('error')}")


def test_all_components():
    """测试所有组分数据查询"""
    print("\n" + "=" * 80)
    print("测试3: 所有组分数据查询")
    print("=" * 80)

    client = get_particulate_api_client()

    results = {}

    # 水溶性离子
    print("\n--- 水溶性离子 ---")
    response = client.get_ionic_analysis(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )
    results["ions"] = response
    print(f"Success: {response.get('success')}, Records: {_count_records(response, 'resultOne')}")

    # 碳组分
    print("\n--- 碳组分 ---")
    response = client.get_carbon_components(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )
    results["carbon"] = response
    print(f"Success: {response.get('success')}, Records: {_count_records(response, 'resultData')}")

    # 地壳元素
    print("\n--- 地壳元素 ---")
    response = client.get_crustal_elements(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )
    results["crustal"] = response
    print(f"Success: {response.get('success')}, Records: {_count_records(response, 'resultOne')}")

    # 微量元素
    print("\n--- 微量元素 ---")
    response = client.get_trace_elements(
        station="揭阳",
        code="1037b",
        start_time="2024-12-24 00:00:00",
        end_time="2024-12-24 23:59:59"
    )
    results["trace"] = response
    print(f"Success: {response.get('success')}, Records: {_count_records(response, 'resultOne')}")

    # 汇总
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    for component, result in results.items():
        success = result.get('success')
        records = _count_records(result, 'resultOne' if component != 'carbon' else 'resultData')
        status = "PASS" if success and records > 0 else "FAIL"
        print(f"{component:12} : {status} (records={records})")

    return results


def _count_records(response: dict, path: str) -> int:
    """从响应中统计记录数"""
    if not response.get("success"):
        return 0

    api_response = response.get("api_response")
    if not isinstance(api_response, dict):
        return 0

    result = api_response.get("data", {}).get("result", {})
    records = result.get(path, [])

    return len(records) if isinstance(records, list) else 0


def main():
    print("=" * 80)
    print("颗粒物API客户端测试（UQP版本）")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 测试1: 水溶性离子
        test_ionic_analysis()

        # 测试2: 碳组分
        test_carbon_components()

        # 测试3: 所有组分
        results = test_all_components()

        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)

    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
