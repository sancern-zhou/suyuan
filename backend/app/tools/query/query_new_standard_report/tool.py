"""
新标准统计报表查询工具

基于 HJ 633-2024 新标准的空气质量统计报表查询工具

【核心功能】
- 新标准综合指数计算（PM2.5权重3，O3权重2，NO2权重2，其他权重1）
- 超标天数和达标率统计
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析

【新标准特点】
- PM2.5断点：IAQI=100时60μg/m³（旧标准75）
- PM10断点：IAQI=100时120μg/m³（旧标准150）
- 超标判断：基于单项质量指数 > 1
"""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import structlog
import os

# 尝试导入xlrd，如果失败则禁用扣沙功能
try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False
    logger = structlog.get_logger()
    logger.warning("xlrd_not_installed", message="xlrd包未安装，扣沙功能将被禁用")

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.utils.data_standardizer import DataStandardizer
from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool
from app.services.gd_suncere_api_client import get_gd_suncere_api_client

logger = structlog.get_logger()


# =============================================================================
# 扣沙数据处理函数
# =============================================================================

# 扣沙数据表格路径（优先使用CSV格式）
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SAND_DEDUCTION_FILE_CSV = os.path.join(_CURRENT_DIR, "扣沙数据.csv")
SAND_DEDUCTION_FILE_XLS = os.path.join(_CURRENT_DIR, "城市扣沙数据查询2015-12-01到2026-03-18.xls")

# 全局缓存：城市 -> 日期 -> 扣沙完整信息（包括首要污染物）
_sand_deduction_cache: Dict[str, Dict[str, Dict]] = {}


def load_sand_deduction_dates() -> Dict[str, Dict[str, Dict]]:
    """
    从扣沙表格中加载扣沙日期和完整信息

    支持两种格式：
    1. CSV格式（优先）：扣沙数据.csv
    2. Excel格式（备用）：城市扣沙数据查询2015-12-01到2026-03-18.xls

    Returns:
        城市名称 -> 日期 -> 扣沙完整信息（包括首要污染物）
        例如：{"广州": {"2023-03-13": {"primary_pollutant": "PM10", ...}, ...}, ...}
    """
    global _sand_deduction_cache

    # 如果已经加载，直接返回缓存
    if _sand_deduction_cache:
        return _sand_deduction_cache

    # 优先尝试CSV格式
    if os.path.exists(SAND_DEDUCTION_FILE_CSV):
        return _load_sand_deduction_dates_csv()

    # 备用：尝试Excel格式
    if os.path.exists(SAND_DEDUCTION_FILE_XLS):
        return _load_sand_deduction_dates_xls()

    # 都不存在
    logger.warning(
        "sand_deduction_file_not_found",
        csv_file=SAND_DEDUCTION_FILE_CSV,
        xls_file=SAND_DEDUCTION_FILE_XLS,
        message="扣沙数据表格不存在，将不进行扣沙处理"
    )
    return {}


def _load_sand_deduction_dates_csv() -> Dict[str, Dict[str, Dict]]:
    """从CSV文件加载扣沙日期和完整信息（包括首要污染物）"""
    global _sand_deduction_cache

    import csv

    sand_data = {}

    try:
        # CSV文件使用GBK编码
        with open(SAND_DEDUCTION_FILE_CSV, 'r', encoding='gbk') as f:
            reader = csv.DictReader(f)

            for row in reader:
                city = row.get('name', '').strip()
                date_str = row.get('timepoint', '').strip()
                pm10 = row.get('pm10', '').strip()
                pm25 = row.get('pm2_5', '').strip()
                primary_pollutant = row.get('primarypollutant', '').strip()

                # 检查是否为扣沙日（PM10或PM2.5为"—"）
                if pm10 == '—' or pm25 == '—':
                    try:
                        # 转换日期格式：2023/3/13 0:00 -> 2023-03-13
                        # 先移除时间部分
                        date_part = date_str.split()[0] if ' ' in date_str else date_str
                        # 解析日期
                        date_obj = datetime.strptime(date_part, '%Y/%m/%d')
                        standardized_date = date_obj.strftime('%Y-%m-%d')

                        # 初始化城市数据
                        if city not in sand_data:
                            sand_data[city] = {}

                        # 保存完整的扣沙信息（包括首要污染物）
                        # 处理首要污染物格式：O3_8H -> O3_8h
                        primary_normalized = primary_pollutant if primary_pollutant != '—' else None
                        if primary_normalized == 'O3_8H':
                            primary_normalized = 'O3_8h'

                        sand_data[city][standardized_date] = {
                            'primary_pollutant': primary_normalized,
                            'pm10': pm10,
                            'pm2_5': pm25,
                            'so2': row.get('so2', '').strip(),
                            'no2': row.get('no2', '').strip(),
                            'co': row.get('co', '').strip(),
                            'o3_8h': row.get('o3_8h', '').strip(),
                            'o3': row.get('o3', '').strip(),
                            'no': row.get('no', '').strip(),
                            'nox': row.get('nox', '').strip(),
                            'aqi': row.get('aqi', '').strip(),
                            'qualitytype': row.get('qualitytype', '').strip(),
                            'is_sand_day': True
                        }
                    except ValueError as e:
                        logger.warning(
                            "invalid_sand_deduction_date",
                            city=city,
                            date_str=date_str,
                            error=str(e)
                        )
                        continue

        _sand_deduction_cache = sand_data
        logger.info(
            "sand_deduction_dates_loaded_from_csv",
            cities_count=len(sand_data),
            total_dates=sum(len(dates) for dates in sand_data.values()),
            details={city: len(dates) for city, dates in sand_data.items()}
        )

        return sand_data

    except Exception as e:
        logger.error(
            "failed_to_load_sand_deduction_csv",
            file=SAND_DEDUCTION_FILE_CSV,
            error=str(e)
        )
        return {}


def _load_sand_deduction_dates_xls() -> Dict[str, Dict[str, Dict]]:
    """从Excel文件加载扣沙日期和完整信息（备用方案）"""
    global _sand_deduction_cache

    # 检查xlrd是否可用
    if not XLRD_AVAILABLE:
        logger.warning(
            "sand_deduction_disabled",
            message="xlrd包未安装，扣沙功能被禁用"
        )
        return {}

    try:
        # 读取Excel文件
        workbook = xlrd.open_workbook(SAND_DEDUCTION_FILE_XLS)
        sheet = workbook.sheet_by_index(0)

        # 解析扣沙日期和完整信息
        sand_data = {}
        for row_idx in range(1, sheet.nrows):
            row = sheet.row_values(row_idx)
            city = row[0]
            date_str = row[2]
            pm10 = row[5]
            pm25 = row[8]
            primary_pollutant = row[10] if len(row) > 10 else ''

            # 检查是否为扣沙日（PM10或PM2.5为"—"）
            if pm10 == '—' or pm25 == '—':
                # 转换日期格式：2025年04月13日 -> 2025-04-13
                try:
                    # 替换中文
                    date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
                    # 标准化格式
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    standardized_date = date_obj.strftime('%Y-%m-%d')

                    # 初始化城市数据
                    if city not in sand_data:
                        sand_data[city] = {}

                    # 保存完整的扣沙信息（包括首要污染物）
                    primary_normalized = primary_pollutant.strip() if primary_pollutant and primary_pollutant != '—' else None
                    if primary_normalized == 'O3_8H':
                        primary_normalized = 'O3_8h'

                    sand_data[city][standardized_date] = {
                        'primary_pollutant': primary_normalized,
                        'pm10': pm10,
                        'pm2_5': pm25,
                        'aqi': str(row[11] if len(row) > 11 else '').strip(),  # 保存AQI值（第12列）
                        'is_sand_day': True
                    }
                except ValueError as e:
                    logger.warning(
                        "invalid_sand_deduction_date",
                        city=city,
                        date_str=date_str,
                        error=str(e)
                    )
                    continue

        _sand_deduction_cache = sand_data
        logger.info(
            "sand_deduction_dates_loaded_from_xls",
            cities_count=len(sand_data),
            total_dates=sum(len(dates) for dates in sand_data.values()),
            details={city: len(dates) for city, dates in sand_data.items()}
        )

        return sand_data

    except Exception as e:
        logger.error(
            "failed_to_load_sand_deduction_xls",
            file=SAND_DEDUCTION_FILE_XLS,
            error=str(e)
        )
        return {}


