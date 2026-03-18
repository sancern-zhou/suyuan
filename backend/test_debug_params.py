"""
调试：打印实际发送的API参数
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import json


def test_with_manual_params():
    """手动构建参数测试"""
    base_url = "http://180.184.91.74:9093/api/uqp/query"

    # 根据之前的成功测试，使用这个参数组合
    params = {
        "question": "查询东莞市2024-12-24期间的小时级PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "StartTime": "2024-12-24 00:00:00",
        "EndTime": "2024-12-24 23:59:59",
        "dateType": 3,  # 关键：使用 dateType
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4", "Cl", "Ca", "Mg", "K", "Na"],
        "Station": "东莞",
        "Code": "1037b"
    }

    print("=" * 80)
    print("手动参数测试")
    print("=" * 80)
    print("发送的参数:")
    print(json.dumps(params, ensure_ascii=False, indent=2))

    response = requests.post(base_url, json=params, timeout=120)
    data = response.json()

    records = data.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"\n返回记录数: {len(records)}")

    if records:
        print(f"第一条时间: {records[0].get('TimePoint')}")
        if len(records) > 1:
            print(f"最后一条时间: {records[-1].get('TimePoint')}")
            print(f"\n所有时间点（前10个）:")
            for i, r in enumerate(records[:10]):
                print(f"  {i+1}. {r.get('TimePoint')}")

    # 对比：使用 TimeStart/TimeEnd 的情况
    print("\n" + "=" * 80)
    print("对比测试：使用 TimeStart/TimeEnd")
    print("=" * 80)

    params2 = params.copy()
    params2["TimeStart"] = params2.pop("StartTime")
    params2["TimeEnd"] = params2.pop("EndTime")

    print("发送的参数:")
    print(json.dumps(params2, ensure_ascii=False, indent=2))

    response2 = requests.post(base_url, json=params2, timeout=120)
    data2 = response2.json()

    records2 = data2.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"\n返回记录数: {len(records2)}")
    if records2:
        print(f"第一条时间: {records2[0].get('TimePoint')}")

    return len(records), len(records2)


if __name__ == "__main__":
    count1, count2 = test_with_manual_params()
    print(f"\n结果对比:")
    print(f"  StartTime/EndTime + dateType: {count1} 条")
    print(f"  TimeStart/TimeEnd + dateType:  {count2} 条")
