"""
外部 API 响应格式规范

本文件记录所有外部 API 的响应数据结构，用于工具层的数据解析。
每个 API 格式应该包含：
- 响应路径：数据记录在响应中的嵌套位置
- 关键字段：站点、时间、数据字段的映射
- 字段映射：中文列名到标准英文列名的映射

使用时：工具的 _seek_records 方法应优先使用这里定义的路径

============================================================================
测试脚本使用说明
============================================================================

运行以下命令测试四个颗粒物 API 并保存返回数据：

    cd D:\溯源\backend
    python -c "
import asyncio
from app.api_response_formats import test_all_particulate_apis
asyncio.run(test_all_particulate_apis())
    "

数据将保存到：tests/test_particulate_api_responses.json

============================================================================
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.http_client import http_client

# =============================================================================
# 颗粒物 API 响应格式定义
# =============================================================================
# 四个查询类型：水溶性离子、碳组分、地壳元素、微量元素
# 响应结构：
# {
#   "data": {
#     "result": {
#       "resultOne": [...],      # 时序数据（每小时一条记录）- 水溶性离子/地壳元素/微量元素
#       "resultData": [...],     # 时序数据 - 碳组分 (OC/EC)
#       "resultTwo": {...},      # 汇总统计
#       "resultThree": [...],    # 占比数据
#       "resultFour": {...}      # 平均值
#     }
#   }
# }
# 记录字段：
#   - Code: 站点编码
#   - StationName: 站点名称
#   - TimePoint: 时间点 (YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DDTHH:MM:SS)
#   - 数据字段（中文）：硅、铝、铁、钙、钾等

# =============================================================================
# 实际API响应结构（2025-12-29 测试记录）
# =============================================================================
PARTICULATE_API_CONFIGS = {
    "水溶性离子": {
        "response_path": "data.result.resultOne",
        "fields": ["Al3+", "Br⁻", "Ca²⁺", "Cl⁻", "F⁻", "K⁺", "Li⁺", "Mg²⁺", "NH₄⁺", "NO₂⁻", "NO₃⁻", "Na⁺", "PM₂.₅", "PO₄³⁻", "SO₄²⁻"],
        "time_field": "TimePoint",
        "station_fields": {"Code": "station_code", "StationName": "station_name"},
        "notes": "使用 resultOne 路径，字段使用上标符号如 NH₄⁺"
    },
    "碳组分": {
        "response_path": "data.result.resultData",
        "fields": ["OC（TOT）", "EC（TOT）", "PM₂.₅"],
        "time_field": "TimePoint",
        "station_fields": {"Code": "station_code", "StationName": "station_name"},
        "notes": "使用 resultData 路径（非 resultOne），字段名包含括号如 OC（TOT）"
    },
    "地壳元素": {
        "response_path": "data.result.resultOne",
        "fields": ["硅", "铝", "铁", "钙"],
        "time_field": "TimePoint",
        "station_fields": {"Code": "station_code", "StationName": "station_name"},
        "notes": "使用 resultOne 路径，字段为中文"
    },
    "微量元素": {
        "response_path": "data.result.resultOne",
        "fields": ["钛", "钾", "铁"],  # 注：API可能返回非请求的字段
        "time_field": "TimePoint",
        "station_fields": {"Code": "station_code", "StationName": "station_name"},
        "notes": "使用 resultOne 路径，API可能返回钾(K)、钛(Ti)、铁(Fe)而非请求的锌/铅/铜"
    }
}

PARTICULATE_API_FORMAT = {
    "endpoint": "180.184.91.74:9093/api/uqp/query",
    "description": "颗粒物组分数据查询 API（水溶性离子、碳组分、地壳元素、微量元素）",
    "response_path": "data.result.resultOne",  # 默认路径，水溶性离子/地壳元素/微量元素
    "alt_response_path": "data.result.resultData",  # 备选路径，碳组分使用
    "record_keys": {
        # 字段映射：API 列名 -> 标准字段名
        "Code": "station_code",
        "StationName": "station_name",
        "TimePoint": "timestamp",
        # 地壳元素
        "硅": "silicon",
        "铝": "aluminum",
        "铁": "iron",
        "钙": "calcium",
        "镁": "magnesium",
        "钛": "titanium",
        # 微量元素/重金属
        "钾": "potassium",
        "锌": "zinc",
        "铅": "lead",
        "铜": "copper",
        "镉": "cadmium",
        "铬": "chromium",
        "镍": "nickel",
        "砷": "arsenic",
        "汞": "mercury",
        "锰": "manganese",
        # 水溶性离子
        "硝酸盐": "nitrate",
        "硫酸盐": "sulfate",
        "铵盐": "ammonium",
        "钙离子": "calcium_ion",
        "镁离子": "magnesium_ion",
        "钾离子": "potassium_ion",
        "钠离子": "sodium_ion",
        "氯离子": "chloride",
        # 碳组分
        "OC（TOT）": "organic_carbon",
        "EC（TOT）": "elemental_carbon",
    },
    "notes": [
        "resultOne 包含小时级时序数据（水溶性离子、地壳元素、微量元素）",
        "resultData 包含小时级时序数据（碳组分 OC/EC）",
        "resultThree 包含各组分占比（百分比）",
        "resultFour 包含整体平均值统计",
        "数据单位：通常为 ug/m3 或 ng/m3",
        "水溶性离子字段使用上标符号：NH₄⁺, SO₄²⁻, NO₃⁻ 等",
        "碳组分字段名包含括号：OC（TOT）, EC（TOT）",
    ]
}

# =============================================================================
# VOCs API (180.184.91.74:9091 /api/uqp/query)
# =============================================================================
VOCs_API_FORMAT = {
    "endpoint": "180.184.91.74:9091/api/uqp/query",
    "description": "VOCs 监测数据查询 API",
    "response_path": "dataList",  # 或 data
    "record_keys": {
        "mtime": "timestamp",
        "stationcode": "station_code",
        "stationname": "station_name",
    },
    "notes": [
        "VOCs 物种字段作为动态字段保留",
        "物种数据通过 species_data 字段聚合保存",
        "单位：通常为 ppb 或 ug/m3",
    ]
}

# =============================================================================
# 气象数据 API (180.184.91.74:9095)
# =============================================================================
WEATHER_API_FORMAT = {
    "endpoint": "180.184.91.74:9095",
    "description": "气象数据查询 API（多接口）",
    "response_paths": ["data", "dataList", "result", "records"],
    "record_keys": {
        "time": "timestamp",
        "station_code": "station_code",
        "station_name": "station_name",
    },
    "notes": [
        "气象数据有多个子接口，响应格式略有不同",
        "常见字段：temperature_2m, relative_humidity, pressure, wind_speed, wind_direction 等",
        "单位：temperature(C), humidity(%), pressure(hPa), wind(m/s)",
    ]
}

# =============================================================================
# 空气质量数据 API (180.184.91.74:9092)
# =============================================================================
AIR_QUALITY_API_FORMAT = {
    "endpoint": "180.184.91.74:9092/api/uqp/query",
    "description": "空气质量监测数据查询 API（PM2.5, PM10, O3, NO2 等）",
    "response_path": "data",
    "record_keys": {
        "time": "timestamp",
        "station_code": "station_code",
        "station_name": "station_name",
        "PM2.5": "pm25",
        "PM10": "pm10",
        "O3": "o3",
        "NO2": "no2",
        "SO2": "so2",
        "CO": "co",
        "AQI": "aqi",
    },
    "notes": [
        "污染物浓度单位：通常为 ug/m3",
        "AQI 为无量纲指数",
    ]
}

# =============================================================================
# 上风向分析 API
# =============================================================================
UPWIND_API_FORMAT = {
    "endpoint": "180.184.91.74:9095 (相关接口)",
    "description": "上风向分析相关 API",
    "notes": [
        "响应格式因具体接口而异",
        "通常包含站点信息、坐标、排放源信息等",
    ]
}

# =============================================================================
# 格式注册表（供工具层引用）
# =============================================================================
API_FORMATS_REGISTRY = {
    "particulate": PARTICULATE_API_FORMAT,
    "vocs": VOCs_API_FORMAT,
    "weather": WEATHER_API_FORMAT,
    "air_quality": AIR_QUALITY_API_FORMAT,
    "upwind": UPWIND_API_FORMAT,
}


def get_api_format(api_type: str) -> Optional[Dict[str, Any]]:
    """获取指定 API 类型的格式定义"""
    return API_FORMATS_REGISTRY.get(api_type)


def get_response_path(api_type: str) -> str:
    """获取指定 API 类型的响应数据路径"""
    fmt = get_api_format(api_type)
    if fmt:
        return fmt.get("response_path", fmt.get("response_paths", ["data"])[0])
    return "data"


# =============================================================================
# 测试脚本：测试四个颗粒物 API 并保存返回数据
# =============================================================================

PARTICULATE_API_URL = "http://180.184.91.74:9093/api/uqp/query"

# 四个测试查询
PARTICULATE_TESTS = [
    {
        "name": "水溶性离子",
        "question": "查询揭阳市2024-12-24期间的小时级PM2.5水溶性离子数据，必须包含硫酸盐(SO4)、硝酸盐(NO3)、铵盐(NH4)"
    },
    {
        "name": "碳组分",
        "question": "查询揭阳市2024-12-24期间的小时级PM2.5碳组分数据，必须包含有机碳(OC)、元素碳(EC)"
    },
    {
        "name": "地壳元素",
        "question": "查询揭阳市2024-12-24期间的小时级PM2.5地壳元素数据，必须包含铝(Al)、硅(Si)、铁(Fe)、钙(Ca)"
    },
    {
        "name": "微量元素",
        "question": "查询揭阳市2024-12-24期间的小时级PM2.5微量元素/重金属数据，必须包含锌(Zn)、铅(Pb)、铜(Cu)"
    }
]


def find_all_records(obj: Any, depth: int = 0, max_depth: int = 5) -> List[List[Dict[str, Any]]]:
    """递归查找所有可能的记录列表"""
    if depth > max_depth:
        return []

    results = []

    if isinstance(obj, list):
        if len(obj) > 0:
            first = obj[0]
            if isinstance(first, dict):
                results.append(obj)
                return results
            elif isinstance(first, list):
                for sublist in obj:
                    sub_results = find_all_records(sublist, depth + 1, max_depth)
                    results.extend(sub_results)
        return results

    if isinstance(obj, dict):
        for key, value in obj.items():
            sub_results = find_all_records(value, depth + 1, max_depth)
            results.extend(sub_results)

    return results


async def test_single_particulate_api(name: str, question: str) -> Dict[str, Any]:
    """测试单个颗粒物 API 并返回结果"""
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"问题: {question[:50]}...")
    print('='*60)

    try:
        response = await http_client.post(
            PARTICULATE_API_URL,
            json_data={"question": question},
            timeout=120
        )

        # 分析响应结构
        result = {
            "name": name,
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "response_type": type(response).__name__,
        }

        if isinstance(response, dict):
            result["response_keys"] = list(response.keys())

            # 查找所有列表
            all_lists = find_all_records(response)
            result["all_list_counts"] = [
                len(lst) for lst in all_lists if isinstance(lst, list)
            ]

            for i, lst in enumerate(all_lists):
                if len(lst) > 0:
                    first = lst[0]
                    if isinstance(first, dict):
                        result[f"list_{i+1}_count"] = len(lst)
                        result[f"list_{i+1}_first_keys"] = list(first.keys())[:20]

            result["raw_response"] = response
            result["status"] = "success"
        else:
            result["raw_response"] = str(response)[:5000]
            result["status"] = "unexpected_type"

        return result

    except Exception as e:
        import traceback
        print(f"错误: {e}")
        traceback.print_exc()
        return {
            "name": name,
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }


async def test_all_particulate_apis() -> Dict[str, Any]:
    """测试所有四个颗粒物 API 并保存结果"""
    results = {
        "test_time": datetime.now().isoformat(),
        "api_url": PARTICULATE_API_URL,
        "tests": []
    }

    for test in PARTICULATE_TESTS:
        result = await test_single_particulate_api(test["name"], test["question"])
        results["tests"].append(result)

    # 保存结果到 backend 目录下的 tests 文件夹
    import os
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_file = os.path.join(backend_dir, "tests", "test_particulate_api_responses.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"测试完成！结果已保存到: {output_file}")
    print('='*60)

    # 打印摘要
    print("\n摘要:")
    for test in results["tests"]:
        status = test.get("status", "unknown")
        list_counts = test.get("all_list_counts", [])
        if status == "success":
            print(f"  - {test['name']}: 成功, 找到 {len(list_counts)} 个列表, 记录数: {list_counts}")
        else:
            print(f"  - {test['name']}: {status}")

    return results


# =============================================================================
# 便捷命令
# =============================================================================

if __name__ == "__main__":
    print("运行四个颗粒物 API 测试...")
    print("="*60)
    asyncio.run(test_all_particulate_apis())