def clean_sand_deduction_data(records: List[Dict], sand_dates: Dict[str, Dict[str, Dict]]) -> List[Dict]:
    """
    根据扣沙表格清洗数据（单一数据源原则）

    业务规则：
    - 扣沙日：完全使用扣沙表数据，不依赖API原始数据
    - 非扣沙日：使用API原始数据
    - 添加is_sand_deduction_day标记，前端可显示"已扣沙"

    单一数据源原则：
    - 扣沙日的所有字段（measurements、首要污染物、AQI等）全部从扣沙表读取
    - 避免API数据和扣沙表数据混合导致的数据覆盖问题

    Args:
        records: 原始日报数据列表
        sand_dates: 城市 -> 日期 -> 扣沙完整信息（包括首要污染物和AQI）

    Returns:
        清洗后的数据列表
    """
    if not sand_dates:
        return records

    cleaned_records = []

    for record in records:
        # 获取城市名称和日期
        city = (
            record.get("city") or
            record.get("city_name") or
            record.get("cityName") or
            record.get("name") or
            ""
        )

        # 从timePoint、timestamp或time_date中提取日期部分
        date_field = (
            record.get("timePoint") or      # API原始字段
            record.get("timestamp") or       # 标准化后字段
            record.get("time_date", "")      # 备用字段
        )

        if isinstance(date_field, str):
            date_part = date_field.split('T')[0].split()[0] if date_field else ""
        else:
            date_part = ""

        # 检查该日期是否为扣沙日
        is_sand_day = False
        sand_info = None
        if city and date_part and city in sand_dates:
            if date_part in sand_dates[city]:
                is_sand_day = True
                sand_info = sand_dates[city][date_part]

        if is_sand_day and sand_info:
            # ====================================================================
            # 扣沙日：完全使用扣沙表数据（单一数据源原则）
            # ====================================================================
            def sand_val(v):
                """扣沙表中'—'转为'-'，None转为None，其他保持原值"""
                if v is None:
                    return None
                return "-" if v in ('—', '') else v

            # 从API原始数据读取PM2.5/PM10原始值（用于统计计算）
            measurements = record.get("measurements", {})
            pm25_original = measurements.get("PM2_5") or measurements.get("pm2_5") or record.get("PM2_5") or record.get("pm2_5")
            pm10_original = measurements.get("PM10") or measurements.get("pm10") or record.get("PM10") or record.get("pm10")

            # 构造新的记录，完全从扣沙表读取数据
            cleaned_record = {
                # 保留元数据字段（从API原始数据）
                "city": city,
                "city_name": city,
                "name": city,
                "timestamp": date_part,
                "timePoint": date_field,
                "is_sand_deduction_day": True,

                # 污染物浓度（从扣沙表读取）
                "measurements": {
                    "SO2": sand_val(sand_info.get('so2')),
                    "NO2": sand_val(sand_info.get('no2')),
                    "PM10": sand_val(sand_info.get('pm10')),
                    "CO": sand_val(sand_info.get('co')),
                    "O3_8h": sand_val(sand_info.get('o3_8h')),
                    "O3": sand_val(sand_info.get('o3')),
                    "PM2_5": sand_val(sand_info.get('pm2_5')),
                    "NO": sand_val(sand_info.get('no')),
                    "NOx": sand_val(sand_info.get('nox')),
                },

                # AQI（从扣沙表读取）
                "AQI": int(float(sand_info.get('aqi', 0))) if sand_info.get('aqi') and sand_info.get('aqi') not in ('—', '', None) else 0,

                # 首要污染物（从扣沙表读取，None表示AQI ≤ 50）
                "primary_pollutant": sand_info.get('primary_pollutant'),

                # 空气质量等级（从扣沙表读取）
                "air_quality_level": sand_info.get('qualitytype') or sand_val(sand_info.get('qualitytype')),

                # 【关键】保存原始PM2.5/PM10值（从API原始数据读取，用于统计计算）
                "PM2_5_original": pm25_original,
                "PM10_original": pm10_original,
            }

            logger.info(
                "sand_deduction_applied",
                city=city,
                date=date_part,
                primary_pollutant=sand_info.get('primary_pollutant'),
                aqi=sand_info.get('aqi'),
                note="完全使用扣沙表数据（单一数据源原则）"
            )
        else:
            # ====================================================================
            # 非扣沙日：使用API原始数据
            # ====================================================================
            cleaned_record = record.copy()
            cleaned_record["is_sand_deduction_day"] = False

        cleaned_records.append(cleaned_record)

    return cleaned_records


# =============================================================================
# 常量定义
# =============================================================================

# 修约精度配置（GB/T 8170-2008 数值修约规则）
ROUNDING_PRECISION = {
    # 原始监测数据（小时或日数据）- "原始监测数据"列
    'raw_data': {
        'PM2_5': 1,      # μg/m³，保留1位
        'PM10': 1,       # μg/m³，保留1位
        'SO2': 1,        # μg/m³，保留1位
        'NO2': 1,        # μg/m³，保留1位
        'O3_8h': 1,      # μg/m³，保留1位
        'CO': 2,         # mg/m³，保留2位
        'NO': 1,         # μg/m³，保留1位
        'NOx': 1,        # μg/m³，保留1位
    },
    # 统计数据（月、季、年均值及特定百分位数）- "统计数据"列
    'statistical_data': {
        'PM2_5': 1,      # μg/m³，保留1位
        'PM10': 1,       # μg/m³，保留1位
        'SO2': 1,        # μg/m³，保留1位
        'NO2': 1,        # μg/m³，保留1位
        'O3_8h': 1,      # μg/m³，保留1位
        'CO': 2,         # mg/m³，保留2位
        'NO': 1,         # μg/m³，保留1位
        'NOx': 1,        # μg/m³，保留1位
    },
    # 达标评价数据 - "达标评价数据"列
    'evaluation_data': {
        'PM2_5': 1,      # μg/m³，保留1位
        'PM10': 1,       # μg/m³，保留1位
        'SO2': 1,        # μg/m³，保留1位
        'NO2': 1,        # μg/m³，保留1位
        'O3_8h': 1,      # μg/m³，保留1位
        'CO': 2,         # mg/m³，保留2位
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
        'composite_index': 3,      # 综合指数，保留3位
        'single_index': 3,         # 单项质量指数，保留3位（中间计算值）
    }
}

