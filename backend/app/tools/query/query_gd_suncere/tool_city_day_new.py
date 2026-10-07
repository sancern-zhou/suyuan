"""
广东省 Suncere 城市日数据查询工具（新标准 HJ 633-2026）

查询广东省城市日空气质量数据，并自动更新为新标准（HJ 633-2026）字段。

**新标准变化**：
- PM2.5 日平均(IAQI=100): 75 → 60 μg/m³
- PM10 日平均(IAQI=100): 150 → 120 μg/m³

**更新字段**：
- measurements.PM2_5_IAQI → 新标准值
- measurements.PM10_IAQI → 新标准值
- measurements.AQI → 新标准值
- record.air_quality_level → 新标准等级
- record.primary_pollutant → 新标准首要污染物

**修约规则**（按 HJ 633-2026）：
- PM2.5/PM10/SO2/NO2/O3：保留0位小数
- CO：保留1位小数
- IAQI/AQI：向上进位取整数

**扣沙处理**：
- 由接口 sandType 参数处理，工具不再做本地扣沙修正
"""
from typing import Any, Dict, List
import math
import re

from app.tools.query.query_gd_suncere.tool import apply_rounding


def parse_primary_pollutants(primary: Any) -> List[str]:
    """解析首要污染物字符串，支持双/多首要污染物的常见分隔写法。"""
    if not primary:
        return []

    aliases = {
        "PM2.5": "PM2_5",
        "PM2_5": "PM2_5",
        "PM25": "PM2_5",
        "PM10": "PM10",
        "SO2": "SO2",
        "NO2": "NO2",
        "CO": "CO",
        "O3": "O3_8h",
        "O3_8H": "O3_8h",
        "O3-8H": "O3_8h",
        "O3_8": "O3_8h",
        "臭氧": "O3_8h",
        "二氧化氮": "NO2",
        "二氧化硫": "SO2",
        "一氧化碳": "CO",
    }
    valid_pollutants = {"PM2_5", "PM10", "SO2", "NO2", "CO", "O3_8h"}

    normalized = str(primary).strip()
    if not normalized or normalized in {"-", "无", "None", "null"}:
        return []

    parts = re.split(r"[，,、；;/|]+|和|及|与|\s+", normalized)
    pollutants = []
    seen = set()
    for part in parts:
        token = part.strip()
        if not token:
            continue

        token_key = token.upper().replace(" ", "")
        token_key = token_key.replace("PM2.5", "PM2_5")
        pollutant = aliases.get(token) or aliases.get(token_key)

        if pollutant in valid_pollutants and pollutant not in seen:
            pollutants.append(pollutant)
            seen.add(pollutant)

    return pollutants


def should_use_api_primary_pollutants_for_new_standard(
    api_primary_pollutants: List[str],
    calculated_primary_pollutants: List[str],
    pm25: float,
    pm10: float,
) -> bool:
    """仅在扣沙后颗粒物置零且接口双首污补充 NO2 时使用接口首污。"""
    if len(api_primary_pollutants) <= 1:
        return False

    if "NO2" not in api_primary_pollutants or "NO2" in calculated_primary_pollutants:
        return False

    return pm25 <= 0 and pm10 <= 0


# -----------------------------------------------------------------------------
# 新标准 IAQI 断点配置（HJ 633-2026）
# -----------------------------------------------------------------------------
# IAQI 分段断点表：[浓度限值, IAQI值]
# 浓度单位：μg/m³（CO为mg/m³）

IAQI_BREAKPOINTS_NEW = {
    'SO2': [
        (0, 0), (50, 50), (150, 100), (475, 150),
        (800, 200), (1600, 300), (2100, 400), (2620, 500)
    ],
    'NO2': [
        (0, 0), (40, 50), (80, 100), (180, 150),
        (280, 200), (565, 300), (750, 400), (940, 500)
    ],
    'PM10': [
        (0, 0), (50, 50), (120, 100), (250, 150),
        (350, 200), (420, 300), (500, 400), (600, 500)
    ],
    'CO': [
        (0, 0), (2, 50), (4, 100), (14, 150),
        (24, 200), (36, 300), (48, 400), (60, 500)
    ],
    'O3_8h': [
        (0, 0), (100, 50), (160, 100), (215, 150),
        (265, 200), (800, 300)
    ],
    'PM2_5': [
        (0, 0), (35, 50), (60, 100), (115, 150),
        (150, 200), (250, 300), (350, 400), (500, 500)
    ]
}


