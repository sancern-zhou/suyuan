"""
对比测试：不同question文本的影响
"""

import sys
import os

# 设置UTF-8编码输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import json


def test_question_variations():
    """测试不同question文本的影响"""
    base_url = "http://180.184.91.74:9093/api/uqp/query"

    base_params = {
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "StartTime": "2024-12-24 00:00:00",
        "EndTime": "2024-12-24 23:59:59",
        "dateType": 3,
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4"],
        "Station": "东莞",
        "Code": "1037b"
    }

    print("=" * 80)
    print("测试：不同question文本的影响")
    print("=" * 80)

    # 测试1: 不包含"小时级"
    print("\n【测试1】question不包含'小时级'")
    params1 = base_params.copy()
    params1["question"] = "查询东莞市2024-12-24期间的PM2.5水溶性离子数据"

    response1 = requests.post(base_url, json=params1, timeout=120)
    data1 = response1.json()
    records1 = data1.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records1)}")

    # 测试2: 包含"小时级"
    print("\n【测试2】question包含'小时级'")
    params2 = base_params.copy()
    params2["question"] = "查询东莞市2024-12-24期间的**小时级**PM2.5水溶性离子数据"

    response2 = requests.post(base_url, json=params2, timeout=120)
    data2 = response2.json()
    records2 = data2.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records2)}")

    # 测试3: 明确指定23个小时
    print("\n【测试3】question明确说明需要23个小时的数据")
    params3 = base_params.copy()
    params3["question"] = "查询东莞市2024-12-24期间的小时级PM2.5水溶性离子数据，需要23个小时的逐时数据"

    response3 = requests.post(base_url, json=params3, timeout=120)
    data3 = response3.json()
    records3 = data3.get("data", {}).get("result", {}).get("resultOne", [])
    print(f"记录数: {len(records3)}")

    print("\n" + "=" * 80)
    print("结果汇总")
    print("=" * 80)
    print(f"不包含'小时级':     {len(records1)} 条")
    print(f"包含'小时级':       {len(records2)} 条")
    print(f"明确说明23个小时:   {len(records3)} 条")

    if max(len(records1), len(records2), len(records3)) >= 20:
        print("\n✓ question文本对API返回有显著影响！")
        print("建议：在question中明确包含'小时级'关键词")


if __name__ == "__main__":
    test_question_variations()
