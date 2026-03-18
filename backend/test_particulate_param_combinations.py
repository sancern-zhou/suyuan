"""
测试颗粒物API - 尝试不同参数组合获取小时级数据

根据参考项目参数：
- dateType: 3 (小时级)
- timePoint: [start, end]

尝试将这些参数添加到UQP API调用中
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


def test_parameter_combinations():
    """测试不同参数组合"""
    base_url = "http://180.184.91.74:9093/api/uqp/query"

    print("=" * 80)
    print("测试：不同参数组合获取小时级数据")
    print("=" * 80)

    # 测试1: 原始参数（TimeType）
    print("\n【测试1】使用 TimeType='Hour'")
    params1 = {
        "question": "查询东莞市2024-12-24期间的PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2024-12-24 00:00:00",
        "TimeEnd": "2024-12-24 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    response1 = requests.post(base_url, json=params1, timeout=120)
    data1 = response1.json()
    records1 = data1.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records1)}")
    if records1:
        print(f"时间点: {records1[0].get('TimePoint')}")

    # 测试2: 添加 dateType 和 timePoint
    print("\n【测试2】添加 dateType=3 和 timePoint")
    params2 = {
        "question": "查询东莞市2024-12-24期间的PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2024-12-24 00:00:00",
        "TimeEnd": "2024-12-24 23:59:59",
        "TimeType": "Hour",
        "dateType": 3,  # 参考项目参数
        "timePoint": ["2024-12-24 00:00:00", "2024-12-24 23:59:59"],  # 参考项目参数
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    response2 = requests.post(base_url, json=params2, timeout=120)
    data2 = response2.json()
    records2 = data2.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records2)}")
    if records2:
        print(f"时间点: {records2[0].get('TimePoint')}")
        if len(records2) > 1:
            print(f"所有时间点（前10个）:")
            for i, r in enumerate(records2[:10]):
                print(f"  {i+1}. {r.get('TimePoint')}")

    # 测试3: 不使用 TimeType，只用 dateType
    print("\n【测试3】只使用 dateType=3，不使用 TimeType")
    params3 = {
        "question": "查询东莞市2024-12-24期间的小时级PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "StartTime": "2024-12-24 00:00:00",
        "EndTime": "2024-12-24 23:59:59",
        "dateType": 3,
        "timePoint": ["2024-12-24 00:00:00", "2024-12-24 23:59:59"],
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    response3 = requests.post(base_url, json=params3, timeout=120)
    data3 = response3.json()
    records3 = data3.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records3)}")
    if records3:
        print(f"时间点: {records3[0].get('TimePoint')}")

    # 测试4: 尝试在 question 中明确指定"小时级"
    print("\n【测试4】在 question 中明确指定'小时级'")
    params4 = {
        "question": "查询东莞市2024-12-24期间的**小时级**PM2.5水溶性离子数据，需要23个小时的数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2024-12-24 00:00:00",
        "TimeEnd": "2024-12-24 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    response4 = requests.post(base_url, json=params4, timeout=120)
    data4 = response4.json()
    records4 = data4.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records4)}")
    if records4:
        print(f"时间点: {records4[0].get('TimePoint')}")

    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    print(f"测试1 (TimeType='Hour'):         {len(records1)} 条记录")
    print(f"测试2 (+dateType=3, timePoint):  {len(records2)} 条记录")
    print(f"测试3 (只用dateType):            {len(records3)} 条记录")
    print(f"测试4 (question强调小时级):       {len(records4)} 条记录")

    # 找到最有效的参数组合
    max_records = max(len(records1), len(records2), len(records3), len(records4))
    if max_records >= 20:
        print(f"\n✓ 成功！找到能返回{max_records}条记录的参数组合")
    else:
        print(f"\n✗ 所有参数组合都只返回1条记录（日数据）")

    return {
        "test1": len(records1),
        "test2": len(records2),
        "test3": len(records3),
        "test4": len(records4)
    }


def main():
    print("=" * 80)
    print("颗粒物API参数组合测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = test_parameter_combinations()

    print("\n" + "=" * 80)
    print("下一步建议")
    print("=" * 80)
    if max(results.values()) < 20:
        print("UQP API可能不支持小时级颗粒物数据查询")
        print("建议:")
        print("1. 联系API提供方确认UQP是否支持小时级数据")
        print("2. 或者使用参考项目的专用API端点（需要token认证）")
        print("3. 或者使用日数据进行PMF分析（需要多日数据）")


if __name__ == "__main__":
    main()
