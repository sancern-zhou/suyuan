"""
广东省 Suncere 城市日数据查询工具（新标准 HJ 633-2024）

查询广东省城市日空气质量数据，并自动更新为新标准（HJ 633-2024）字段。

**新标准变化**：
- PM2.5 日平均(IAQI=100): 75 → 60 μg/m³
- PM10 日平均(IAQI=100): 150 → 120 μg/m³

**更新字段**：
- measurements.PM2_5_IAQI → 新标准值
- measurements.PM10_IAQI → 新标准值
- measurements.AQI → 新标准值
- record.air_quality_level → 新标准等级
- record.primary_pollutant → 新标准首要污染物

**修约规则**（按 HJ 633-2024）：
- PM2.5/PM10/SO2/NO2/O3：保留0位小数
- CO：保留1位小数
- IAQI/AQI：向上进位取整数
"""
from typing import Dict, Any, List
import math
import structlog

from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.agent.context.execution_context import ExecutionContext
from app.utils.data_standardizer import get_data_standardizer


logger = structlog.get_logger()


# -----------------------------------------------------------------------------
# 新标准 IAQI 断点配置（HJ 633-2024）
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
    计算新标准（HJ 633-2024）污染物的空气质量分指数（IAQI）

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
            # 向上进位取整数（HJ 633-2024 要求）
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
    - measurements.PM2_5_IAQI → 新标准值
    - measurements.PM10_IAQI → 新标准值
    - measurements.AQI → 新标准值
    - record.air_quality_level → 新标准等级
    - record.primary_pollutant → 新标准首要污染物

    Args:
        standardized_records: 标准化后的记录列表（直接修改）
    """
    for record in standardized_records:
        measurements = record.get("measurements", {})

        # 提取浓度值（支持多种字段名格式）
        pm25_raw = (measurements.get("PM2_5") or measurements.get("pm2_5") or
                   record.get("pm2_5") or record.get("PM2_5") or 0)
        pm10_raw = (measurements.get("PM10") or measurements.get("pm10") or
                   record.get("pm10") or record.get("PM10") or 0)
        so2_raw = (measurements.get("SO2") or measurements.get("so2") or
                  record.get("so2") or record.get("SO2") or 0)
        no2_raw = (measurements.get("NO2") or measurements.get("no2") or
                  record.get("no2") or record.get("NO2") or 0)
        co_raw = (measurements.get("CO") or measurements.get("co") or
                 record.get("co") or record.get("CO") or 0)
        o3_8h_raw = (measurements.get("O3_8h") or measurements.get("o3_8h") or
                    record.get("o3_8h") or record.get("O3_8h") or 0)

        # 计算新标准 IAQI（HJ 633-2024，向上进位取整）
        pm25_iaqi = calculate_iaqi_new(pm25_raw, 'PM2_5')
        pm10_iaqi = calculate_iaqi_new(pm10_raw, 'PM10')
        so2_iaqi = calculate_iaqi_new(so2_raw, 'SO2')
        no2_iaqi = calculate_iaqi_new(no2_raw, 'NO2')
        co_iaqi = calculate_iaqi_new(co_raw, 'CO')
        o3_8h_iaqi = calculate_iaqi_new(o3_8h_raw, 'O3_8h')

        # 计算 AQI（最大 IAQI）
        aqi = max(pm25_iaqi, pm10_iaqi, so2_iaqi, no2_iaqi, co_iaqi, o3_8h_iaqi)

        # 确定首要污染物（AQI > 50 时）
        pollutants_with_iaqi = {
            'PM2_5': pm25_iaqi,
            'PM10': pm10_iaqi,
            'SO2': so2_iaqi,
            'NO2': no2_iaqi,
            'CO': co_iaqi,
            'O3_8h': o3_8h_iaqi
        }
        primary_pollutant = None
        if aqi > 50:
            for pollutant, iaqi in pollutants_with_iaqi.items():
                if iaqi == aqi:
                    primary_pollutant = pollutant
                    break

        # 确定空气质量等级
        air_quality_level = get_aqi_level(aqi)

        # 更新 measurements 中的 IAQI 字段
        measurements['PM2_5_IAQI'] = pm25_iaqi
        measurements['PM10_IAQI'] = pm10_iaqi
        measurements['SO2_IAQI'] = so2_iaqi
        measurements['NO2_IAQI'] = no2_iaqi
        measurements['CO_IAQI'] = co_iaqi
        measurements['O3_8h_IAQI'] = o3_8h_iaqi
        measurements['AQI'] = aqi

        # 更新顶层字段
        record['air_quality_level'] = air_quality_level
        record['primary_pollutant'] = primary_pollutant


def execute_query_city_day_new_standard(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    data_type: int = 1
) -> Dict[str, Any]:
    """
    查询城市日数据（新标准 HJ 633-2024）

    复用现有查询逻辑，但将返回的数据更新为新标准字段。

    Args:
        cities: 城市名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        context: 执行上下文
        data_type: 数据类型（0原始实况，1审核实况，2原始标况，3审核标况），默认1

    Returns:
        UDF v2.0 格式的查询结果
    """
    from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

    logger.info(
        "query_city_day_new_standard_start",
        cities=cities,
        start_date=start_date,
        end_date=end_date
    )

    try:
        api_client = get_gd_suncere_api_client()

        # 转换城市名称为编码
        city_codes = QueryGDSuncereDataTool.geo_resolver.resolve_city_codes(cities)

        if not city_codes:
            raise Exception(f"未找到任何有效的城市代码: {cities}")

        # 智能分段查询：根据查询日期范围自动判断是否需要分段
        from app.tools.query.query_gd_suncere.tool import calculate_date_segments

        # 计算分段
        segments = calculate_date_segments(start_date, end_date)
        logger.info(
            "query_city_day_new_standard_segments",
            segment_count=len(segments),
            segments=segments
        )

        # 如果有多个分段，使用并发查询
        if len(segments) > 1:
            import asyncio

            async def fetch_all_segments():
                from app.tools.query.query_gd_suncere.tool import query_day_data_by_segment
                tasks = []
                for seg_start, seg_end, seg_data_type in segments:
                    task = query_day_data_by_segment(
                        api_client=api_client,
                        city_codes=city_codes,
                        start_date=seg_start,
                        end_date=seg_end,
                        data_type=seg_data_type
                    )
                    tasks.append(task)
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results

            # 执行并发查询
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            all_results = loop.run_until_complete(fetch_all_segments())
            loop.close()

            # 合并结果
            raw_records = []
            for i, result in enumerate(all_results):
                if isinstance(result, Exception):
                    logger.error(
                        "query_city_day_new_standard_segment_error",
                        segment_index=i,
                        error=str(result)
                    )
                elif isinstance(result, list):
                    raw_records.extend(result)
                    logger.info(
                        "query_city_day_new_standard_segment_success",
                        segment_index=i,
                        record_count=len(result)
                    )

            logger.info(
                "query_city_day_new_standard_segments_merged",
                total_segments=len(segments),
                total_records=len(raw_records)
            )
        else:
            # 单分段，直接查询
            seg_start, seg_end, seg_data_type = segments[0]
            response = api_client.query_city_day_data(
                city_codes=city_codes,
                start_date=seg_start,
                end_date=seg_end,
                data_type=seg_data_type
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            raw_records = response.get("result", [])

        if not raw_records:
            logger.warning(
                "query_city_day_new_standard_no_data",
                cities=cities,
                date_range=f"{start_date} to {end_date}"
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    "tool_name": "query_gd_suncere_city_day_new",
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "standard": "HJ 633-2024",
                    "message": "查询成功但无数据返回"
                },
                "summary": f"未找到 {', '.join(cities)} 在指定时间段的日报数据"
            }

        logger.info(
            "query_city_day_new_standard_data_received",
            record_count=len(raw_records)
        )

        # 数据标准化
        standardizer = get_data_standardizer()
        standardized_records = standardizer.standardize(raw_records)

        logger.info(
            "city_day_new_standard_data_standardized",
            raw_count=len(raw_records),
            standardized_count=len(standardized_records)
        )

        # 更新为新标准字段（HJ 633-2024）
        update_to_new_standard(standardized_records)

        logger.info(
            "city_day_new_standard_fields_updated",
            record_count=len(standardized_records),
            updated_fields=["PM2_5_IAQI", "PM10_IAQI", "AQI", "air_quality_level", "primary_pollutant"]
        )

        # 保存到上下文
        data_id = context.data_manager.save_data(
            data=standardized_records,
            schema="air_quality_unified",
            metadata={
                "source": "gd_suncere_api",
                "query_type": "city_day_new_standard",
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "standard": "HJ 633-2024",  # 标记为新标准
                "schema_version": "v2.0",
                "field_mapping_applied": True,
                "field_mapping_info": standardizer.get_field_mapping_info() if standardizer else {}
            }
        )

        logger.info(
            "city_day_new_standard_data_saved",
            data_id=data_id,
            record_count=len(standardized_records)
        )

        return {
            "status": "success",
            "success": True,
            "data": standardized_records[:50],  # 返回前50条供预览
            "metadata": {
                "tool_name": "query_gd_suncere_city_day_new",
                "data_id": data_id,
                "total_records": len(standardized_records),
                "returned_records": min(50, len(standardized_records)),
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "standard": "HJ 633-2024",  # 标记为新标准
                "schema_version": "v2.0",
                "source": "gd_suncere_api"
            },
            "summary": f"成功获取 {', '.join(cities)} 的日报数据共 {len(standardized_records)} 条（新标准 HJ 633-2024），已保存为 {data_id}"
        }

    except Exception as e:
        logger.error(
            "query_city_day_new_standard_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return {
            "status": "failed",
            "success": False,
            "error": str(e),
            "data": None,
            "metadata": {
                "tool_name": "query_gd_suncere_city_day_new",
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "standard": "HJ 633-2024"
            },
            "summary": f"新标准城市日数据查询失败: {str(e)}"
        }
