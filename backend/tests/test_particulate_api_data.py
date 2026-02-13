"""
测试颗粒物API返回数据

验证目的：
1. 检查API返回的水溶性离子数据字段
2. 检查API返回的碳组分数据字段
3. 验证PMF分析所需的5个核心组分是否齐全：SO4, NO3, NH4, OC, EC
"""

import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, List
import json


async def test_particulate_api():
    """测试颗粒物API返回的数据格式"""

    base_url = "http://180.184.91.74:9093"
    timeout = httpx.Timeout(120.0)

    print("=" * 80)
    print("颗粒物API数据测试")
    print("=" * 80)

    # 测试1: 水溶性离子数据
    print("\n【测试1】水溶性离子数据查询")
    print("-" * 80)

    ion_query = {
        "question": "查询东莞市2026-01-27期间的小时级PM2.5水溶性离子数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2026-01-27 00:00:00",
        "TimeEnd": "2026-01-27 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["SO4", "NO3", "NH4", "Cl", "Ca", "Mg", "K", "Na", "F"],
        "Station": "东莞",
        "Code": "1037b"
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/api/uqp/query", json=ion_query)
        if resp.status_code == 200:
            data = resp.json()
            print_data_analysis("水溶性离子", data)
        else:
            print(f"[ERROR] 请求失败: {resp.status_code}")

    # 测试2: 碳组分数据
    print("\n【测试2】碳组分数据查询")
    print("-" * 80)

    carbon_query = {
        "question": "查询东莞市2026-01-27期间的小时级PM2.5碳组分数据",
        "Detect": "ComponentPm25/GetComponentPm25Analysis",
        "TimeStart": "2026-01-27 00:00:00",
        "TimeEnd": "2026-01-27 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Station": "东莞",
        "Code": "1037b"
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/api/uqp/query", json=carbon_query)
        if resp.status_code == 200:
            data = resp.json()
            print_data_analysis("碳组分", data)
        else:
            print(f"[ERROR] 请求失败: {resp.status_code}")

    # 测试3: 地壳元素数据
    print("\n【测试3】地壳元素数据查询")
    print("-" * 80)

    crustal_query = {
        "question": "查询东莞市2026-01-27期间的小时级PM2.5地壳元素数据",
        "Detect": "ElementCompositionAnalysis/GetChartAnalysis",
        "TimeStart": "2026-01-27 00:00:00",
        "TimeEnd": "2026-01-27 23:59:59",
        "TimeType": "Hour",
        "DataType": "PM2_5",
        "Columns": ["Al", "Si", "Fe", "Ca", "Ti", "Mn", "Zn", "Pb", "Cu", "Ni", "Cr", "Cd"],
        "Station": "东莞",
        "Code": "1037b"
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/api/uqp/query", json=crustal_query)
        if resp.status_code == 200:
            data = resp.json()
            print_data_analysis("地壳元素", data)
        else:
            print(f"[ERROR] 请求失败: {resp.status_code}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


def print_data_analysis(data_type: str, response: Dict[str, Any]):
    """分析并打印API返回数据"""

    print(f"\n数据类型: {data_type}")
    print(f"响应键: {list(response.keys())}")

    # 提取数据路径
    if "data" in response:
        data_obj = response["data"]
        if "result" in data_obj:
            result = data_obj["result"]

            # 检查resultOne或resultData
            records = []
            if "resultOne" in result:
                records = result["resultOne"]
                data_path = "data.result.resultOne"
            elif "resultData" in result:
                records = result["resultData"]
                data_path = "data.result.resultData"
            else:
                print(f"[WARNING] 未找到resultOne或resultData字段")
                print(f"result的键: {list(result.keys())}")
                return

            print(f"数据路径: {data_path}")
            print(f"记录数量: {len(records)}")

            if len(records) > 0:
                first_record = records[0]
                print(f"\n第一条记录的字段:")
                print(f"  键: {list(first_record.keys())}")

                # 分析组分字段
                component_fields = []
                for key in first_record.keys():
                    # 排除元数据字段
                    if key not in ["TimePoint", "TimeType", "DataType", "Code", "StationName",
                                   "PM₂.₅", "PM2_5", "AQI", "id", "timestamp"]:
                        component_fields.append(key)

                print(f"\n组分字段 ({len(component_fields)}个):")
                for field in sorted(component_fields):
                    value = first_record[field]
                    # 显示前几条记录的值
                    sample_values = []
                    for i in range(min(3, len(records))):
                        val = records[i].get(field)
                        if val is not None and val != "":
                            sample_values.append(str(val))
                    print(f"  {field}: {sample_values[:3]}")

                # PMF核心组分检查
                pmf_required = {"SO4", "NO3", "NH4", "OC", "EC"}
                pmf_available = set()

                # 标准化字段名检查
                normalized_fields = set()
                for field in component_fields:
                    normalized = field.replace(" ", "").replace("_", "").replace("⁻", "").replace("²", "").replace("+", "")
                    normalized_fields.add(normalized)
                    normalized_fields.add(field)

                for required in pmf_required:
                    if required in normalized_fields:
                        pmf_available.add(required)

                print(f"\n【PMF核心组分检查】")
                print(f"  要求: {', '.join(sorted(pmf_required))}")
                print(f"  已找到: {', '.join(sorted(pmf_available))}")
                print(f"  缺失: {', '.join(sorted(pmf_required - pmf_available))}")
                print(f"  覆盖率: {len(pmf_available) / len(pmf_required) * 100:.1f}%")

                if len(pmf_available) >= 3:
                    print(f"  ✓ 满足PMF最低要求（≥3个核心组分）")
                else:
                    print(f"  ✗ 不满足PMF最低要求（≥3个核心组分）")

            else:
                print("[WARNING] 没有记录数据")

        else:
            print(f"[WARNING] data中没有result字段")
            print(f"data的键: {list(data_obj.keys())}")
    else:
        print(f"[WARNING] 响应中没有data字段")


if __name__ == "__main__":
    asyncio.run(test_particulate_api())