# 新标准（HJ 633-2024）24小时平均标准限值（单位：μg/m³，CO为mg/m³）
# 注意：新标准相比旧标准（HJ 633-2011）加严了PM2.5和PM10的限值
# - PM2.5: 新标准60 vs 旧标准75
# - PM10: 新标准120 vs 旧标准150
STANDARD_LIMITS = {
    'PM2_5': 60,   # 新标准24小时平均二级标准（HJ 633-2024，IAQI=100对应60）
    'PM10': 120,   # 新标准24小时平均二级标准（HJ 633-2024，IAQI=100对应120）
    'SO2': 150,    # 24小时平均二级标准
    'NO2': 80,     # 24小时平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

# 用于年均综合指数计算的标准限值
# 注意：PM10和PM2.5采用收严后的新标准限值
ANNUAL_STANDARD_LIMITS = {
    'PM2_5': 30,   # 年平均二级标准（新标准收严：35→30）
    'PM10': 60,    # 年平均二级标准（新标准收严：70→60）
    'SO2': 60,     # 年平均二级标准
    'NO2': 40,     # 年平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
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

# 新标准IAQI分段表（HJ 633-2024）
# IAQI 分段断点表：[浓度限值, IAQI值]
# 浓度单位：μg/m³（CO为mg/m³）
IAQI_BREAKPOINTS_NEW = {
    'SO2': [        # SO2 日平均
        (0, 0), (50, 50), (150, 100), (475, 150),
        (800, 200), (1600, 300), (2100, 400), (2620, 500)
    ],
    'NO2': [        # NO2 日平均
        (0, 0), (40, 50), (80, 100), (180, 150),
        (280, 200), (565, 300), (750, 400), (940, 500)
    ],
    'PM10': [       # PM10 日平均（新标准，收严）
        (0, 0), (50, 50), (120, 100), (250, 150),
        (350, 200), (420, 300), (500, 400), (600, 500)
    ],
    'CO': [         # CO 日平均（mg/m³）
        (0, 0), (2, 50), (4, 100), (14, 150),
        (24, 200), (36, 300), (48, 400), (60, 500)
    ],
    'O3_8h': [      # O3 日最大8小时平均
        (0, 0), (100, 50), (160, 100), (215, 150),
        (265, 200), (800, 300)  # 浓度 > 800 时，IAQI 固定为 300
    ],
    'PM2_5': [      # PM2.5 日平均（新标准 HJ 633，仅IAQI=100收严）
        (0, 0), (35, 50), (60, 100), (115, 150),
        (150, 200), (250, 300), (350, 400), (500, 500)
    ]
}


# =============================================================================
# 辅助函数
# =============================================================================

def safe_round(value: float, precision: int) -> float:
    """
    通用修约函数（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

    Args:
        value: 原始值
        precision: 保留的小数位数

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    from decimal import Decimal, ROUND_HALF_EVEN

    # 将浮点数转换为字符串再转换为Decimal，避免浮点数精度问题
    value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
    decimal_value = Decimal(value_str)

    # 构造修约单位（如0.01表示保留2位小数）
    quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')

    # 使用ROUND_HALF_EVEN进行修约
    rounded = decimal_value.quantize(quantize_unit, rounding=ROUND_HALF_EVEN)

    return float(rounded)


def apply_rounding(value: float, pollutant: str, data_type: str = 'statistical_data') -> float:
    """
    应用修约规则（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

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

    # 调用通用修约函数
    return safe_round(value, precision)


def format_pollutant_value(value: float, pollutant: str, data_type: str = 'statistical_data', use_final_rounding: bool = False):
    """
    格式化污染物浓度值，确保按修约规范正确显示小数位数

    用于返回结果中的数值格式化：
    - 默认（综合指数计算）：所有污染物（除CO外）保留1位小数，CO保留2位小数
    - 最终输出（use_final_rounding=True）：PM2.5和CO保留1位小数，其他四个指标取整

    Args:
        value: 已修约的数值
        pollutant: 污染物名称
        data_type: 数据类型
        use_final_rounding: 是否使用最终输出修约规则（一般修约规范）

    Returns:
        格式化后的值（整数或浮点数）
    """
    if value is None:
        return 0.0

    # 如果使用最终输出修约规则，重新应用修约
    if use_final_rounding:
        rounded_value = apply_rounding(value, pollutant, 'final_output')
        # 获取修约精度，决定返回类型
        precision = ROUNDING_PRECISION.get('final_output', {}).get(pollutant, 2)
        if precision == 0:
            return int(rounded_value)  # 返回整数类型
        return rounded_value

    # 返回浮点数（已修约的值）
    return float(value)


def calculate_iaqi(concentration: float, pollutant: str, standard: str = 'new') -> int:
    """
    计算污染物的空气质量分指数（IAQI）

    使用分段线性插值公式：
    IAQIP = (IAQIHi - IAQILo) / (BPHi - BPLo) × (CP - BPLo) + IAQILo

    特殊情况：
    - O3_8h 浓度 > 800 时，IAQI 固定为 300（最高值）

    Args:
        concentration: 污染物浓度值（μg/m³，CO为mg/m³）
        pollutant: 污染物名称（'SO2', 'NO2', 'PM10', 'CO', 'O3_8h', 'PM2_5'）
        standard: 标准类型，'new' 或 'old'，默认为 'new'

    Returns:
        IAQI值（整数）
    """
    # 确保concentration是数值类型（处理API返回的字符串类型）
    if concentration is None or concentration == '' or concentration == '-':
        return 0
    try:
        concentration = float(concentration)
    except (TypeError, ValueError):
        return 0

    if concentration <= 0:
        return 0

    # O3_8h 特殊处理：浓度 > 800 时，IAQI 固定为 300
    if pollutant == 'O3_8h' and concentration > 800:
        return 300

    # 选择对应的分段标准表
    breakpoints = IAQI_BREAKPOINTS_NEW.get(pollutant, [])
    if not breakpoints:
        return 0

    # 找到浓度所在的分段
    for i in range(len(breakpoints) - 1):
        bp_lo, iaqi_lo = breakpoints[i]
        bp_hi, iaqi_hi = breakpoints[i + 1]

        if bp_lo <= concentration <= bp_hi:
            # 使用分段线性插值公式计算IAQI
            if bp_hi == bp_lo:  # 防止除零
                return iaqi_hi
            iaqi = (iaqi_hi - iaqi_lo) / (bp_hi - bp_lo) * (concentration - bp_lo) + iaqi_lo
            import math
            return math.ceil(iaqi)

    # 浓度超过最高分段，返回最高IAQI
    return breakpoints[-1][1]


def calculate_date_segments(start_date: str, end_date: str) -> List[Tuple[str, str, int]]:
    """
    计算查询日期的智能分段

    规则：
    - 距离当天3天内（含3天）的数据使用原始数据（data_type=0）
    - 距离当天3天外的数据使用审核数据（data_type=1）
    - 如果查询周期跨越3天边界，分成两个时间段

    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        分段列表，每个元素为 (start_date, end_date, data_type)
    """
    segments = []
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)

    # 解析日期
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    # 计算查询开始和结束日期距离今天的天数
    start_days_from_today = (today - start).days
    end_days_from_today = (today - end).days

    logger.info(
        "calculate_date_segments",
        start_date=start_date,
        end_date=end_date,
        today=today.isoformat(),
        three_days_ago=three_days_ago.isoformat(),
        start_days_from_today=start_days_from_today,
        end_days_from_today=end_days_from_today
    )

    # 情况1: 查询范围全部在原始实况范围（今天及3天内）
    # 条件：查询开始日期距离今天 <= 3天
    if start_days_from_today <= 3:
        # 全部使用原始实况
        segments.append((start_date, end_date, 0))
        logger.info(
            "date_segments_all_recent",
            data_type=0,
            type="原始实况",
            reason=f"查询范围全部在原始实况范围内（{start_date}至{end_date}），全部使用原始实况"
        )

    # 情况2: 查询范围全部在审核实况范围（4天前及更早）
    # 条件：查询结束日期距离今天 >= 4天
    elif end_days_from_today >= 4:
        # 全部使用审核实况
        segments.append((start_date, end_date, 1))
        logger.info(
            "date_segments_all_historical",
            data_type=1,
            type="审核实况",
            reason=f"查询范围全部在审核实况范围内（{start_date}至{end_date}），全部使用审核实况"
        )

    # 情况3: 查询范围跨越3天边界，需要分段
    else:
        # 第一段：审核实况（start 到 three_days_ago - 1）
        segment1_end = three_days_ago - timedelta(days=1)
        segments.append((start_date, segment1_end.isoformat(), 1))

        # 第二段：原始实况（three_days_ago 到 end）
        segment2_start = three_days_ago
        segments.append((segment2_start.isoformat(), end_date, 0))

        logger.info(
            "date_segments_split",
            segment1=(start_date, segment1_end.isoformat(), 1),
            segment2=(segment2_start.isoformat(), end_date, 0),
            split_point=three_days_ago.isoformat(),
            reason=f"查询范围跨越3天边界({three_days_ago.isoformat()})，分段查询"
        )

    return segments


async def query_day_data_by_segment(
    api_client,
    city_codes: List[str],
    start_date: str,
    end_date: str,
    data_type: int
) -> List[Dict]:
    """
    按时间段查询日报数据

    Args:
        api_client: API客户端
        city_codes: 城市编码列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        data_type: 数据类型（0原始实况，1审核实况）

    Returns:
        日报数据列表
    """
    try:
        logger.info(
            "query_day_data_by_segment",
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            data_type_name="原始实况" if data_type == 0 else "审核实况"
        )

        response = await asyncio.to_thread(
            api_client.query_city_day_data,
            city_codes=city_codes,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type
        )

        if response.get("success"):
            raw_data = response.get("result", [])
            logger.info(
                "query_day_data_by_segment_success",
                record_count=len(raw_data),
                data_type=data_type
            )
            return raw_data
        else:
            error_msg = response.get('msg', 'Unknown error')
            logger.error(
                "query_day_data_by_segment_failed",
                error=error_msg,
                data_type=data_type
            )
            return []

    except Exception as e:
        logger.error(
            "query_day_data_by_segment_error",
            error=str(e),
            data_type=data_type
        )
        return []


# =============================================================================
# 核心执行函数
# =============================================================================

async def execute_query_new_standard_report(
    cities: List[str],
    start_date: str,
    end_date: str,
    enable_sand_deduction: bool = True,
    exclude_exceed_details: bool = False,
    context: Optional[ExecutionContext] = None
) -> Dict[str, Any]:
    """
    执行新标准统计报表查询

    Args:
        cities: 城市列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        enable_sand_deduction: 是否启用扣沙处理（默认True，剔除沙尘暴天气的PM2.5/PM10数据）
        exclude_exceed_details: 是否排除超标详情（默认False），为True时不返回exceed_details字段
        context: 执行上下文（可选）

    Returns:
        新标准统计报表结果（UDF v2.0格式）
    """
    # 初始化
    api_client = get_gd_suncere_api_client()
    data_standardizer = DataStandardizer() if context else None

    # 城市名称转换为城市编码（使用类方法）
    city_codes = []
    for city in cities:
        code = QueryGDSuncereDataTool.get_city_code(city)
        if code:
            city_codes.append(code)
        else:
            logger.warning("city_code_not_found", city=city)

    if not city_codes:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {
                "schema_version": "v2.0",
                "tool_name": "query_new_standard_report",
                "error": "No valid city codes found"
            },
            "summary": "未找到有效的城市编码"
        }

    logger.info(
        "query_new_standard_report_start",
        cities=cities,
        city_codes=city_codes,
        start_date=start_date,
        end_date=end_date,
        enable_sand_deduction=enable_sand_deduction
    )

    # 计算日期分段
    segments = calculate_date_segments(start_date, end_date)

    # 并发查询各时间段的日报数据
    all_daily_data = []
    query_tasks = []
    for seg_start, seg_end, data_type in segments:
        task = query_day_data_by_segment(
            api_client, city_codes, seg_start, seg_end, data_type
        )
        query_tasks.append(task)

    segment_results = await asyncio.gather(*query_tasks, return_exceptions=True)

    for i, result in enumerate(segment_results):
        if isinstance(result, Exception):
            logger.error(
                "segment_query_error",
                segment=segments[i],
                error=str(result)
            )
        else:
            all_daily_data.extend(result)

    logger.info(
        "daily_data_collected",
        total_records=len(all_daily_data),
        segments_count=len(segments)
    )

    if not all_daily_data:
        return {
            "status": "empty",
            "success": True,
            "data": {},
            "metadata": {
                "schema_version": "v2.0",
                "tool_name": "query_new_standard_report",
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "total_days": 0
            },
            "summary": f"未查询到 {', '.join(cities)} 在 {start_date} 至 {end_date} 期间的日报数据"
        }

    # 清洗扣沙日数据（在数据标准化之前）
    # 只有启用扣沙时才加载扣沙表格和清洗数据
    sand_dates = {}
    cleaned_data = all_daily_data

    if enable_sand_deduction:
        sand_dates = load_sand_deduction_dates()
        cleaned_data = clean_sand_deduction_data(all_daily_data, sand_dates)
        logger.info(
            "sand_deduction_data_cleaned",
            total_records=len(cleaned_data),
            cleaned_count=sum(1 for r in cleaned_data if r.get("PM2_5") is None or r.get("PM10") is None),
            sand_cities_count=len(sand_dates),
            note="扣沙处理已启用"
        )
    else:
        logger.info(
            "sand_deduction_skipped",
            total_records=len(all_daily_data),
            note="扣沙处理未启用，使用原始数据"
        )

    # 数据标准化（如果提供了context）
    standardized_data = cleaned_data
    if context and data_standardizer:
        standardized_data = []
        for record in cleaned_data:
            try:
                standardized = data_standardizer.standardize(record)
                standardized_data.append(standardized)
            except Exception as e:
                logger.warning("data_standardization_failed", record=record, error=str(e))
                standardized_data.append(record)

    # 按城市分组日报数据
    daily_data_by_city: Dict[str, List[Dict]] = {}
    for record in standardized_data:
        # 尝试多种城市字段名
        # 注意：API返回的数据使用 'name' 字段存储城市名称
        city_name = (
            record.get("city") or
            record.get("city_name") or
            record.get("cityName") or
            record.get("name") or
            ""
        )
        if city_name:
            if city_name not in daily_data_by_city:
                daily_data_by_city[city_name] = []
            daily_data_by_city[city_name].append(record)

    logger.info(
        "daily_data_grouped_by_city",
        cities_count=len(daily_data_by_city),
        city_names=list(daily_data_by_city.keys())
    )

    # 【关键容错】如果分组后没有找到城市数据，且只查询一个城市，将所有记录归类到查询城市名下
    # 这处理API不返回city字段的极端情况
    if not daily_data_by_city and len(cities) == 1:
        logger.info(
            "no_city_field_in_data",
            message="数据中没有城市字段，使用查询参数中的城市名称",
            query_city=cities[0],
            record_count=len(standardized_data)
        )
        daily_data_by_city[cities[0]] = standardized_data

    # 计算各城市的新标准统计指标
    city_stats = {}

    for city, daily_records in daily_data_by_city.items():
        if not daily_records:
            continue

        logger.info("calculating_new_standard", city=city, day_count=len(daily_records))

        # 初始化统计变量
        total_days = len(daily_records)
        exceed_days = 0
        exceed_details = []
        pm25_sum = 0
        pm10_sum = 0
        pm25_valid_count = 0  # PM2.5有效天数（剔除扣沙日）
        pm10_valid_count = 0  # PM10有效天数（剔除扣沙日）
        so2_sum = 0
        no2_sum = 0
        co_sum = 0
        o3_8h_sum = 0

        # 有效天数统计（所有六项污染物都有数据的天数）
        valid_days = 0  # 所有六项都有数据的天数

        # 收集每日浓度值用于计算百分位数
        daily_co_values = []
        daily_o3_8h_values = []
        daily_so2_values = []
        daily_no2_values = []
        daily_pm10_values = []
        daily_pm25_values = []

        # 首要污染物统计
        primary_pollutant_days = {
            'PM2_5': 0,
            'PM10': 0,
            'SO2': 0,
            'NO2': 0,
            'CO': 0,
            'O3_8h': 0
        }

        # 【新增】记录每个污染物的首要污染物日期列表
        primary_pollutant_dates = {
            'PM2_5': [],
            'PM10': [],
            'SO2': [],
            'NO2': [],
            'CO': [],
            'O3_8h': []
        }

        # 各污染物超标天数统计
        exceed_days_by_pollutant = {
            'PM2_5': 0,
            'PM10': 0,
            'SO2': 0,
            'NO2': 0,
            'CO': 0,
            'O3_8h': 0
        }

        # 首要污染物超标天统计（某污染物既是首要污染物又超标）
        primary_pollutant_exceed_days = {
            'PM2_5': 0,
            'PM10': 0,
            'SO2': 0,
            'NO2': 0,
            'CO': 0,
            'O3_8h': 0
        }

        for record in daily_records:
            # 提取浓度值
            measurements = record.get("measurements", {})

            def safe_float(value, default=0.0):
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            # 检查是否为扣沙日
            is_sand_day = record.get("is_sand_deduction_day", False)

            # 优先从 measurements 中提取，其次从顶层字段提取
            if is_sand_day:
                # 扣沙日：PM2.5/PM10为"-"，使用原始值计算统计指标
                pm25_raw = safe_float(record.get("PM2_5_original"))
                pm10_raw = safe_float(record.get("PM10_original"))
            else:
                pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5") or
                        record.get("pm2_5") or record.get("PM2_5"))
                pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10") or
                        record.get("pm10") or record.get("PM10"))

            so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2") or
                   record.get("so2") or record.get("SO2"))
            no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2") or
                   record.get("no2") or record.get("NO2"))
            co_raw = safe_float(measurements.get("CO") or measurements.get("co") or
                  record.get("co") or record.get("CO"))
            o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h") or
                    record.get("o3_8h") or record.get("O3_8h"))

            # 按原始监测数据规则修约日数据
            # 这些值用于计算均值、分指数、综合指数（扣沙日PM2.5/PM10使用原始值但不参与均值）
            pm25 = apply_rounding(pm25_raw, 'PM2_5', 'raw_data')
            pm10 = apply_rounding(pm10_raw, 'PM10', 'raw_data')
            so2 = apply_rounding(so2_raw, 'SO2', 'raw_data')
            no2 = apply_rounding(no2_raw, 'NO2', 'raw_data')
            co = apply_rounding(co_raw, 'CO', 'raw_data')
            o3_8h = apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data')

            # 累加修约后的浓度值
            if pm25 > 0:
                pm25_sum += pm25
                pm25_valid_count += 1

            if pm10 > 0:
                pm10_sum += pm10
                pm10_valid_count += 1

            # 其他污染物正常累加
            so2_sum += so2
            no2_sum += no2
            co_sum += co
            o3_8h_sum += o3_8h

            # 统计有效天数（只要有一项污染物有数据就算有效天）
            if pm25 > 0 or pm10 > 0 or so2 > 0 or no2 > 0 or co > 0 or o3_8h > 0:
                valid_days += 1

            # 收集修约后的每日值（用于百分位数计算）
            if co > 0:
                daily_co_values.append(co)
            if o3_8h > 0:
                daily_o3_8h_values.append(o3_8h)
            if so2 > 0:
                daily_so2_values.append(so2)
            if no2 > 0:
                daily_no2_values.append(no2)
            if pm10 > 0:
                daily_pm10_values.append(pm10)
            if pm25 > 0:
                daily_pm25_values.append(pm25)

            # 计算该日各污染物的单项质量指数 Ii = Ci / Si
            # 业务规则：扣沙日的PM2.5/PM10分指数使用扣沙后值（为0），用于综合指数计算
            pm25_index_new = pm25 / STANDARD_LIMITS['PM2_5']
            pm10_index_new = pm10 / STANDARD_LIMITS['PM10']
            so2_index_new = so2 / STANDARD_LIMITS['SO2']
            no2_index_new = no2 / STANDARD_LIMITS['NO2']
            co_index_new = co / STANDARD_LIMITS['CO']
            o3_8h_index_new = o3_8h / STANDARD_LIMITS['O3_8h']

            # 判断该日是否超标
            max_single_index_new = max(pm25_index_new, pm10_index_new, so2_index_new,
                                       no2_index_new, co_index_new, o3_8h_index_new)

            # 计算各污染物的 IAQI（calculate_iaqi 内部已使用 ceil 向上取整）
            # 扣沙日的PM2.5/PM10 IAQI设为0，不参与AQI计算
            pm25_iaqi_new = 0 if is_sand_day else calculate_iaqi(pm25, 'PM2_5', 'new')
            pm10_iaqi_new = 0 if is_sand_day else calculate_iaqi(pm10, 'PM10', 'new')
            so2_iaqi_new = calculate_iaqi(so2, 'SO2', 'new')
            no2_iaqi_new = calculate_iaqi(no2, 'NO2', 'new')
            co_iaqi_new = calculate_iaqi(co, 'CO', 'new')
            o3_8h_iaqi_new = calculate_iaqi(o3_8h, 'O3_8h', 'new')

            # 统计首要污染物（使用向上取整后的IAQI）
            pollutants_with_iaqi_new = {
                'PM2_5': pm25_iaqi_new,
                'PM10': pm10_iaqi_new,
                'SO2': so2_iaqi_new,
                'NO2': no2_iaqi_new,
                'CO': co_iaqi_new,
                'O3_8h': o3_8h_iaqi_new
            }
            # 扣沙日：AQI不重算，使用扣沙表中的值；非扣沙日：正常计算
            if is_sand_day:
                aqi_new = record.get("AQI", 0)
            else:
                aqi_new = math.ceil(max(pollutants_with_iaqi_new.values()))

            # 【调试日志】输出每天的详细计算结果
            timestamp = record.get("timestamp", "unknown")
            date_only = timestamp[:10] if len(timestamp) >= 10 else timestamp

            # 只输出关键日期的详细日志
            if date_only in ['2026-01-17', '2026-01-20', '2026-01-01', '2026-01-24']:
                logger.info(
                    "daily_calculation_debug",
                    date=date_only,
                    concentrations={
                        'PM2_5': f"{pm25_for_aqi:.1f}",
                        'PM10': f"{pm10_for_aqi:.1f}",
                        'SO2': f"{so2:.1f}",
                        'NO2': f"{no2:.1f}",
                        'CO': f"{co:.1f}",
                        'O3_8h': f"{o3_8h:.1f}"
                    },
                    iaqi_new={
                        'PM2_5': f"{pm25_iaqi_new:.1f}",
                        'PM10': f"{pm10_iaqi_new:.1f}",
                        'SO2': f"{so2_iaqi_new:.1f}",
                        'NO2': f"{no2_iaqi_new:.1f}",
                        'CO': f"{co_iaqi_new:.1f}",
                        'O3_8h': f"{o3_8h_iaqi_new:.1f}"
                    },
                    index_new={
                        'PM2_5': f"{pm25_index_new:.3f}",
                        'PM10': f"{pm10_index_new:.3f}",
                        'SO2': f"{so2_index_new:.3f}",
                        'NO2': f"{no2_index_new:.3f}",
                        'CO': f"{co_index_new:.3f}",
                        'O3_8h': f"{o3_8h_index_new:.3f}"
                    },
                    aqi_new=f"{aqi_new:.1f}",
                    max_single_index_new=f"{max_single_index_new:.3f}",
                    is_sand_day=is_sand_day
                )

            # 业务规则：扣沙日的AQI和首要污染物使用扣沙表中的值
            if is_sand_day:
                # 扣沙日：直接使用扣沙表中的首要污染物
                primary_from_sand = record.get("primary_pollutant")

                # 修复1：支持中文逗号和英文逗号分割（数据中可能使用 "O3_8h，NO2"）
                # 修复2：使用大小写不敏感的统计，避免因 O3_8h vs O3_8H 导致的统计遗漏
                # 修复3：处理 PM2.5（点号）到 PM2_5（下划线）的映射
                if primary_from_sand:
                    import re
                    # 同时支持中文逗号（，）和英文逗号（,）分割
                    sand_pollutants = re.split(r'[，,]', primary_from_sand)
                    primary_pollutants_this_day = [p.strip() for p in sand_pollutants if p.strip()]
                    # 统计每个首要污染物
                    for p in primary_pollutants_this_day:
                        # 标准化污染物名称（处理大小写和点号/下划线差异）
                        dict_key = p

                        # 处理 PM2.5 → PM2_5 映射
                        if p == 'PM2.5':
                            dict_key = 'PM2_5'
                        # 处理 O3_8h 大小写
                        elif p.upper() == 'O3_8H':
                            dict_key = 'O3_8h'

                        if dict_key in primary_pollutant_days:
                            primary_pollutant_days[dict_key] += 1
                            # 【新增】记录首要污染物日期
                            primary_pollutant_dates[dict_key].append(date_only)
                            # 【调试】韶关所有首要污染物追踪
                            if city_name == '韶关':
                                logger.info(
                                    "sand_day_primary_pollutant_counted",
                                    city=city_name,
                                    date=date_only,
                                    primary_from_sand=primary_from_sand,
                                    normalized_pollutant=dict_key,
                                    all_candidates=primary_pollutants_this_day
                                )
                else:
                    primary_pollutants_this_day = []
            else:
                # 非扣沙日：重新计算首要污染物
                primary_pollutants_this_day = []
                if aqi_new > 50:
                    for pollutant, iaqi in pollutants_with_iaqi_new.items():
                        if iaqi == aqi_new:
                            primary_pollutant_days[pollutant] += 1
                            # 【新增】记录首要污染物日期
                            primary_pollutant_dates[pollutant].append(date_only)
                            primary_pollutants_this_day.append(pollutant)
                            # 【调试】韶关所有首要污染物追踪
                            if city_name == '韶关':
                                logger.info(
                                    "non_sand_day_primary_pollutant_counted",
                                    city=city_name,
                                    date=date_only,
                                    pollutant=pollutant,
                                    aqi_new=f"{aqi_new:.1f}",
                                    pm25_iaqi=f"{pm25_iaqi_new:.1f}",
                                    pm10_iaqi=f"{pm10_iaqi_new:.1f}",
                                    o3_8h_iaqi=f"{o3_8h_iaqi_new:.1f}",
                                    no2_iaqi=f"{no2_iaqi_new:.1f}",
                                    so2_iaqi=f"{so2_iaqi_new:.1f}",
                                    co_iaqi=f"{co_iaqi_new:.1f}"
                                )

            # ====================================================================
            # 将新标准计算结果写入record（保存到 data-id）
            # 扣沙日：AQI和首要污染物已由 clean_sand_deduction_data 设置，不覆盖
            # ====================================================================
            record["IAQI_PM2_5"] = pm25_iaqi_new
            record["IAQI_PM10"] = pm10_iaqi_new
            record["IAQI_SO2"] = so2_iaqi_new
            record["IAQI_NO2"] = no2_iaqi_new
            record["IAQI_CO"] = co_iaqi_new
            record["IAQI_O3_8h"] = o3_8h_iaqi_new
            if not is_sand_day:
                record["AQI"] = aqi_new
                if primary_pollutants_this_day:
                    record["primary_pollutant"] = ",".join(primary_pollutants_this_day)
                else:
                    record["primary_pollutant"] = None

            # 单项质量指数（原始API没有此字段，保留 _new 后缀以区分）
            record["single_index_PM2_5_new"] = safe_round(pm25_index_new, 3)
            record["single_index_PM10_new"] = safe_round(pm10_index_new, 3)
            record["single_index_SO2_new"] = safe_round(so2_index_new, 3)
            record["single_index_NO2_new"] = safe_round(no2_index_new, 3)
            record["single_index_CO_new"] = safe_round(co_index_new, 3)
            record["single_index_O3_8h_new"] = safe_round(o3_8h_index_new, 3)

            # 【调试日志】输出首要污染物判断结果
            # 针对韶关的PM2.5首要污染物进行详细追踪
            city_name = record.get("city_name", "")
            if city_name == '韶关':
                logger.info(
                    "primary_pollutant_debug",
                    city=city_name,
                    date=date_only,
                    aqi_new=f"{aqi_new:.1f}",
                    aqi_gt_50=aqi_new > 50,
                    primary_pollutants=primary_pollutants_this_day,
                    is_sand_day=is_sand_day,
                    primary_from_sand=record.get("primary_pollutant") if is_sand_day else None,
                    pm25_iaqi=f"{pm25_iaqi_new:.1f}",
                    pm10_iaqi=f"{pm10_iaqi_new:.1f}",
                    o3_8h_iaqi=f"{o3_8h_iaqi_new:.1f}",
                    no2_iaqi=f"{no2_iaqi_new:.1f}",
                    so2_iaqi=f"{so2_iaqi_new:.1f}",
                    co_iaqi=f"{co_iaqi_new:.1f}",
                    max_single_index=f"{max_single_index_new:.3f}",
                    is_exceeded=max_single_index_new > 1
                )

            # 统计各污染物超标天数（单项质量指数 > 1）
            # 业务规则：扣沙日的PM2.5/PM10分指数为0，不计入超标天数
            if pm25_index_new > 1:
                exceed_days_by_pollutant['PM2_5'] += 1
            if pm10_index_new > 1:
                exceed_days_by_pollutant['PM10'] += 1
            if so2_index_new > 1:
                exceed_days_by_pollutant['SO2'] += 1
            if no2_index_new > 1:
                exceed_days_by_pollutant['NO2'] += 1
            if co_index_new > 1:
                exceed_days_by_pollutant['CO'] += 1
            if o3_8h_index_new > 1:
                exceed_days_by_pollutant['O3_8h'] += 1

            # 新标准超标天数统计
            if max_single_index_new > 1:
                exceed_days += 1

                # 统计首要污染物超标天（某污染物既是首要污染物又超标）
                # 修复：需要检查首要污染物本身是否超标，而不是只检查当天是否有任何污染物超标
                primary_pollutant_indexes = {
                    'PM2_5': pm25_index_new,
                    'PM10': pm10_index_new,
                    'SO2': so2_index_new,
                    'NO2': no2_index_new,
                    'CO': co_index_new,
                    'O3_8h': o3_8h_index_new
                }

                for primary_pollutant in primary_pollutants_this_day:
                    # 修复：使用大小写不敏感的统计，避免因 O3_8h vs O3_8H 导致的统计遗漏
                    # 修复：处理 PM2.5（点号）到 PM2_5（下划线）的映射
                    dict_key = primary_pollutant

                    # 处理 PM2.5 → PM2_5 映射
                    if primary_pollutant == 'PM2.5':
                        dict_key = 'PM2_5'
                    # 处理 O3_8h 大小写
                    elif primary_pollutant.upper() == 'O3_8H':
                        dict_key = 'O3_8h'

                    if dict_key in primary_pollutant_exceed_days:
                        # 只有当首要污染物本身超标时才计入
                        if primary_pollutant_indexes.get(dict_key, 0) > 1:
                            primary_pollutant_exceed_days[dict_key] += 1

                # 记录超标详情
                exceed_pollutants = []
                pollutants = {
                    'PM2_5': (pm25, pm25_index_new),
                    'PM10': (pm10, pm10_index_new),
                    'SO2': (so2, so2_index_new),
                    'NO2': (no2, no2_index_new),
                    'CO': (co, co_index_new),
                    'O3_8h': (o3_8h, o3_8h_index_new)
                }
                for name, (conc, index) in pollutants.items():
                    if index > 1:
                        exceed_pollutants.append({
                            'name': name,
                            'concentration': conc,
                            'index': safe_round(index, 3)
                        })

                exceed_detail = {
                    'date': record.get("timestamp", "unknown"),
                    'max_index': safe_round(max_single_index_new, 3),
                    'exceed_pollutants': exceed_pollutants
                }
                exceed_details.append(exceed_detail)

                # 【调试日志】输出超标详情
                date_only = record.get("timestamp", "unknown")[:10] if len(record.get("timestamp", "")) >= 10 else record.get("timestamp", "unknown")
                if date_only in ['2026-01-17', '2026-01-20', '2026-01-01', '2026-01-24']:
                    logger.info(
                        "exceed_detail_debug",
                        date=date_only,
                        max_index=f"{max_single_index_new:.3f}",
                        exceed_pollutants_count=len(exceed_pollutants),
                        exceed_pollutants=exceed_pollutants,
                        primary_pollutants_this_day=primary_pollutants_this_day,
                        note="超标天记录"
                    )

        # 计算平均浓度（按国家标准修约）
        # PM2.5和PM10: 使用有效天数计算平均值（剔除扣沙日）
        avg_pm25 = apply_rounding(
            pm25_sum / pm25_valid_count if pm25_valid_count > 0 else 0,
            'PM2_5', 'statistical_data'
        )
        avg_pm10 = apply_rounding(
            pm10_sum / pm10_valid_count if pm10_valid_count > 0 else 0,
            'PM10', 'statistical_data'
        )

        # 其他污染物: 使用总天数计算平均值（保持不变）
        avg_so2 = apply_rounding(so2_sum / total_days, 'SO2', 'statistical_data') if total_days > 0 else 0
        avg_no2 = apply_rounding(no2_sum / total_days, 'NO2', 'statistical_data') if total_days > 0 else 0
        avg_co = apply_rounding(co_sum / total_days, 'CO', 'statistical_data') if total_days > 0 else 0
        avg_o3_8h = apply_rounding(o3_8h_sum / total_days, 'O3_8h', 'statistical_data') if total_days > 0 else 0

        # 计算百分位数
        def calculate_percentile(values, percentile):
            """计算百分位数"""
            if not values:
                return 0.0
            sorted_values = sorted(values)
            n = len(sorted_values)
            index = (percentile / 100) * (n - 1)
            lower = int(index)
            upper = lower + 1
            if upper >= n:
                return float(sorted_values[-1])
            weight = index - lower
            return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

        # 计算百分位数（按国家标准修约）
        co_percentile_95 = apply_rounding(calculate_percentile(daily_co_values, 95), 'CO', 'statistical_data')
        o3_8h_percentile_90 = apply_rounding(calculate_percentile(daily_o3_8h_values, 90), 'O3_8h', 'statistical_data')
        so2_percentile_98 = apply_rounding(calculate_percentile(daily_so2_values, 98), 'SO2', 'statistical_data')
        no2_percentile_98 = apply_rounding(calculate_percentile(daily_no2_values, 98), 'NO2', 'statistical_data')
        pm10_percentile_95 = apply_rounding(calculate_percentile(daily_pm10_values, 95), 'PM10', 'statistical_data')
        pm25_percentile_95 = apply_rounding(calculate_percentile(daily_pm25_values, 95), 'PM2_5', 'statistical_data')

        # 计算新标准综合指数
        new_standard_concentrations = {
            'PM2_5': avg_pm25,
            'PM10': avg_pm10,
            'SO2': avg_so2,
            'NO2': avg_no2,
            'CO': co_percentile_95,
            'O3_8h': o3_8h_percentile_90
        }

        # 计算新标准单项质量指数 Ii = Ci / Si
        pm25_index = safe_round(new_standard_concentrations['PM2_5'] / ANNUAL_STANDARD_LIMITS['PM2_5'], 3)
        pm10_index = safe_round(new_standard_concentrations['PM10'] / ANNUAL_STANDARD_LIMITS['PM10'], 3)
        so2_index = safe_round(new_standard_concentrations['SO2'] / ANNUAL_STANDARD_LIMITS['SO2'], 3)
        no2_index = safe_round(new_standard_concentrations['NO2'] / ANNUAL_STANDARD_LIMITS['NO2'], 3)
        co_index = safe_round(new_standard_concentrations['CO'] / ANNUAL_STANDARD_LIMITS['CO'], 3)
        o3_8h_index = safe_round(new_standard_concentrations['O3_8h'] / ANNUAL_STANDARD_LIMITS['O3_8h'], 3)

        # 计算加权单项质量指数
        pm25_weighted_index = safe_round(pm25_index * WEIGHTS['PM2_5'], 3)
        pm10_weighted_index = safe_round(pm10_index * WEIGHTS['PM10'], 3)
        so2_weighted_index = safe_round(so2_index * WEIGHTS['SO2'], 3)
        no2_weighted_index = safe_round(no2_index * WEIGHTS['NO2'], 3)
        co_weighted_index = safe_round(co_index * WEIGHTS['CO'], 3)
        o3_8h_weighted_index = safe_round(o3_8h_index * WEIGHTS['O3_8h'], 3)

        # 计算综合指数
        avg_composite_index = safe_round(
            pm25_weighted_index + pm10_weighted_index + so2_weighted_index +
            no2_weighted_index + co_weighted_index + o3_8h_weighted_index, 3
        )

        # 计算达标率和超标率
        # 达标率和超标率使用有效天数作为分母（所有六项污染物都有数据的天数）
        compliance_rate = safe_round((valid_days - exceed_days) / valid_days * 100, 1) if valid_days > 0 else 0
        exceed_rate = safe_round(exceed_days / valid_days * 100, 1) if valid_days > 0 else 0

        # 计算首要污染物比例
        total_primary_days = sum(primary_pollutant_days.values())
        primary_pollutant_ratio = {}
        if total_primary_days > 0:
            for pollutant, days in primary_pollutant_days.items():
                primary_pollutant_ratio[pollutant] = safe_round(days / total_primary_days * 100, 1)
        else:
            for pollutant in primary_pollutant_days.keys():
                primary_pollutant_ratio[pollutant] = 0.0

        # 计算各污染物超标率
        exceed_rate_by_pollutant = {}
        for pollutant, days in exceed_days_by_pollutant.items():
            if valid_days > 0:
                exceed_rate_by_pollutant[pollutant] = safe_round(days / valid_days * 100, 1)
            else:
                exceed_rate_by_pollutant[pollutant] = 0.0

        # 构建城市统计结果
        city_stats[city] = {
            "composite_index": avg_composite_index,
            "exceed_days": int(exceed_days),
            "valid_days": int(valid_days),
            "exceed_rate": exceed_rate,
            "compliance_rate": compliance_rate,
            "total_days": int(total_days),
            # 六参数统计指标（应用最终输出修约规则：PM2.5和CO保留1位小数，其他取整）
            "SO2": format_pollutant_value(avg_so2, 'SO2', 'statistical_data', use_final_rounding=True),
            "SO2_P98": format_pollutant_value(so2_percentile_98, 'SO2', 'statistical_data', use_final_rounding=True),
            "NO2": format_pollutant_value(avg_no2, 'NO2', 'statistical_data', use_final_rounding=True),
            "NO2_P98": format_pollutant_value(no2_percentile_98, 'NO2', 'statistical_data', use_final_rounding=True),
            "PM10": format_pollutant_value(avg_pm10, 'PM10', 'statistical_data', use_final_rounding=True),
            "PM10_P95": format_pollutant_value(pm10_percentile_95, 'PM10', 'statistical_data', use_final_rounding=True),
            "PM2_5": format_pollutant_value(avg_pm25, 'PM2_5', 'statistical_data', use_final_rounding=True),
            "PM2_5_P95": format_pollutant_value(pm25_percentile_95, 'PM2_5', 'statistical_data', use_final_rounding=True),
            # CO和O3只展示百分位数
            "CO_P95": format_pollutant_value(co_percentile_95, 'CO', 'statistical_data', use_final_rounding=True),
            "O3_8h_P90": format_pollutant_value(o3_8h_percentile_90, 'O3_8h', 'statistical_data', use_final_rounding=True),
            # 加权单项质量指数
            "single_indexes": {
                "SO2": so2_weighted_index,
                "NO2": no2_weighted_index,
                "PM10": pm10_weighted_index,
                "CO": co_weighted_index,
                "PM2_5": pm25_weighted_index,
                "O3_8h": o3_8h_weighted_index
            },
            # 首要污染物统计
            "primary_pollutant_days": {k: int(v) for k, v in primary_pollutant_days.items()},
            "primary_pollutant_ratio": primary_pollutant_ratio,
            "total_primary_days": int(total_primary_days),
            "PM2_5_primary_dates": sorted(primary_pollutant_dates.get('PM2_5', [])),
            # 各污染物超标统计
            "exceed_days_by_pollutant": {k: int(v) for k, v in exceed_days_by_pollutant.items()},
            "exceed_rate_by_pollutant": exceed_rate_by_pollutant,
            # 首要污染物超标天统计（某污染物既是首要污染物又超标）
            "primary_pollutant_exceed_days": {k: int(v) for k, v in primary_pollutant_exceed_days.items()}
        }

        # 可选：添加超标详情（如果未排除）
        if not exclude_exceed_details:
            city_stats[city]["exceed_details"] = exceed_details

        logger.info(
            "city_new_standard_calculated",
            city=city,
            composite_index=avg_composite_index,
            exceed_days=exceed_days,
            compliance_rate=compliance_rate,
            sand_deduction_stats={
                "total_days": total_days,
                "pm25_valid_count": pm25_valid_count,
                "pm10_valid_count": pm10_valid_count,
                "pm25_sand_days": total_days - pm25_valid_count,
                "pm10_sand_days": total_days - pm10_valid_count
            },
            primary_pollutant_days=primary_pollutant_days,
            primary_pollutant_ratio=primary_pollutant_ratio,
            total_primary_days=total_primary_days,
            exceed_days_by_pollutant=exceed_days_by_pollutant,
            exceed_rate_by_pollutant=exceed_rate_by_pollutant,
            exceed_details_count=len(exceed_details)
        )

        # 【调试日志】输出首要污染物的详细对比
        if city == "广州":
            logger.info(
                "primary_pollutant_analysis_summary",
                city=city,
                    note="首要污染物统计基于 AQI>50 的天数",
                    pm25_primary_days=primary_pollutant_days.get('PM2_5', 0),
                    pm10_primary_days=primary_pollutant_days.get('PM10', 0),
                    no2_primary_days=primary_pollutant_days.get('NO2', 0),
                    o3_8h_primary_days=primary_pollutant_days.get('O3_8h', 0),
                    exceed_details_pm25_as_primary=sum(
                        1 for detail in exceed_details
                        if detail.get('exceed_pollutants') and
                        any(p.get('name') == 'PM2_5' and
                            p.get('index', 0) == max(
                                (ep.get('index', 0) for ep in detail.get('exceed_pollutants', [])),
                                default=0
                            )
                            for p in detail.get('exceed_pollutants', []))
                    ),
                    note2="exceed_details 中 PM2.5 作为最大 index 污染物的天数"
            )

    # 可选：保存完整日报数据到数据注册表
    # ⚠️ 已禁用：统计报表工具不返回 data_id，避免 LLM 尝试从 data_id 读取统计字段
    # data_id_str = None
    # if context:
    #     try:
    #         # context.save_data() 直接返回字符串ID
    #         data_id_str = context.save_data(
    #             data=standardized_data,  # 保存清洗和标准化后的数据
    #             schema="air_quality_unified"
    #         )
    #         logger.info("daily_data_saved", data_id=data_id_str)
    #     except Exception as e:
    #         logger.warning("failed_to_save_daily_data", error=str(e))
    data_id_str = None  # 统计报表工具不返回 data_id

    # 计算全省汇总统计（多城市查询时）
    province_wide_stats = None
    if len(cities) > 1 and city_stats:
        province_wide_stats = calculate_province_wide_stats(city_stats)

    # 构建返回结果
    # 统计结果放在 result 字段，与 query_standard_comparison 保持一致
    # 原始日数据通过 data_id 引用
    if len(cities) == 1 and city_stats:
        city_name = list(city_stats.keys())[0]
        result_summary_data = city_stats[city_name]
        result_summary = f"新标准统计报表查询完成，{city_name} {start_date} 至 {end_date}（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
    else:
        result_summary_data = city_stats
        result_summary = f"新标准统计报表查询完成，共{len(city_stats)}个城市（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
        # 添加全省汇总到结果
        if province_wide_stats:
            result_summary_data["province_wide"] = province_wide_stats

    # 添加数据存储信息到摘要
    # if data_id_str:
    #     result_summary += f" | 原始日数据已保存至 data_id: {data_id_str}，统计汇总指标已完整展示在 result 字段中"

    # 构建元数据
    metadata = {
        "schema_version": "v2.0",
        "tool_name": "query_new_standard_report",
        "cities": cities,
        "date_range": f"{start_date} to {end_date}",
        "total_days": sum(s.get("total_days", 0) for s in city_stats.values()) if city_stats else 0,
        "sand_deduction_applied": enable_sand_deduction and bool(sand_dates),  # 是否应用了扣沙处理
        "sand_deduction_info": {
            "enabled": enable_sand_deduction,
            "loaded": bool(sand_dates),
            "cities_with_sand_days": list(sand_dates.keys()) if sand_dates else [],
            "total_sand_days": sum(len(dates) for dates in sand_dates.values()) if sand_dates else 0
        }
    }

    # 添加 data_id 到元数据
    if data_id_str:
        metadata["data_id"] = data_id_str

    # 构建返回结果（UDF v2.0格式）
    # 统计结果在 result 字段，data 字段为 None（不返回详细记录）
    result = {
        "status": "success",
        "success": True,
        "data": None,  # 统计工具不返回详细记录
        "metadata": metadata,
        "summary": result_summary,
        "result": result_summary_data  # 统计分析结果
    }

    return result


