"""
站点级新标准统计报表查询工具

基于 HJ 633-2026 新标准的站点级空气质量统计报表查询工具

【核心功能】
- 新标准综合指数计算（PM2.5权重3，O3权重2，NO2权重2，其他权重1）
- 超标天数和达标率统计
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析

【与城市工具的差异】
- 不支持扣沙处理（站点级别无扣沙数据）
- 使用 station_name 字段替代 city_name
- 支持城市名称自动展开为站点列表
- 支持多站点汇总统计（aggregate参数）
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Any
import structlog

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
from app.tools.query.query_new_standard_report.tool import (
    calculate_iaqi,
    safe_round,
    apply_rounding,
    format_pollutant_value
)

logger = structlog.get_logger()


# =============================================================================
# 常量定义（复用城市工具的常量）
# =============================================================================

# 修约精度配置
ROUNDING_PRECISION = {
    'raw_data': {
        'PM2_5': 1, 'PM10': 1, 'SO2': 1, 'NO2': 1,
        'O3_8h': 1, 'CO': 2, 'NO': 1, 'NOx': 1,
    },
    'statistical_data': {
        'PM2_5': 1, 'PM10': 1, 'SO2': 1, 'NO2': 1,
        'O3_8h': 1, 'CO': 2, 'NO': 1, 'NOx': 1,
    },
    'evaluation_data': {
        'PM2_5': 1, 'PM10': 1, 'SO2': 1, 'NO2': 1,
        'O3_8h': 1, 'CO': 2, 'exceed_multiple': 2,
        'compliance_rate': 1,
    },
    'final_output': {
        'PM2_5': 1, 'CO': 1, 'SO2': 0, 'NO2': 0,
        'PM10': 0, 'O3_8h': 0,
    },
    'other': {
        'composite_index': 3,
        'single_index': 3,
    }
}

# 新标准（HJ 633-2026）24小时平均标准限值
STANDARD_LIMITS = {
    'PM2_5': 60,
    'PM10': 120,
    'SO2': 150,
    'NO2': 80,
    'CO': 4,
    'O3_8h': 160
}

# 权重配置（PM2.5取3，O3、NO2取2）
WEIGHTS = {
    'PM2_5': 3,
    'PM10': 1,
    'SO2': 1,
    'NO2': 2,
    'CO': 1,
    'O3_8h': 2
}

# 污染物映射（不同命名方式的统一）
POLLUTANT_ALIASES = {
    'PM2.5': 'PM2_5',
    'PM10': 'PM10',
    'SO2': 'SO2',
    'NO2': 'NO2',
    'CO': 'CO',
    'O3': 'O3_8h',
    'O3_8h': 'O3_8h',
    'O3_8H': 'O3_8h',
}


# =============================================================================
# 辅助函数
# =============================================================================

def calculate_percentile(values: List[float], percentile: float) -> Optional[float]:
    """
    计算百分位数

    Args:
        values: 数值列表
        percentile: 百分位数（如 95, 90, 98）

    Returns:
        百分位数值
    """
    if not values:
        return None

    # 过滤掉None值
    valid_values = [v for v in values if v is not None]
    if not valid_values:
        return None

    # 排序
    sorted_values = sorted(valid_values)
    n = len(sorted_values)

    # 计算位置
    position = (percentile / 100) * (n - 1)

    # 线性插值
    lower = int(position)
    upper = min(lower + 1, n - 1)

    if lower == upper:
        return sorted_values[lower]

    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    if value is None or value == '' or value == '-':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_measurement(record: Dict, pollutant: str) -> Optional[float]:
    """
    从记录中获取污染物浓度值

    支持多种字段名称格式

    Args:
        record: 数据记录
        pollutant: 污染物名称（如 'PM2_5'）

    Returns:
        浓度值
    """
    measurements = record.get("measurements", {})

    # 尝试从 measurements 字段获取
    if pollutant in measurements:
        return safe_float(measurements[pollutant])

    # 尝试不同的命名方式
    for alias, standard in POLLUTANT_ALIASES.items():
        if standard == pollutant:
            if alias in measurements:
                return safe_float(measurements[alias])
            # 尝试从顶层字段获取
            if alias in record:
                return safe_float(record[alias])

    return None


# =============================================================================
# 站点统计计算函数
# =============================================================================

def _calculate_station_statistics(
    records: List[Dict],
    station_name: str
) -> Dict[str, Any]:
    """
    计算单个站点的新标准统计指标

    Args:
        records: 站点日报数据列表
        station_name: 站点名称

    Returns:
        站点统计结果
    """
    if not records:
        return {
            "station_name": station_name,
            "error": "无数据"
        }

    # 初始化统计变量
    total_days = len(records)
    valid_days = 0
    exceed_days = 0
    composite_index_sum = 0.0

    # 污染物浓度列表
    pm25_values = []
    pm10_values = []
    so2_values = []
    no2_values = []
    co_values = []
    o3_8h_values = []

    # 首要污染物统计
    primary_pollutant_days = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }
    total_primary_days = 0

    # 各污染物超标天数
    exceed_days_by_pollutant = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }

    # 首要污染物超标天（某污染物既是首要污染物又超标）
    primary_pollutant_exceed_days = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }

    # 单项质量指数列表（用于计算综合指数）
    single_index_sums = {
        "PM2_5": 0.0,
        "PM10": 0.0,
        "SO2": 0.0,
        "NO2": 0.0,
        "CO": 0.0,
        "O3_8h": 0.0
    }

    # 遍历所有记录
    for record in records:
        # 获取日期
        date_field = record.get("timestamp") or record.get("timePoint", "")
        if not date_field:
            continue

        valid_days += 1

        # 获取各污染物浓度
        pm25 = get_measurement(record, "PM2_5")
        pm10 = get_measurement(record, "PM10")
        so2 = get_measurement(record, "SO2")
        no2 = get_measurement(record, "NO2")
        co = get_measurement(record, "CO")
        o3_8h = get_measurement(record, "O3_8h")

        # 保存浓度值
        if pm25 is not None:
            pm25_values.append(pm25)
        if pm10 is not None:
            pm10_values.append(pm10)
        if so2 is not None:
            so2_values.append(so2)
        if no2 is not None:
            no2_values.append(no2)
        if co is not None:
            co_values.append(co)
        if o3_8h is not None:
            o3_8h_values.append(o3_8h)

        # 计算IAQI
        iaqi_pm25 = calculate_iaqi(pm25 if pm25 else 0, "PM2_5")
        iaqi_pm10 = calculate_iaqi(pm10 if pm10 else 0, "PM10")
        iaqi_so2 = calculate_iaqi(so2 if so2 else 0, "SO2")
        iaqi_no2 = calculate_iaqi(no2 if no2 else 0, "NO2")
        iaqi_co = calculate_iaqi(co if co else 0, "CO")
        iaqi_o3_8h = calculate_iaqi(o3_8h if o3_8h else 0, "O3_8h")

        # 计算单项质量指数（浓度/标准限值）
        si_pm25 = (pm25 if pm25 else 0) / STANDARD_LIMITS['PM2_5']
        si_pm10 = (pm10 if pm10 else 0) / STANDARD_LIMITS['PM10']
        si_so2 = (so2 if so2 else 0) / STANDARD_LIMITS['SO2']
        si_no2 = (no2 if no2 else 0) / STANDARD_LIMITS['NO2']
        si_co = (co if co else 0) / STANDARD_LIMITS['CO']
        si_o3_8h = (o3_8h if o3_8h else 0) / STANDARD_LIMITS['O3_8h']

        # 累加单项质量指数
        single_index_sums["PM2_5"] += si_pm25
        single_index_sums["PM10"] += si_pm10
        single_index_sums["SO2"] += si_so2
        single_index_sums["NO2"] += si_no2
        single_index_sums["CO"] += si_co
        single_index_sums["O3_8h"] += si_o3_8h

        # 判断首要污染物（IAQI最大的污染物）
        iaqi_values = {
            "PM2_5": iaqi_pm25,
            "PM10": iaqi_pm10,
            "SO2": iaqi_so2,
            "NO2": iaqi_no2,
            "CO": iaqi_co,
            "O3_8h": iaqi_o3_8h
        }

        max_iaqi = max(iaqi_values.values())
        if max_iaqi > 50:
            # 找出IAQI最大的污染物
            primary_pollutants = [p for p, iaqi in iaqi_values.items() if iaqi == max_iaqi]
            if primary_pollutants:
                primary = primary_pollutants[0]
                primary_pollutant_days[primary] += 1
                total_primary_days += 1

                # 判断首要污染物是否超标
                if si_pm25 > 1 and primary == "PM2_5":
                    primary_pollutant_exceed_days["PM2_5"] += 1
                elif si_pm10 > 1 and primary == "PM10":
                    primary_pollutant_exceed_days["PM10"] += 1
                elif si_so2 > 1 and primary == "SO2":
                    primary_pollutant_exceed_days["SO2"] += 1
                elif si_no2 > 1 and primary == "NO2":
                    primary_pollutant_exceed_days["NO2"] += 1
                elif si_co > 1 and primary == "CO":
                    primary_pollutant_exceed_days["CO"] += 1
                elif si_o3_8h > 1 and primary == "O3_8h":
                    primary_pollutant_exceed_days["O3_8h"] += 1

        # 判断是否超标（任意污染物单项质量指数 > 1）
        day_exceeded = (
            si_pm25 > 1 or si_pm10 > 1 or si_so2 > 1 or
            si_no2 > 1 or si_co > 1 or si_o3_8h > 1
        )

        if day_exceeded:
            exceed_days += 1
            # 统计各污染物超标天数
            if si_pm25 > 1:
                exceed_days_by_pollutant["PM2_5"] += 1
            if si_pm10 > 1:
                exceed_days_by_pollutant["PM10"] += 1
            if si_so2 > 1:
                exceed_days_by_pollutant["SO2"] += 1
            if si_no2 > 1:
                exceed_days_by_pollutant["NO2"] += 1
            if si_co > 1:
                exceed_days_by_pollutant["CO"] += 1
            if si_o3_8h > 1:
                exceed_days_by_pollutant["O3_8h"] += 1

        # 计算当日综合指数
        day_composite_index = (
            si_pm25 * WEIGHTS['PM2_5'] +
            si_pm10 * WEIGHTS['PM10'] +
            si_so2 * WEIGHTS['SO2'] +
            si_no2 * WEIGHTS['NO2'] +
            si_co * WEIGHTS['CO'] +
            si_o3_8h * WEIGHTS['O3_8h']
        ) / sum(WEIGHTS.values())

        composite_index_sum += day_composite_index

    # 计算平均单项质量指数
    avg_single_indexes = {}
    for pollutant in single_index_sums:
        if valid_days > 0:
            avg_single_indexes[pollutant] = safe_round(
                single_index_sums[pollutant] / valid_days,
                3
            )
        else:
            avg_single_indexes[pollutant] = 0.0

    # 计算综合指数
    composite_index = 0.0
    if valid_days > 0:
        composite_index = safe_round(composite_index_sum / valid_days, 3)

    # 计算超标率和达标率
    exceed_rate = 0.0
    compliance_rate = 0.0
    if valid_days > 0:
        exceed_rate = safe_round((exceed_days / valid_days) * 100, 1)
        compliance_rate = safe_round(100 - exceed_rate, 1)

    # 计算百分位数
    PM2_5_P95 = calculate_percentile(pm25_values, 95)
    PM10_P95 = calculate_percentile(pm10_values, 95)
    SO2_P98 = calculate_percentile(so2_values, 98)
    NO2_P98 = calculate_percentile(no2_values, 98)
    CO_P95 = calculate_percentile(co_values, 95)
    O3_8h_P90 = calculate_percentile(o3_8h_values, 90)

    # 计算平均浓度
    avg_PM2_5 = safe_round(sum(pm25_values) / len(pm25_values), 1) if pm25_values else None
    avg_PM10 = safe_round(sum(pm10_values) / len(pm10_values), 1) if pm10_values else None
    avg_SO2 = safe_round(sum(so2_values) / len(so2_values), 1) if so2_values else None
    avg_NO2 = safe_round(sum(no2_values) / len(no2_values), 1) if no2_values else None
    avg_CO = safe_round(sum(co_values) / len(co_values), 2) if co_values else None
    avg_O3_8h = safe_round(sum(o3_8h_values) / len(o3_8h_values), 1) if o3_8h_values else None

    # 构建结果
    result = {
        "station_name": station_name,
        "composite_index": composite_index,
        "exceed_days": exceed_days,
        "exceed_rate": exceed_rate,
        "compliance_rate": compliance_rate,
        "total_days": total_days,
        "valid_days": valid_days,

        # 平均浓度
        "PM2_5": avg_PM2_5,
        "PM10": avg_PM10,
        "SO2": avg_SO2,
        "NO2": avg_NO2,
        "CO": avg_CO,
        "O3_8h": avg_O3_8h,

        # 百分位数
        "PM2_5_P95": apply_rounding(PM2_5_P95, 'PM2_5', 'statistical_data') if PM2_5_P95 is not None else None,
        "PM10_P95": apply_rounding(PM10_P95, 'PM10', 'statistical_data') if PM10_P95 is not None else None,
        "SO2_P98": apply_rounding(SO2_P98, 'SO2', 'statistical_data') if SO2_P98 is not None else None,
        "NO2_P98": apply_rounding(NO2_P98, 'NO2', 'statistical_data') if NO2_P98 is not None else None,
        "CO_P95": apply_rounding(CO_P95, 'CO', 'statistical_data') if CO_P95 is not None else None,
        "O3_8h_P90": apply_rounding(O3_8h_P90, 'O3_8h', 'statistical_data') if O3_8h_P90 is not None else None,

        # 单项质量指数
        "single_indexes": {
            "PM2_5": avg_single_indexes["PM2_5"],
            "PM10": avg_single_indexes["PM10"],
            "SO2": avg_single_indexes["SO2"],
            "NO2": avg_single_indexes["NO2"],
            "CO": avg_single_indexes["CO"],
            "O3_8h": avg_single_indexes["O3_8h"]
        },

        # 首要污染物统计
        "primary_pollutant_days": primary_pollutant_days,
        "total_primary_days": total_primary_days,

        # 超标统计
        "exceed_days_by_pollutant": exceed_days_by_pollutant,

        # 首要污染物超标天
        "primary_pollutant_exceed_days": primary_pollutant_exceed_days,
    }

    return result


def _calculate_station_aggregate_stats(station_results: List[Dict]) -> Dict[str, Any]:
    """
    计算多站点汇总统计（算术平均）

    Args:
        station_results: 各站点统计结果列表

    Returns:
        汇总统计结果
    """
    if not station_results:
        return {}

    # 过滤掉有错误的站点
    valid_results = [r for r in station_results if "error" not in r]
    if not valid_results:
        return {}

    n = len(valid_results)

    # 初始化累加变量
    composite_index_sum = 0.0
    exceed_days_sum = 0
    total_days_sum = 0
    valid_days_sum = 0

    # 污染物浓度累加
    pm25_sum = 0.0
    pm10_sum = 0.0
    so2_sum = 0.0
    no2_sum = 0.0
    co_sum = 0.0
    o3_8h_sum = 0.0

    # 百分位数累加
    pm25_p95_sum = 0.0
    pm10_p95_sum = 0.0
    so2_p98_sum = 0.0
    no2_p98_sum = 0.0
    co_p95_sum = 0.0
    o3_8h_p90_sum = 0.0

    # 单项质量指数累加
    single_index_sums = {
        "PM2_5": 0.0,
        "PM10": 0.0,
        "SO2": 0.0,
        "NO2": 0.0,
        "CO": 0.0,
        "O3_8h": 0.0
    }

    # 首要污染物天数累加
    primary_pollutant_sums = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }
    total_primary_sum = 0

    # 超标天数累加
    exceed_by_pollutant_sums = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }

    # 首要污染物超标天数累加
    primary_exceed_sums = {
        "PM2_5": 0,
        "PM10": 0,
        "SO2": 0,
        "NO2": 0,
        "CO": 0,
        "O3_8h": 0
    }

    # 遍历所有站点
    for result in valid_results:
        composite_index_sum += result.get("composite_index", 0)
        exceed_days_sum += result.get("exceed_days", 0)
        total_days_sum += result.get("total_days", 0)
        valid_days_sum += result.get("valid_days", 0)

        # 累加浓度
        if result.get("PM2_5") is not None:
            pm25_sum += result["PM2_5"]
        if result.get("PM10") is not None:
            pm10_sum += result["PM10"]
        if result.get("SO2") is not None:
            so2_sum += result["SO2"]
        if result.get("NO2") is not None:
            no2_sum += result["NO2"]
        if result.get("CO") is not None:
            co_sum += result["CO"]
        if result.get("O3_8h") is not None:
            o3_8h_sum += result["O3_8h"]

        # 累加百分位数
        if result.get("PM2_5_P95") is not None:
            pm25_p95_sum += result["PM2_5_P95"]
        if result.get("PM10_P95") is not None:
            pm10_p95_sum += result["PM10_P95"]
        if result.get("SO2_P98") is not None:
            so2_p98_sum += result["SO2_P98"]
        if result.get("NO2_P98") is not None:
            no2_p98_sum += result["NO2_P98"]
        if result.get("CO_P95") is not None:
            co_p95_sum += result["CO_P95"]
        if result.get("O3_8h_P90") is not None:
            o3_8h_p90_sum += result["O3_8h_P90"]

        # 累加单项质量指数
        single_indexes = result.get("single_indexes", {})
        for p in single_index_sums:
            single_index_sums[p] += single_indexes.get(p, 0)

        # 累加首要污染物天数
        primary_days = result.get("primary_pollutant_days", {})
        for p in primary_pollutant_sums:
            primary_pollutant_sums[p] += primary_days.get(p, 0)
        total_primary_sum += result.get("total_primary_days", 0)

        # 累加超标天数
        exceed_days = result.get("exceed_days_by_pollutant", {})
        for p in exceed_by_pollutant_sums:
            exceed_by_pollutant_sums[p] += exceed_days.get(p, 0)

        # 累加首要污染物超标天数
        primary_exceed = result.get("primary_pollutant_exceed_days", {})
        for p in primary_exceed_sums:
            primary_exceed_sums[p] += primary_exceed.get(p, 0)

    # 计算平均值
    aggregate_result = {
        "station_name": "多站点汇总",
        "composite_index": safe_round(composite_index_sum / n, 3) if n > 0 else 0,
        "exceed_days": exceed_days_sum,
        "total_days": total_days_sum,
        "valid_days": valid_days_sum,
        "exceed_rate": safe_round((exceed_days_sum / valid_days_sum) * 100, 1) if valid_days_sum > 0 else 0,
        "compliance_rate": safe_round(100 - (exceed_days_sum / valid_days_sum) * 100, 1) if valid_days_sum > 0 else 100,

        # 平均浓度
        "PM2_5": safe_round(pm25_sum / n, 1) if pm25_sum > 0 else None,
        "PM10": safe_round(pm10_sum / n, 1) if pm10_sum > 0 else None,
        "SO2": safe_round(so2_sum / n, 1) if so2_sum > 0 else None,
        "NO2": safe_round(no2_sum / n, 1) if no2_sum > 0 else None,
        "CO": safe_round(co_sum / n, 2) if co_sum > 0 else None,
        "O3_8h": safe_round(o3_8h_sum / n, 1) if o3_8h_sum > 0 else None,

        # 平均百分位数
        "PM2_5_P95": safe_round(pm25_p95_sum / n, 1) if pm25_p95_sum > 0 else None,
        "PM10_P95": safe_round(pm10_p95_sum / n, 1) if pm10_p95_sum > 0 else None,
        "SO2_P98": safe_round(so2_p98_sum / n, 1) if so2_p98_sum > 0 else None,
        "NO2_P98": safe_round(no2_p98_sum / n, 1) if no2_p98_sum > 0 else None,
        "CO_P95": safe_round(co_p95_sum / n, 2) if co_p95_sum > 0 else None,
        "O3_8h_P90": safe_round(o3_8h_p90_sum / n, 1) if o3_8h_p90_sum > 0 else None,

        # 平均单项质量指数
        "single_indexes": {
            "PM2_5": safe_round(single_index_sums["PM2_5"] / n, 3) if n > 0 else 0,
            "PM10": safe_round(single_index_sums["PM10"] / n, 3) if n > 0 else 0,
            "SO2": safe_round(single_index_sums["SO2"] / n, 3) if n > 0 else 0,
            "NO2": safe_round(single_index_sums["NO2"] / n, 3) if n > 0 else 0,
            "CO": safe_round(single_index_sums["CO"] / n, 3) if n > 0 else 0,
            "O3_8h": safe_round(single_index_sums["O3_8h"] / n, 3) if n > 0 else 0,
        },

        # 平均首要污染物天数
        "primary_pollutant_days": {
            "PM2_5": primary_pollutant_sums["PM2_5"],
            "PM10": primary_pollutant_sums["PM10"],
            "SO2": primary_pollutant_sums["SO2"],
            "NO2": primary_pollutant_sums["NO2"],
            "CO": primary_pollutant_sums["CO"],
            "O3_8h": primary_pollutant_sums["O3_8h"],
        },
        "total_primary_days": total_primary_sum,

        # 累计超标天数
        "exceed_days_by_pollutant": exceed_by_pollutant_sums,

        # 累计首要污染物超标天数
        "primary_pollutant_exceed_days": primary_exceed_sums,
    }

    return aggregate_result


def execute_query_station_new_standard_report(
    cities: Optional[List[str]] = None,
    stations: Optional[List[str]] = None,
    start_date: str = None,
    end_date: str = None,
    aggregate: bool = False,
    context: ExecutionContext = None,
    station_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行站点新标准统计报表查询

    Args:
        cities: 城市名称列表（自动展开为站点）
        stations: 站点名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        aggregate: 是否计算多站点汇总统计
        context: 执行上下文
        station_type: 站点类型（如"国控"/"省控"/"市控"或"1.0"/"2.0"/"3.0"）

    Returns:
        查询结果
    """
    logger.info(
        "query_station_new_standard_report_start",
        cities=cities,
        stations=stations,
        start_date=start_date,
        end_date=end_date,
        aggregate=aggregate,
        station_type=station_type
    )

    try:
        # 1. 查询站点日报数据
        query_result = QueryGDSuncereDataTool.query_station_day_data(
            cities=cities,
            stations=stations,
            start_date=start_date,
            end_date=end_date,
            context=context,
            station_type=station_type
        )

        if query_result.get("status") == "empty":
            return {
                "status": "empty",
                "success": True,
                "result": {},
                "summary": query_result.get("summary"),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "query_station_new_standard_report",
                    "cities": cities or [],
                    "stations": stations or [],
                }
            }

        if query_result.get("status") == "failed":
            return {
                "status": "failed",
                "success": False,
                "result": {},
                "summary": query_result.get("summary", "查询失败"),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "query_station_new_standard_report",
                    "error": query_result.get("summary"),
                }
            }

        # 2. 获取数据记录（优先从data_id获取完整数据）
        data_id = query_result.get("data_id")

        if data_id and context:
            # 从data_id获取完整数据（未采样的完整数据集）
            records = context.get_raw_data(data_id)
            logger.info(
                "loading_full_data_from_data_id",
                data_id=data_id,
                record_count=len(records) if records else 0
            )
        else:
            # 降级：从data字段获取（可能已被采样）
            records = query_result.get("data", [])
            logger.warning(
                "using_sampled_data_from_data_field",
                record_count=len(records),
                warning="统计数据可能不准确（采样数据）"
            )

        if not records:
            return {
                "status": "empty",
                "success": True,
                "result": {},
                "summary": f"未找到站点数据（{start_date}至{end_date}）",
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "query_station_new_standard_report",
                    "cities": cities or [],
                    "stations": stations or [],
                }
            }

        # 3. 按站点分组
        station_groups = {}
        for record in records:
            # 获取站点名称
            station_name = (
                record.get("station_name") or
                record.get("name") or
                record.get("station", "未知站点")
            )

            if station_name not in station_groups:
                station_groups[station_name] = []
            station_groups[station_name].append(record)

        logger.info(
            "station_data_grouped",
            stations_count=len(station_groups),
            station_names=list(station_groups.keys()),
            total_records=len(records)
        )

        # 4. 计算各站点统计
        station_results = {}
        for station_name, station_records in station_groups.items():
            station_stats = _calculate_station_statistics(
                station_records,
                station_name
            )
            station_results[station_name] = station_stats

        # 5. 计算多站点汇总（如果需要）
        if aggregate and len(station_results) > 1:
            aggregate_stats = _calculate_station_aggregate_stats(
                list(station_results.values())
            )
            station_results["station_aggregate"] = aggregate_stats

        # 6. 构建返回结果
        result = {
            "status": "success",
            "success": True,
            "result": station_results,
            "summary": f"站点新标准统计报表查询完成（{start_date}至{end_date}，共{len(station_results)}个站点，数据为审核实况）",
            "metadata": {
                "schema_version": "v2.0",
                "generator": "query_station_new_standard_report",
                "generator_version": "1.0.0",
                "cities": cities or [],
                "stations": stations or [],
                "start_date": start_date,
                "end_date": end_date,
                "aggregate": aggregate,
                "station_count": len(station_results),
            }
        }

        logger.info(
            "query_station_new_standard_report_completed",
            stations_count=len(station_results),
            aggregate_calculated=aggregate
        )

        return result

    except Exception as e:
        logger.error(
            "query_station_new_standard_report_failed",
            error=str(e),
            exc_info=True
        )
        return {
            "status": "failed",
            "success": False,
            "result": {},
            "summary": f"站点新标准统计报表查询失败: {str(e)}",
            "metadata": {
                "schema_version": "v2.0",
                "generator": "query_station_new_standard_report",
                "error": str(e),
            }
        }


