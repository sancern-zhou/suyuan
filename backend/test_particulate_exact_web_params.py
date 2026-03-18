"""
测试颗粒物API - 完全复现网页端参数

根据网页端截图，需要检查：
1. 时间范围是否正确
2. 是否有其他必需参数
3. 响应数据结构
"""

import sys
import os
import json
from datetime import datetime

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests


def test_exact_web_params():
    """完全按照网页端参数测试"""
    base_url = "http://180.184.91.74:9093"
    endpoint = "/api/uqp/query"
    url = f"{base_url}{endpoint}"

    # 网页端测试参数（从截图推断）
    params = {
        "question": "查询东莞市2024-12-24期间的PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2024-12-24 00:00:00",
        "TimeEnd": "2024-12-24 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4", "Cl", "Ca", "Mg", "K", "Na", "F"],
        "Station": "东莞",
        "Code": "1037b"
    }

    print("=" * 80)
    print("测试：完全复现网页端参数")
    print("=" * 80)
    print(f"URL: {url}")
    print(f"Parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")

    try:
        response = requests.post(url, json=params, headers={"Content-Type": "application/json"}, timeout=120)

        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            print(f"\nResponse Keys: {list(data.keys())}")

            # 保存完整响应用于分析
            with open("test_response_exact_web.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("完整响应已保存到: test_response_exact_web.json")

            # 分析响应结构
            if "data" in data:
                result = data["data"].get("result", {})
                if isinstance(result, dict):
                    records = result.get("resultOne", [])

                    print(f"\nRecords Count: {len(records)}")

                    if records:
                        print(f"\n前5条记录的时间点:")
                        for i, record in enumerate(records[:5]):
                            timepoint = record.get("TimePoint", "N/A")
                            print(f"  {i+1}. {timepoint}")

                        first = records[0]
                        print(f"\n第一条记录的所有字段和值:")
                        for key, value in first.items():
                            print(f"  {key}: {value}")

                        # 统计PMF核心组分
                        pmf_fields = {}
                        for field in first.keys():
                            for comp in ["SO4", "NO3", "NH4"]:
                                if comp in field.replace("⁻", "").replace("⁺", "").replace("^", "").replace("_", "").replace("²", ""):
                                    pmf_fields[field] = first.get(field)

                        print(f"\nPMF核心组分字段:")
                        for field, value in pmf_fields.items():
                            is_valid = value not in ["—", "", None]
                            status = "✓" if is_valid else "✗"
                            print(f"  {status} {field}: {value}")

                        # 统计所有记录的数据完整性
                        print(f"\n数据完整性统计（基于所有{len(records)}条记录）:")
                        for field in pmf_fields.keys():
                            valid_count = sum(1 for r in records if r.get(field) not in ["—", "", None])
                            completeness = valid_count / len(records) * 100
                            print(f"  {field}: {valid_count}/{len(records)} ({completeness:.1f}%) 有效")

                        return len(records)
            else:
                print(f"Error in response: {data}")
        else:
            print(f"HTTP Error: {response.text}")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

    return 0


def test_with_different_time_format():
    """尝试不同的时间格式"""
    print("\n" + "=" * 80)
    print("测试：不同的时间格式")
    print("=" * 80)

    base_url = "http://180.184.91.74:9093/api/uqp/query"

    # 尝试ISO格式
    params_iso = {
        "question": "查询东莞市2024-12-24期间的PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2024-12-24T00:00:00",
        "TimeEnd": "2024-12-24T23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    try:
        response = requests.post(base_url, json=params_iso, timeout=120)
        if response.status_code == 200:
            data = response.json()
            records = data.get("data", {}).get("result", {}).get("resultOne", [])
            print(f"ISO时间格式 - Records: {len(records)}")
    except Exception as e:
        print(f"ISO格式测试失败: {e}")


def main():
    print("=" * 80)
    print("颗粒物API参数测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    record_count = test_exact_web_params()
    test_with_different_time_format()

    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)
    if record_count >= 20:
        print(f"✓ 成功获取{record_count}条记录，满足PMF要求")
    else:
        print(f"✗ 只获取{record_count}条记录，不满足PMF要求（需要≥20条）")
        print("需要进一步分析为什么网页端能返回23条而我们只能获取1条")


if __name__ == "__main__":
    main()