def calculate_province_wide_stats(city_stats: Dict[str, Dict]) -> Dict[str, Any]:
    """
    计算全省汇总统计指标

    汇总规则：
    - **均值类指标**（各城市均值）：composite_index, single_indexes.*, SO2, NO2, PM10, PM2_5, CO_P95, O3_8h_P90等
    - **累加类指标**（各城市累加）：exceed_days, valid_days, exceed_days_by_pollutant.*, primary_pollutant_days.*, total_primary_days
    - **计算类指标**：exceed_rate, compliance_rate, exceed_rate_by_pollutant.*, primary_pollutant_ratio
    - **不可用指标**：primary_pollutant_exceed_days（全省汇总时无意义，因为首要污染物的定义依赖于数据范围）

    ⚠️ 重要：为什么 primary_pollutant_exceed_days 不能累加？
    - 首要污染物的定义：IAQI 最大的污染物
    - 单城市首要污染物：该城市范围内 IAQI 最大的污染物
    - 全省首要污染物：全省范围内 IAQI 最大的污染物（可能不同）
    - 例如：某天全省O3超标，21个城市都记录"O3作为首要污染物且超标"
    - 如果简单累加，会得到 21天，但实际全省只有 1天
    - 正确做法：从全省原始监测数据重新计算（需要访问所有城市的原始数据）

    Args:
        city_stats: 各城市统计数据字典

    Returns:
        全省汇总统计数据
    """
    if not city_stats:
        return {}

    logger.info("calculating_province_wide_stats", cities_count=len(city_stats))

    # 过滤有效城市数据
    valid_cities = {k: v for k, v in city_stats.items() if v and isinstance(v, dict)}
    if not valid_cities:
        return {}

    num_cities = len(valid_cities)

    # ========== 累加类指标 ==========
    total_exceed_days = sum(s.get("exceed_days", 0) for s in valid_cities.values())
    total_valid_days = sum(s.get("valid_days", 0) for s in valid_cities.values())
    total_primary_days = sum(s.get("total_primary_days", 0) for s in valid_cities.values())

    # 各污染物超标天累加
    exceed_days_by_pollutant = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }
    for city_stats_data in valid_cities.values():
        city_exceed = city_stats_data.get("exceed_days_by_pollutant", {})
        for pollutant in exceed_days_by_pollutant.keys():
            exceed_days_by_pollutant[pollutant] += int(city_exceed.get(pollutant, 0))

    # 首要污染物天数累加
    primary_pollutant_days = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }
    for city_stats_data in valid_cities.values():
        city_primary = city_stats_data.get("primary_pollutant_days", {})
        for pollutant in primary_pollutant_days.keys():
            primary_pollutant_days[pollutant] += int(city_primary.get(pollutant, 0))

    # 首要污染物超标天累加（各地市首要污染物超标天数累加）
    # 注意：这是各地市"首要污染物超标天数"的累加值，用于统计各地市的首要污染物超标情况
    # 含义：全省范围内，各地市作为首要污染物且超标的天数之和
    primary_pollutant_exceed_days = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }
    for city_stats_data in valid_cities.values():
        city_primary_exceed = city_stats_data.get("primary_pollutant_exceed_days", {})
        if city_primary_exceed:  # 确保不是 None
            for pollutant in primary_pollutant_exceed_days.keys():
                primary_pollutant_exceed_days[pollutant] += int(city_primary_exceed.get(pollutant, 0))

    # ========== 均值类指标 ==========
    # 综合指数均值
    composite_index_sum = sum(s.get("composite_index", 0) for s in valid_cities.values())
    avg_composite_index = safe_round(composite_index_sum / num_cities, 3) if num_cities > 0 else 0

    # 各污染物浓度均值（先计算原始均值，再应用最终输出修约）
    so2_sum = sum(s.get("SO2", 0) for s in valid_cities.values())
    no2_sum = sum(s.get("NO2", 0) for s in valid_cities.values())
    pm10_sum = sum(s.get("PM10", 0) for s in valid_cities.values())
    pm25_sum = sum(s.get("PM2_5", 0) for s in valid_cities.values())
    co_p95_sum = sum(s.get("CO_P95", 0) for s in valid_cities.values())
    o3_8h_p90_sum = sum(s.get("O3_8h_P90", 0) for s in valid_cities.values())

    so2_percentile_98_sum = sum(s.get("SO2_P98", 0) for s in valid_cities.values())
    no2_percentile_98_sum = sum(s.get("NO2_P98", 0) for s in valid_cities.values())
    pm10_percentile_95_sum = sum(s.get("PM10_P95", 0) for s in valid_cities.values())
    pm25_percentile_95_sum = sum(s.get("PM2_5_P95", 0) for s in valid_cities.values())

    # 计算原始均值（不修约）
    avg_so2_raw = so2_sum / num_cities if num_cities > 0 else 0
    avg_no2_raw = no2_sum / num_cities if num_cities > 0 else 0
    avg_pm10_raw = pm10_sum / num_cities if num_cities > 0 else 0
    avg_pm25_raw = pm25_sum / num_cities if num_cities > 0 else 0
    avg_co_p95_raw = co_p95_sum / num_cities if num_cities > 0 else 0
    avg_o3_8h_p90_raw = o3_8h_p90_sum / num_cities if num_cities > 0 else 0

    avg_so2_p98_raw = so2_percentile_98_sum / num_cities if num_cities > 0 else 0
    avg_no2_p98_raw = no2_percentile_98_sum / num_cities if num_cities > 0 else 0
    avg_pm10_p95_raw = pm10_percentile_95_sum / num_cities if num_cities > 0 else 0
    avg_pm25_p95_raw = pm25_percentile_95_sum / num_cities if num_cities > 0 else 0

    # 应用最终输出修约规则（与城市统计一致）
    avg_so2 = format_pollutant_value(avg_so2_raw, 'SO2', 'statistical_data', use_final_rounding=True)
    avg_no2 = format_pollutant_value(avg_no2_raw, 'NO2', 'statistical_data', use_final_rounding=True)
    avg_pm10 = format_pollutant_value(avg_pm10_raw, 'PM10', 'statistical_data', use_final_rounding=True)
    avg_pm25 = format_pollutant_value(avg_pm25_raw, 'PM2_5', 'statistical_data', use_final_rounding=True)
    avg_co_p95 = format_pollutant_value(avg_co_p95_raw, 'CO', 'statistical_data', use_final_rounding=True)
    avg_o3_8h_p90 = format_pollutant_value(avg_o3_8h_p90_raw, 'O3_8h', 'statistical_data', use_final_rounding=True)

    avg_so2_p98 = format_pollutant_value(avg_so2_p98_raw, 'SO2', 'statistical_data', use_final_rounding=True)
    avg_no2_p98 = format_pollutant_value(avg_no2_p98_raw, 'NO2', 'statistical_data', use_final_rounding=True)
    avg_pm10_p95 = format_pollutant_value(avg_pm10_p95_raw, 'PM10', 'statistical_data', use_final_rounding=True)
    avg_pm25_p95 = format_pollutant_value(avg_pm25_p95_raw, 'PM2_5', 'statistical_data', use_final_rounding=True)

    # 单项质量指数均值
    single_indexes_sums = {
        'SO2': 0, 'NO2': 0, 'PM10': 0, 'CO': 0, 'PM2_5': 0, 'O3_8h': 0
    }
    for city_stats_data in valid_cities.values():
        city_indexes = city_stats_data.get("single_indexes", {})
        for pollutant in single_indexes_sums.keys():
            single_indexes_sums[pollutant] += city_indexes.get(pollutant, 0)

    single_indexes = {
        pollutant: safe_round(single_indexes_sums[pollutant] / num_cities, 3)
        for pollutant in single_indexes_sums.keys()
    } if num_cities > 0 else {p: 0 for p in single_indexes_sums.keys()}

    # ========== 计算类指标 ==========
    # 超标率和达标率
    exceed_rate = safe_round(total_exceed_days / total_valid_days * 100, 1) if total_valid_days > 0 else 0
    compliance_rate = safe_round((total_valid_days - total_exceed_days) / total_valid_days * 100, 1) if total_valid_days > 0 else 0

    # 各污染物超标率
    exceed_rate_by_pollutant = {}
    for pollutant, days in exceed_days_by_pollutant.items():
        exceed_rate_by_pollutant[pollutant] = safe_round(days / total_valid_days * 100, 1) if total_valid_days > 0 else 0

    # 首要污染物比例
    primary_pollutant_ratio = {}
    for pollutant, days in primary_pollutant_days.items():
        primary_pollutant_ratio[pollutant] = safe_round(days / total_primary_days * 100, 1) if total_primary_days > 0 else 0

    # 总天数累计（各城市总天数累加）
    total_days_sum = sum(s.get("total_days", 0) for s in valid_cities.values())
    total_total_days = int(total_days_sum) if num_cities > 0 else 0

    # 构建全省汇总结果
    province_wide = {
        "composite_index": avg_composite_index,
        "exceed_days": int(total_exceed_days),
        "valid_days": int(total_valid_days),
        "exceed_rate": exceed_rate,
        "compliance_rate": compliance_rate,
        "total_days": int(total_total_days),
        # 六参数统计指标
        "SO2": avg_so2,
        "SO2_P98": avg_so2_p98,
        "NO2": avg_no2,
        "NO2_P98": avg_no2_p98,
        "PM10": avg_pm10,
        "PM10_P95": avg_pm10_p95,
        "PM2_5": avg_pm25,
        "PM2_5_P95": avg_pm25_p95,
        "CO_P95": avg_co_p95,
        "O3_8h_P90": avg_o3_8h_p90,
        # 单项质量指数
        "single_indexes": single_indexes,
        # 首要污染物统计
        "primary_pollutant_days": {k: int(v) for k, v in primary_pollutant_days.items()},
        "primary_pollutant_ratio": primary_pollutant_ratio,
        "total_primary_days": int(total_primary_days),
        # 各污染物超标统计
        "exceed_days_by_pollutant": {k: int(v) for k, v in exceed_days_by_pollutant.items()},
        "exceed_rate_by_pollutant": exceed_rate_by_pollutant,
        # 首要污染物超标天统计（各地市首要污染物超标天数累加）
        "primary_pollutant_exceed_days": primary_pollutant_exceed_days,
        # 全省统计指标类型说明（帮助LLM理解指标含义）
        "_indicator_types": {
            # 均值类指标（各城市平均值）
            "composite_index": "平均值",
            "SO2": "平均值", "SO2_P98": "平均值",
            "NO2": "平均值", "NO2_P98": "平均值",
            "PM10": "平均值", "PM10_P95": "平均值",
            "PM2_5": "平均值", "PM2_5_P95": "平均值",
            "CO_P95": "平均值", "O3_8h_P90": "平均值",
            "single_indexes": "平均值（各城市单项质量指数的平均）",
            "total_days": "累计值（各城市总天数累加）",
            "exceed_rate": "计算值（基于累计值计算）",
            "compliance_rate": "计算值（基于累计值计算）",
            "exceed_rate_by_pollutant": "计算值（基于累计值计算）",
            "primary_pollutant_ratio": "计算值（基于累计值计算）",
            # 累计类指标（各城市累加）
            "exceed_days": "累计值（各城市超标天数累加）",
            "valid_days": "累计值（各城市有效天数累加）",
            "primary_pollutant_days": "累计值（各城市首要污染物天数累加）",
            "total_primary_days": "累计值（各城市首要污染物总天数累加）",
            "exceed_days_by_pollutant": "累计值（各城市污染物超标天数累加）",
            "primary_pollutant_exceed_days": "累计值（各地市首要污染物超标天数累加：统计各地市作为首要污染物且超标的天数之和）"
        }
    }

    logger.info(
        "province_wide_stats_calculated",
        cities_count=num_cities,
        composite_index=avg_composite_index,
        exceed_days=total_exceed_days,
        valid_days=total_valid_days
    )

    return province_wide