def calculate_iaqi_new(concentration: float, pollutant: str) -> int:
    """
    计算新标准（HJ 633-2026）污染物的空气质量分指数（IAQI）

    使用分段线性插值公式：
    IAQIP = (IAQIHi - IAQILo) / (BPHi - BPLo) × (CP - BPLo) + IAQILo

    特殊规则：
    - O3_8h 浓度 > 800 时，IAQI 固定为 300
    - 计算结果向上进位取整数（不四舍五入）

    Args:
        concentration: 污染物浓度值（μg/m³，CO为mg/m³）
        pollutant: 污染物名称（'SO2', 'NO2', 'PM10', 'CO', 'O3_8h', 'PM2_5'）

    Returns:
        IAQI值（整数，向上进位）
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
            # 向上进位取整数（HJ 633-2026 要求）
            return math.ceil(iaqi)

    # 浓度超过最高分段，返回最高IAQI
    return breakpoints[-1][1]


def get_aqi_level(aqi: int) -> str:
    """
    根据AQI值获取空气质量等级

    Args:
        aqi: AQI值

    Returns:
        空气质量等级名称
    """
    if aqi <= 50:
        return '优'
    elif aqi <= 100:
        return '良'
    elif aqi <= 150:
        return '轻度污染'
    elif aqi <= 200:
        return '中度污染'
    elif aqi <= 300:
        return '重度污染'
    else:
        return '严重污染'


def update_to_new_standard(standardized_records: List[Dict]) -> None:
    """
    将标准化记录更新为新标准字段

    更新内容：
    - measurements 浓度值 → 按日数据修约规则修约（保留整数位）
    - measurements.PM2_5_IAQI → 新标准值
    - measurements.PM10_IAQI → 新标准值
    - measurements.AQI → 新标准值
    - record.air_quality_level → 新标准等级
    - record.primary_pollutant → 新标准首要污染物

    Args:
        standardized_records: 标准化后的记录列表（直接修改）
    """
    def safe_float(value, default=0.0):
        """安全转换为浮点数"""
        if value is None or value == '' or value == '-':
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    for record in standardized_records:
        measurements = record.get("measurements", {})
        original_primary_pollutants = parse_primary_pollutants(record.get("primary_pollutant", ""))

        # 提取浓度值
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

        # 应用修约规则并更新 measurements（日数据：0位小数转为整数）
        if pm25_raw > 0:
            measurements['PM2_5'] = int(apply_rounding(pm25_raw, 'PM2_5', 'raw_data'))
        if pm10_raw > 0:
            measurements['PM10'] = int(apply_rounding(pm10_raw, 'PM10', 'raw_data'))
        measurements['SO2'] = int(apply_rounding(so2_raw, 'SO2', 'raw_data'))
        measurements['NO2'] = int(apply_rounding(no2_raw, 'NO2', 'raw_data'))
        measurements['CO'] = apply_rounding(co_raw, 'CO', 'raw_data')  # CO保留1位小数
        measurements['O3_8h'] = int(apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data'))

        # 计算新标准 IAQI 并重算 AQI 和首要污染物
        pm25_iaqi = calculate_iaqi_new(pm25_raw, 'PM2_5') if pm25_raw > 0 else 0
        pm10_iaqi = calculate_iaqi_new(pm10_raw, 'PM10') if pm10_raw > 0 else 0
        so2_iaqi = calculate_iaqi_new(so2_raw, 'SO2')
        no2_iaqi = calculate_iaqi_new(no2_raw, 'NO2')
        co_iaqi = calculate_iaqi_new(co_raw, 'CO')
        o3_8h_iaqi = calculate_iaqi_new(o3_8h_raw, 'O3_8h')

        measurements['PM2_5_IAQI'] = pm25_iaqi
        measurements['PM10_IAQI'] = pm10_iaqi
        measurements['SO2_IAQI'] = so2_iaqi
        measurements['NO2_IAQI'] = no2_iaqi
        measurements['CO_IAQI'] = co_iaqi
        measurements['O3_8h_IAQI'] = o3_8h_iaqi

        aqi = max(pm25_iaqi, pm10_iaqi, so2_iaqi, no2_iaqi, co_iaqi, o3_8h_iaqi)
        measurements['AQI'] = aqi

        calculated_primary_pollutants = []
        if aqi > 50:
            for pollutant, iaqi in [('PM2_5', pm25_iaqi), ('PM10', pm10_iaqi),
                                    ('SO2', so2_iaqi), ('NO2', no2_iaqi),
                                    ('CO', co_iaqi), ('O3_8h', o3_8h_iaqi)]:
                if iaqi == aqi:
                    calculated_primary_pollutants.append(pollutant)

        use_api_primary_pollutants = should_use_api_primary_pollutants_for_new_standard(
            original_primary_pollutants,
            calculated_primary_pollutants,
            pm25_raw,
            pm10_raw,
        )
        primary_pollutants = (
            original_primary_pollutants
            if use_api_primary_pollutants
            else calculated_primary_pollutants
        )
        primary_pollutant = ",".join(primary_pollutants) if primary_pollutants else None

        air_quality_level = get_aqi_level(aqi)

        # 更新顶层字段
        record['air_quality_level'] = air_quality_level
        record['primary_pollutant'] = primary_pollutant
        if use_api_primary_pollutants:
            record['primary_pollutant_calc_new'] = (
                ",".join(calculated_primary_pollutants)
                if calculated_primary_pollutants else None
            )
        else:
            record.pop('primary_pollutant_calc_new', None)