class QueryStationNewStandardReportTool(LLMTool):
    """站点级新标准统计报表查询工具"""

    def __init__(self):
        function_schema = {
            "name": "query_station_new_standard_report",
            "description": """查询站点级基于 HJ 633-2026 新标准的空气质量统计报表。

【核心功能】
- 新标准综合指数计算（PM2.5权重3，O3权重2，NO2权重2，其他权重1）
- 超标天数和达标率统计
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析
- 支持按站点类型过滤（国控/省控/市控等）

【与城市工具的差异】
- 不支持扣沙处理（站点级别无扣沙数据）
- 使用 station_name 字段替代 city_name
- 支持城市名称自动展开为站点列表
- 支持多站点汇总统计（aggregate参数）

【返回数据说明】
- result字段：⭐ 完整的统计结果（包含所有站点的详细统计数据）
  - 各站点的综合指数、超标天数、达标率、六参数统计等
  - aggregate=true时，额外包含station_aggregate（多站点汇总）
  - ⚠️ 重要：result 字段包含完整的统计分析结果，**直接用于报告生成和分析**
- data_id字段：站点日报工具返回的原始数据存储标识符
  - 仅用于需要访问原始监测数据或进行聚合分析时使用
  - ⚠️ 一般情况下不需要使用此字段，result 字段已包含所有统计结果

【输入参数】
- station_type: 站点类型（可选，默认'国控'）。⚠️ 仅在使用 cities 参数时有效，用于过滤该城市下的指定类型站点。如果使用 stations 参数，则不需要此参数（站点名称已确定类型）。有效值：'国控'/'省控'/'市控' 或 '1.0'/'2.0'/'3.0'
- cities: 城市名称列表（可选，自动展开为该城市下所有站点），如 ['广州']。如果不提供 station_type，默认查询国控站点
- stations: 站点名称列表（可选，直接查询指定站点），如 ['广雅中学', '市监测站']。使用此参数时不需要提供 station_type
- start_date: 开始日期 (YYYY-MM-DD)
- end_date: 结束日期 (YYYY-MM-DD)
- aggregate: 是否计算多站点汇总统计（默认false）

【重要】
- cities 和 stations 至少提供一个（为避免数据量过大，不支持全省查询）
- station_type 为可选参数，使用 stations 时不需要提供，使用 cities 时默认为'国控'
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_type": {
                        "type": "string",
                        "description": "站点类型（可选，默认'国控'）。⚠️ 仅在使用 cities 参数时有效，用于过滤该城市下的指定类型站点。如果使用 stations 参数，则不需要此参数（站点名称已确定类型）。有效值：'国控'/'省控'/'市控' 或 '1.0'/'2.0'/'3.0'"
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（可选，自动展开为该城市下所有站点），如 ['广州']。如果不提供 station_type，默认查询国控站点"
                    },
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点名称列表（可选，直接查询指定站点），如 ['广雅中学', '市监测站']。使用此参数时不需要提供 station_type"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 YYYY-MM-DD"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 YYYY-MM-DD"
                    },
                    "aggregate": {
                        "type": "boolean",
                        "description": "是否计算多站点汇总统计（默认false）"
                    }
                },
                "required": ["start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_station_new_standard_report",
            description="Query station-level new standard report",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        """执行查询"""
        # 参数验证
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        station_type = kwargs.get("station_type")
        cities = kwargs.get("cities")
        stations = kwargs.get("stations")
        aggregate = kwargs.get("aggregate", False)

        if not start_date or not end_date:
            return {
                "status": "failed",
                "success": False,
                "result": {},
                "summary": "缺少必需参数: start_date 或 end_date",
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "query_station_new_standard_report",
                    "error": "Missing required parameters",
                }
            }

        if not cities and not stations:
            return {
                "status": "failed",
                "success": False,
                "result": {},
                "summary": "必须提供cities或stations参数。为避免数据量过大，不支持全省查询。请指定具体城市或站点。",
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "query_station_new_standard_report",
                    "error": "Missing cities or stations parameter",
                    "suggestion": "请提供需要查询的城市或站点"
                }
            }

        # 智能推断 station_type
        # 规则1: 如果使用 stations 参数，不需要 station_type（站点名称已确定类型）
        # 规则2: 如果只使用 cities 参数且没有 station_type，默认使用"国控"
        if stations and not cities:
            # 场景1: 只提供站点名称，不需要 station_type
            if station_type:
                logger.warning(
                    "query_station_new_standard_report_ignored_station_type",
                    reason="使用stations参数时，station_type将被忽略",
                    stations=stations,
                    provided_station_type=station_type
                )
            # 不传递 station_type
            effective_station_type = None
        elif cities and not stations:
            # 场景2: 只提供城市名称，使用默认的"国控"或用户指定的 station_type
            effective_station_type = station_type or "国控"
        else:
            # 场景3: 同时提供 cities 和 stations，使用用户指定的 station_type（如果有）
            effective_station_type = station_type

        # 调用同步函数（不使用await）
        return execute_query_station_new_standard_report(
            cities=cities,
            stations=stations,
            start_date=start_date,
            end_date=end_date,
            aggregate=aggregate,
            context=context,
            station_type=effective_station_type
        )