# =============================================================================
# 工具类
# =============================================================================

class QueryNewStandardReportTool(LLMTool):
    """
    新标准统计报表查询工具

    查询任意时间段内基于HJ 633-2024新标准的空气质量统计报表
    """

    def __init__(self):
        function_schema = {
            "name": "query_new_standard_report",
            "description": """
查询基于HJ 633-2024新标准的空气质量统计报表。

【核心功能】
- 新标准综合指数计算（所有污染物权重均为1）
- 超标天数和达标率统计（基于单项质量指数 > 1）
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析

【新标准特点】
- PM2.5断点：IAQI=100时60μg/m³（旧标准75）
- PM10断点：IAQI=100时120μg/m³（旧标准150）
- 超标判断：基于单项质量指数 > 1

【返回数据说明】
- result字段：⭐ 统计汇总结果（综合指数、超标天数、首要污染物比例等）
  - **综合指标**：composite_index（综合指数）, exceed_days（超标天数）, valid_days（有效天数）, exceed_rate（超标率%）, compliance_rate（达标率%）, total_days（总天数）
  - **六参数统计**：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
  - **加权单项质量指数**：single_indexes.SO2/NO2/PM10/CO/PM2_5/O3_8h
  - **首要污染物统计**：primary_pollutant_days（各污染物作为首要污染物的天数）, primary_pollutant_ratio（首要污染物比例%）, total_primary_days（总首要污染物天数）, PM2_5_primary_dates（PM2.5作为首要污染物的日期列表）
  - **超标统计**：exceed_days_by_pollutant（各污染物超标天数）, exceed_rate_by_pollutant（各污染物超标率%）, primary_pollutant_exceed_days（首要污染物超标天，既是首要污染物又超标的天数）
  - 单城市查询：直接返回城市统计数据
  - 多城市查询：返回各城市统计数据 + province_wide（全省汇总统计）
  - ⚠️ 重要：result 字段包含完整的统计汇总结果，**直接用于报告生成和分析**
- data_id字段：完整日报数据（基于HJ 633-2024新标准计算的每日监测数据）
  - ⚠️ 重要：data_id 只包含每日监测数据（timestamp、AQI、measurements 等），**不包含**统计汇总指标
  - ❌ 不要从 data_id 读取 exceed_days_by_pollutant、primary_pollutant_exceed_days 等统计字段（这些字段只在 result 中）

【全省汇总统计规则】（多城市查询时）
- **均值类指标**（各城市均值）：composite_index, single_indexes.*, SO2, NO2, PM10, PM2_5, CO_P95, O3_8h_P90等
- **累加类指标**（各城市累加）：exceed_days, valid_days, exceed_days_by_pollutant.*, primary_pollutant_days.*, primary_pollutant_exceed_days.*, total_primary_days
- **计算类指标**：exceed_rate, compliance_rate, exceed_rate_by_pollutant.*, primary_pollutant_ratio

**重要**：全省汇总结果中包含 `_indicator_types` 字段，明确标注每个指标是"平均值"还是"累计值"，避免误解。

**重要**：data_id中的日报数据已用新标准计算结果覆盖原始字段，Agent可直接使用：
- AQI：新标准空气质量指数（覆盖原始值）
- primary_pollutant：新标准首要污染物（覆盖原始值）
- IAQI_PM2_5、IAQI_PM10、IAQI_SO2、IAQI_NO2、IAQI_CO、IAQI_O3_8h：新标准分指数（覆盖原始值）
- single_index_PM2_5_new、single_index_PM10_new等：单项质量指数（新增字段）

使用示例：
- read_data_registry(data_id="xxx", fields=["timestamp", "AQI", "primary_pollutant", "IAQI_PM2_5"])

【输入参数】
- cities: 城市列表
- start_date: 开始日期 (YYYY-MM-DD)
- end_date: 结束日期 (YYYY-MM-DD)
- enable_sand_deduction: 是否启用扣沙处理（默认true，剔除沙尘暴天气的PM2.5/PM10数据）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 'YYYY-MM-DD'"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 'YYYY-MM-DD'"
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理（剔除沙尘暴天气的PM2.5/PM10数据，默认true）"
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_new_standard_report",
            description="Query new standard (HJ 633-2024) air quality statistics report",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        """
        执行新标准统计报表查询

        Args:
            context: 执行上下文
            **kwargs: 工具参数
                - cities: 城市列表
                - start_date: 开始日期 (YYYY-MM-DD)
                - end_date: 结束日期 (YYYY-MM-DD)
                - enable_sand_deduction: 是否启用扣沙处理（默认true）

        Returns:
            新标准统计报表结果（UDF v2.0格式）
        """
        # 提取参数
        cities = kwargs.get("cities", [])
        start_date = kwargs.get("start_date", "")
        end_date = kwargs.get("end_date", "")
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)  # 默认true
        exclude_exceed_details = kwargs.get("exclude_exceed_details", False)  # 默认false（保留详情）

        # 参数验证
        if not cities:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "tool_name": "query_new_standard_report",
                    "error": "Missing required parameter: cities"
                },
                "summary": "缺少必需参数：城市列表"
            }

        if not start_date or not end_date:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "tool_name": "query_new_standard_report",
                    "error": "Missing required parameters: start_date or end_date"
                },
                "summary": "缺少必需参数：开始日期或结束日期"
            }

        # 日期格式验证
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "tool_name": "query_new_standard_report",
                    "error": "Invalid date format. Expected format: YYYY-MM-DD"
                },
                "summary": "日期格式错误，期望格式：YYYY-MM-DD"
            }

        # 执行查询
        return await execute_query_new_standard_report(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            enable_sand_deduction=enable_sand_deduction,
            exclude_exceed_details=exclude_exceed_details,
            context=context
        )
