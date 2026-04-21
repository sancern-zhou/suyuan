"""
数值修约规则模块

基于 GB/T 8170-2008 数值修约规则与 HJ 633-2026 标准

说明：
1. 原始监测数据：污染物原始监测数据（小时或日数据）的保留小数位数要求
2. 统计数据：基于日数据计算月、季、年均值及特定百分位数时的保留小数位数
   - 统计数据可比日数据多保留1位小数或同日数据
   - PM2.5：日数据0位 → 统计数据1位（多保留1位）
   - 其他污染物：统计数据同日数据
"""

from typing import Union


# 修约精度配置（GB/T 8170-2008 数值修约规则）
ROUNDING_PRECISION = {
    # 原始监测数据（小时或日数据）- "原始监测数据"列
    'raw_data': {
        'PM2_5': 0,      # μg/m³，保留0位
        'PM10': 0,       # μg/m³，保留0位
        'SO2': 0,        # μg/m³，保留0位
        'NO2': 0,        # μg/m³，保留0位
        'O3_8h': 0,      # μg/m³，保留0位
        'CO': 1,         # mg/m³，保留1位
        'O3': 0,         # μg/m³，保留0位
        'NO': 0,         # μg/m³，保留0位
        'NOx': 0,        # μg/m³，保留0位
    },
    # 统计数据（月、季、年均值及特定百分位数）- "统计数据"列（新标准）
    # 基于日数据计算时，可比日数据多保留1位或同日数据
    'statistical_data': {
        'PM2_5': 1,      # μg/m³，保留1位（日数据0位，多保留1位）
        'PM10': 1,       # μg/m³，保留1位（日数据0位，多保留1位）
        'SO2': 1,        # μg/m³，保留1位（日数据0位，多保留1位）
        'NO2': 1,        # μg/m³，保留1位（日数据0位，多保留1位）
        'O3_8h': 1,      # μg/m³，保留1位（日数据0位，多保留1位）
        'CO': 2,         # mg/m³，保留2位（日数据1位，多保留1位）
        'NO': 0,         # μg/m³，保留0位（同日数据）
        'NOx': 0,        # μg/m³，保留0位（同日数据）
    },
    # 旧标准统计数据（HJ 633-2013）- 与新标准不同
    # CO保留1位小数，其他污染物取整（同日数据）
    'statistical_data_old': {
        'PM2_5': 0,      # μg/m³，取整
        'PM10': 0,       # μg/m³，取整
        'SO2': 0,        # μg/m³，取整
        'NO2': 0,        # μg/m³，取整
        'O3_8h': 0,      # μg/m³，取整
        'CO': 1,         # mg/m³，保留1位
        'NO': 0,         # μg/m³，取整
        'NOx': 0,        # μg/m³，取整
    },
    # 达标评价数据 - "达标评价数据"列
    'evaluation_data': {
        'PM2_5': 0,      # μg/m³，保留0位
        'PM10': 0,       # μg/m³，保留0位
        'SO2': 0,        # μg/m³，保留0位
        'NO2': 0,        # μg/m³，保留0位
        'O3_8h': 0,      # μg/m³，保留0位
        'CO': 1,         # mg/m³，保留1位
        'O3': 0,         # μg/m³，保留0位
        'exceed_multiple': 2,  # 超标倍数，保留2位
        'compliance_rate': 1,  # 达标率（%），保留1位
    },
    # 最终输出修约规则（一般修约规范）
    'final_output': {
        'PM2_5': 1,      # μg/m³，保留1位小数
        'CO': 1,         # mg/m³，保留1位小数
        'SO2': 0,        # μg/m³，取整
        'NO2': 0,        # μg/m³，取整
        'PM10': 0,       # μg/m³，取整
        'O3_8h': 0,      # μg/m³，取整
    },
    # 其他指标（中间计算值）
    'other': {
        'composite_index': 2,      # 综合指数，保留2位
        'single_index': 3,         # 单项质量指数，保留3位
    }
}


def apply_rounding(value: Union[float, None], pollutant: str, data_type: str = 'statistical_data') -> float:
    """
    应用修约规则（四舍六入五成双）

    Args:
        value: 原始值
        pollutant: 污染物名称（如'PM2_5', 'SO2'等）
        data_type: 数据类型（'raw_data', 'statistical_data', 'evaluation_data'）

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    # 获取该污染物的修约精度
    precision = ROUNDING_PRECISION.get(data_type, {}).get(pollutant, 2)

    # 使用Python的round()函数（四舍六入五成双）
    return round(value, precision)


def format_pollutant_value(value: Union[float, None], pollutant: str, data_type: str = 'statistical_data'):
    """
    格式化污染物浓度值，确保按规范正确显示小数位数

    Args:
        value: 已修约的数值
        pollutant: 污染物名称
        data_type: 数据类型

    Returns:
        格式化后的值（整数、浮点数或字符串）
    """
    if value is None:
        return 0.0

    # 获取该污染物的修约精度
    precision = ROUNDING_PRECISION.get(data_type, {}).get(pollutant, 2)

    # PM2.5 特殊处理：强制显示一位小数（字符串格式）
    if pollutant == 'PM2_5' and data_type == 'statistical_data':
        return f"{value:.1f}"

    # 0位小数：返回整数
    if precision == 0:
        return int(value)
    # 1位或更多小数：返回浮点数
    else:
        return float(value)
