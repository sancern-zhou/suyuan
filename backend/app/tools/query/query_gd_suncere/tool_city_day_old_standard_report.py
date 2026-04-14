"""
旧标准统计报表查询工具

基于 HJ 633-2013 旧标准的空气质量统计报表查询工具

【核心功能】
- 旧标准综合指数计算（所有污染物权重均为1）
- 超标天数和达标率统计
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析

【旧标准特点】
- PM2.5断点：IAQI=100时75μg/m³（新标准60）
- PM10断点：IAQI=100时150μg/m³（新标准120）
- 超标判断：基于单项质量指数 > 1

【返回数据说明】
- result字段：统计汇总结果（综合指数、超标天数、首要污染物比例等）
- data_id字段：完整日报数据（基于HJ 633-2013旧标准计算）

**重要**：data_id中的日报数据已用旧标准计算结果覆盖原始字段，Agent可直接使用：
- AQI：旧标准空气质量指数（覆盖原始值）
- primary_pollutant：旧标准首要污染物（覆盖原始值）
- IAQI_PM2_5、IAQI_PM10、IAQI_SO2、IAQI_NO2、IAQI_CO、IAQI_O3_8h：旧标准分指数（覆盖原始值）
- single_index_PM2_5_old、single_index_PM10_old等：单项质量指数（新增字段）

使用示例：
- read_data_registry(data_id="xxx", fields=["timestamp", "AQI", "primary_pollutant", "IAQI_PM2_5"])
"""

import asyncio
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
from app.tools.query.query_gd_suncere.tool import (
    QueryGDSuncereDataTool,
    OLD_STANDARD_LIMITS,
    ANNUAL_STANDARD_LIMITS_OLD,
    WEIGHTS,
    IAQI_BREAKPOINTS_OLD,
    calculate_iaqi,
    safe_round,
    apply_rounding,
    format_pollutant_value
)
from app.services.gd_suncere_api_client import get_gd_suncere_api_client

logger = structlog.get_logger()


# =============================================================================
# 主函数
# =============================================================================

async def execute_query_old_standard_report(
    cities: List[str],
    start_date: str,
    end_date: str,
    enable_sand_deduction: bool = True,
    use_new_composite_algorithm: bool = False,
    context: Optional[ExecutionContext] = None
) -> Dict[str, Any]:
    """
    执行旧标准统计报表查询

    Args:
        cities: 城市列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        enable_sand_deduction: 是否启用扣沙处理（默认True，剔除沙尘暴天气的PM2.5/PM10数据）
        use_new_composite_algorithm: 是否使用新综合指数算法（默认False，使用旧算法）
            - False（默认）: 旧综合指数算法（所有污染物权重均为1）
            - True: 新综合指数算法（PM2.5权重3，NO2权重2，O3权重2，其他权重1）
        context: 执行上下文（可选）

    Returns:
        旧标准统计报表结果（UDF v2.0格式）
    """
    # 初始化
    if not context:
        return {
            "status": "failed",
            "success": False,
            "error": "缺少ExecutionContext参数",
            "data": None,
            "metadata": {},
            "summary": "缺少ExecutionContext参数"
        }

    logger.info(
        "old_standard_report_query_start",
        cities=cities,
        start_date=start_date,
        end_date=end_date,
        enable_sand_deduction=enable_sand_deduction,
        session_id=getattr(context, 'session_id', 'unknown')
    )

    try:
        # 步骤1: 并发查询所有城市的日数据（enable_sand_deduction 由日数据工具处理）
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_city_day

        async def query_single_city(city: str):
            """查询单个城市的数据（包装同步函数为协程）"""
            return execute_query_gd_suncere_city_day(
                cities=[city],
                start_date=start_date,
                end_date=end_date,
                context=context,
                enable_sand_deduction=enable_sand_deduction
            )

        # 创建并发查询任务
        query_tasks = [query_single_city(city) for city in cities]

        # 并发执行查询
        city_results = await asyncio.gather(*query_tasks, return_exceptions=True)

        # 步骤2: 合并所有城市的日数据
        all_city_data = {}
        all_daily_records = []

        for i, result in enumerate(city_results):
            if isinstance(result, Exception):
                logger.warning(
                    "city_query_failed",
                    city=cities[i],
                    error=str(result)
                )
                continue

            if not result.get("success"):
                logger.warning(
                    "city_query_no_data",
                    city=cities[i],
                    summary=result.get("summary", "Unknown error")
                )
                continue

            # 获取日数据
            data_id_info = result.get("metadata", {}).get("data_id")
            if data_id_info:
                # data_id 可能是字符串或字典（包含 data_id 和 file_path）
                if isinstance(data_id_info, dict):
                    data_id_str = data_id_info.get("data_id")
                else:
                    data_id_str = data_id_info

                if data_id_str:
                    daily_data = context.data_manager.get_raw_data(data_id_str)
                    if daily_data:
                        all_city_data[cities[i]] = daily_data
                        all_daily_records.extend(daily_data)
                        logger.info(
                            "city_daily_data_loaded",
                            city=cities[i],
                            record_count=len(daily_data)
                        )

        if not all_daily_records:
            return {
                "status": "empty",
                "success": True,
                "data": None,
                "metadata": {
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "total_records": 0,
                    "schema_version": "v2.0"
                },
                "summary": f"未查询到数据：{', '.join(cities)} {start_date} 至 {end_date}"
            }

        # 步骤3: 标准化数据（扣沙已由日数据工具处理，无需重复）
        data_standardizer = DataStandardizer()
        standardized_data = []
        for record in all_daily_records:
            try:
                standardized = data_standardizer.standardize(record)
                standardized_data.append(standardized)
            except Exception as e:
                logger.warning("data_standardization_failed", record=record, error=str(e))
                standardized_data.append(record)

        # 步骤5: 重新计算旧标准 AQI、IAQI、首要污染物
        for record in standardized_data:
            measurements = record.get("measurements", {})

            # 提取浓度值
            def safe_float(value, default=0.0):
                if value is None or value == '' or value == '-':
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            # 检查是否为扣沙日
            is_sand_day = record.get("is_sand_deduction_day", False)

            if is_sand_day:
                # 扣沙日：PM2.5/PM10为"-"，使用原始值计算统计指标
                pm25_raw = safe_float(record.get("PM2_5_original"))
                pm10_raw = safe_float(record.get("PM10_original"))
            else:
                pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5"))
                pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10"))

            so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2"))
            no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2"))
            co_raw = safe_float(measurements.get("CO") or measurements.get("co"))
            o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h"))

            # 按原始监测数据规则修约
            pm25 = apply_rounding(pm25_raw, 'PM2_5', 'raw_data')
            pm10 = apply_rounding(pm10_raw, 'PM10', 'raw_data')
            so2 = apply_rounding(so2_raw, 'SO2', 'raw_data')
            no2 = apply_rounding(no2_raw, 'NO2', 'raw_data')
            co = apply_rounding(co_raw, 'CO', 'raw_data')
            o3_8h = apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data')

            # 计算旧标准IAQI并向上进位取整数
            import math
            # 扣沙日的PM2.5/PM10 IAQI设为0，不参与AQI计算
            pm25_iaqi_old = 0 if is_sand_day else math.ceil(calculate_iaqi(pm25, 'PM2_5', 'old'))
            pm10_iaqi_old = 0 if is_sand_day else math.ceil(calculate_iaqi(pm10, 'PM10', 'old'))
            so2_iaqi_old = math.ceil(calculate_iaqi(so2, 'SO2', 'old'))
            no2_iaqi_old = math.ceil(calculate_iaqi(no2, 'NO2', 'old'))
            co_iaqi_old = math.ceil(calculate_iaqi(co, 'CO', 'old'))
            o3_8h_iaqi_old = math.ceil(calculate_iaqi(o3_8h, 'O3_8h', 'old'))

            # 扣沙日：AQI不重算，使用扣沙表中的值；非扣沙日：正常计算
            if is_sand_day:
                aqi_old = record.get("AQI", 0)
            else:
                aqi_old = math.ceil(max(pm25_iaqi_old, pm10_iaqi_old, so2_iaqi_old,
                                       no2_iaqi_old, co_iaqi_old, o3_8h_iaqi_old))

            # 更新measurements中的IAQI（覆盖原始值）
            if isinstance(record.get("measurements"), dict):
                record["measurements"]["IAQI_PM2_5"] = pm25_iaqi_old
                record["measurements"]["IAQI_PM10"] = pm10_iaqi_old
                record["measurements"]["IAQI_SO2"] = so2_iaqi_old
                record["measurements"]["IAQI_NO2"] = no2_iaqi_old
                record["measurements"]["IAQI_CO"] = co_iaqi_old
                record["measurements"]["IAQI_O3_8h"] = o3_8h_iaqi_old

            # 扣沙日：AQI和首要污染物不覆盖（保持扣沙表中的值）
            if not is_sand_day:
                record["AQI"] = aqi_old
                if "aqi" in record:
                    record["aqi"] = aqi_old

            # 计算旧标准首要污染物
            # 【扣沙日特殊处理】首要污染物已在 clean_sand_deduction_data 中设置为扣沙表中的值
            primary_from_sand = record.get("primary_pollutant")
            if is_sand_day:
                # 扣沙日：直接使用扣沙表中的首要污染物
                # None表示无首要污染物（AQI ≤ 50），不需要重新计算
                if primary_from_sand:
                    primary_pollutants_this_day = [primary_from_sand]
                else:
                    primary_pollutants_this_day = []
            else:
                # 非扣沙日：重新计算首要污染物
                pollutants_with_iaqi_old = {
                    'PM2_5': pm25_iaqi_old, 'PM10': pm10_iaqi_old, 'SO2': so2_iaqi_old,
                    'NO2': no2_iaqi_old, 'CO': co_iaqi_old, 'O3_8h': o3_8h_iaqi_old
                }

                primary_pollutants_this_day = []
                if aqi_old > 50:
                    for pollutant, iaqi in pollutants_with_iaqi_old.items():
                        # 使用向上取整后的IAQI进行比较
                        if iaqi == aqi_old:
                            primary_pollutants_this_day.append(pollutant)

            if primary_pollutants_this_day:
                record["primary_pollutant"] = ",".join(primary_pollutants_this_day)
            else:
                record["primary_pollutant"] = None

            # 单项质量指数（新增字段，标识旧标准）
            pm25_index_old = safe_round(pm25 / OLD_STANDARD_LIMITS['PM2_5'], 3) if pm25 > 0 else 0
            pm10_index_old = safe_round(pm10 / OLD_STANDARD_LIMITS['PM10'], 3) if pm10 > 0 else 0
            so2_index_old = safe_round(so2 / OLD_STANDARD_LIMITS['SO2'], 3) if so2 > 0 else 0
            no2_index_old = safe_round(no2 / OLD_STANDARD_LIMITS['NO2'], 3) if no2 > 0 else 0
            co_index_old = safe_round(co / OLD_STANDARD_LIMITS['CO'], 3) if co > 0 else 0
            o3_8h_index_old = safe_round(o3_8h / OLD_STANDARD_LIMITS['O3_8h'], 3) if o3_8h > 0 else 0

            record["single_index_PM2_5_old"] = pm25_index_old
            record["single_index_PM10_old"] = pm10_index_old
            record["single_index_SO2_old"] = so2_index_old
            record["single_index_NO2_old"] = no2_index_old
            record["single_index_CO_old"] = co_index_old
            record["single_index_O3_8h_old"] = o3_8h_index_old

        # 步骤6: 按城市分组并计算旧标准统计
        from collections import defaultdict

        daily_data_by_city = defaultdict(list)
        for record in standardized_data:
            city_name = (
                record.get("city", "") or
                record.get("city_name", "") or
                record.get("cityName", "") or
                record.get("name", "")
            )
            if city_name:
                daily_data_by_city[city_name].append(record)

        # 容错：如果没有城市字段，使用查询参数
        if not daily_data_by_city and len(cities) == 1:
            daily_data_by_city[cities[0]] = standardized_data

        # 计算各城市的旧标准统计
        city_stats = {}

        for city, city_daily_records in daily_data_by_city.items():
            logger.info("calculating_old_standard_stats_for_city", city=city, day_count=len(city_daily_records))

            # 计算旧标准统计
            city_stat = calculate_old_standard_city_stats(
                city_daily_records, city,
                use_new_composite_algorithm=use_new_composite_algorithm
            )
            city_stats[city] = city_stat

        # 计算全省汇总统计（多城市查询时）
        province_wide_stats = None
        if len(cities) > 1:
            # 导入全省汇总计算函数
            from app.tools.query.query_new_standard_report.tool import calculate_province_wide_stats
            province_wide_stats = calculate_province_wide_stats(city_stats)

        # 步骤7: 保存完整日报数据到数据注册表
        # ⚠️ 已禁用：统计报表工具不返回 data_id，避免 LLM 尝试从 data_id 读取统计字段
        saved_data = None
        # data_id_str = None
        # if context:
        #     try:
        #         data_id_str = context.save_data(
        #             data=standardized_data,  # 保存清洗、标准化和旧标准计算后的数据
        #             schema="air_quality_unified"
        #         )
        #         logger.info("old_standard_daily_data_saved", data_id=data_id_str)
        #     except Exception as e:
        #         logger.warning("failed_to_save_old_standard_daily_data", error=str(e))
        data_id_str = None  # 统计报表工具不返回 data_id

        # 步骤8: 构建返回结果
        total_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

        # 综合指数算法说明
        composite_algorithm_desc = "新综合指数算法（PM2.5权重3，NO2权重2，O3权重2）" if use_new_composite_algorithm else "旧综合指数算法（所有权重均为1）"

        # 统计结果放在 result 字段，原始日数据通过 data_id 引用
        if len(cities) == 1 and city_stats:
            city_name = list(city_stats.keys())[0]
            result_summary_data = city_stats[city_name]
            result_summary = f"旧标准统计报表查询完成（{composite_algorithm_desc}），{city_name} {start_date} 至 {end_date}（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
        else:
            result_summary_data = city_stats
            result_summary = f"旧标准统计报表查询完成（{composite_algorithm_desc}），共{len(city_stats)}个城市（数据为审核实况，最近的3天自动使用原始数据） | 无原始数据 data_id，统计汇总指标已完整展示在 result 字段中"
            # 添加全省汇总到结果
            if province_wide_stats:
                result_summary_data["province_wide"] = province_wide_stats

        # 添加数据存储信息到摘要
        # if data_id_str:
        #     result_summary += f" | 日报数据已保存 (data_id: {data_id_str})"

        metadata = {
            "tool_name": "query_old_standard_report",
            "cities": cities,
            "date_range": f"{start_date} to {end_date}",
            "schema_version": "v2.0",
            "total_days": total_days,
            "standard": "HJ 633-2013",  # 标识旧标准
            "composite_algorithm": "new" if use_new_composite_algorithm else "old",  # 综合指数算法标识
            "enable_sand_deduction": enable_sand_deduction
        }

        if data_id_str:
            metadata["data_id"] = data_id_str

        return {
            "status": "success",
            "success": True,
            "data": None,
            "metadata": metadata,
            "summary": result_summary,
            "result": result_summary_data
        }

    except Exception as e:
        logger.error(
            "old_standard_report_query_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        return QueryGDSuncereDataTool._create_error_response(str(e))


def calculate_old_standard_city_stats(
    daily_records: List[Dict],
    city_name: str,
    use_new_composite_algorithm: bool = False
) -> Dict[str, Any]:
    """
    计算单个城市的旧标准统计指标

    Args:
        daily_records: 日报数据列表（已清洗扣沙日、已标准化、已计算旧标准AQI/IAQI）
        city_name: 城市名称
        use_new_composite_algorithm: 是否使用新综合指数算法（默认False，使用旧算法）
            - False（默认）: 旧综合指数算法（所有污染物权重均为1）
            - True: 新综合指数算法（PM2.5权重3，NO2权重2，O3权重2，其他权重1）

    Returns:
        旧标准统计结果
    """
    if not daily_records:
        return {}

    logger.info("calculating_old_standard_city_stats", city=city_name, day_count=len(daily_records))

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

    # 收集每日浓度值用于计算百分位数
    daily_co_values = []
    daily_o3_8h_values = []
    daily_so2_values = []
    daily_no2_values = []
    daily_pm10_values = []
    daily_pm25_values = []

    # 首要污染物统计
    primary_pollutant_days = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }

    # 各污染物超标天数统计
    exceed_days_by_pollutant = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }

    # 首要污染物超标天统计（某污染物既是首要污染物又超标）
    primary_pollutant_exceed_days = {
        'PM2_5': 0, 'PM10': 0, 'SO2': 0, 'NO2': 0, 'CO': 0, 'O3_8h': 0
    }

    # 有效天数统计（只要有一项污染物有数据就算有效天）
    valid_days = 0

    for record in daily_records:
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

        # 提取浓度值
        pm25_raw = safe_float(measurements.get("PM2_5") or measurements.get("pm2_5"))
        pm10_raw = safe_float(measurements.get("PM10") or measurements.get("pm10"))
        so2_raw = safe_float(measurements.get("SO2") or measurements.get("so2"))
        no2_raw = safe_float(measurements.get("NO2") or measurements.get("no2"))
        co_raw = safe_float(measurements.get("CO") or measurements.get("co"))
        o3_8h_raw = safe_float(measurements.get("O3_8h") or measurements.get("o3_8h"))

        # 按原始监测数据规则修约
        pm25 = apply_rounding(pm25_raw, 'PM2_5', 'raw_data')
        pm10 = apply_rounding(pm10_raw, 'PM10', 'raw_data')
        so2 = apply_rounding(so2_raw, 'SO2', 'raw_data')
        no2 = apply_rounding(no2_raw, 'NO2', 'raw_data')
        co = apply_rounding(co_raw, 'CO', 'raw_data')
        o3_8h = apply_rounding(o3_8h_raw, 'O3_8h', 'raw_data')

        # 累加修约后的浓度值（扣沙日PM2.5/PM10为0，不计入）
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

        # 计算旧标准单项质量指数 Ii = Ci / Si
        pm25_index_old = pm25 / OLD_STANDARD_LIMITS['PM2_5'] if pm25 > 0 else 0
        pm10_index_old = pm10 / OLD_STANDARD_LIMITS['PM10'] if pm10 > 0 else 0
        so2_index_old = so2 / OLD_STANDARD_LIMITS['SO2'] if so2 > 0 else 0
        no2_index_old = no2 / OLD_STANDARD_LIMITS['NO2'] if no2 > 0 else 0
        co_index_old = co / OLD_STANDARD_LIMITS['CO'] if co > 0 else 0
        o3_8h_index_old = o3_8h / OLD_STANDARD_LIMITS['O3_8h'] if o3_8h > 0 else 0

        # 判断该日是否超标
        max_single_index_old = max(pm25_index_old, pm10_index_old, so2_index_old,
                                   no2_index_old, co_index_old, o3_8h_index_old)

        # 统计首要污染物（从已计算的primary_pollutant字段获取）
        # 修复1：支持中文逗号和英文逗号分割（数据中可能使用 "O3_8h，NO2"）
        # 修复2：使用大小写不敏感的统计，避免因 O3_8h vs O3_8H 导致的统计遗漏
        # 修复3：处理 PM2.5（点号）到 PM2_5（下划线）的映射
        primary = record.get("primary_pollutant", "")
        if primary:
            # 同时支持中文逗号（，）和英文逗号（,）分割
            import re
            pollutants = re.split(r'[，,]', primary)
            for p in pollutants:
                p_clean = p.strip()
                if not p_clean:
                    continue
                # 标准化污染物名称（处理大小写和点号/下划线差异）
                dict_key = p_clean

                # 处理 PM2.5 → PM2_5 映射
                if p_clean == 'PM2.5':
                    dict_key = 'PM2_5'
                # 处理 O3_8h 大小写
                elif p_clean.upper() == 'O3_8H':
                    dict_key = 'O3_8h'

                if dict_key in primary_pollutant_days:
                    primary_pollutant_days[dict_key] += 1

        # 统计各污染物超标天数（单项质量指数 > 1）
        if pm25_index_old > 1:
            exceed_days_by_pollutant['PM2_5'] += 1
        if pm10_index_old > 1:
            exceed_days_by_pollutant['PM10'] += 1
        if so2_index_old > 1:
            exceed_days_by_pollutant['SO2'] += 1
        if no2_index_old > 1:
            exceed_days_by_pollutant['NO2'] += 1
        if co_index_old > 1:
            exceed_days_by_pollutant['CO'] += 1
        if o3_8h_index_old > 1:
            exceed_days_by_pollutant['O3_8h'] += 1

        # 旧标准超标天数统计
        if max_single_index_old > 1:
            exceed_days += 1

            # 统计首要污染物超标天（某污染物既是首要污染物又超标）
            # 修复：需要检查首要污染物本身是否超标，而不是只检查当天是否有任何污染物超标
            primary_pollutant_indexes = {
                'PM2_5': pm25_index_old,
                'PM10': pm10_index_old,
                'SO2': so2_index_old,
                'NO2': no2_index_old,
                'CO': co_index_old,
                'O3_8h': o3_8h_index_old
            }

            primary = record.get("primary_pollutant", "")
            if primary:
                # 同时支持中文逗号（，）和英文逗号（,）分割
                import re
                pollutants = re.split(r'[，,]', primary)
                for p in pollutants:
                    p_clean = p.strip()
                    if not p_clean:
                        continue
                    # 标准化污染物名称（处理大小写和点号/下划线差异）
                    dict_key = p_clean

                    # 处理 PM2.5 → PM2_5 映射
                    if p_clean == 'PM2.5':
                        dict_key = 'PM2_5'
                    # 处理 O3_8h 大小写
                    elif p_clean.upper() == 'O3_8H':
                        dict_key = 'O3_8h'

                    if dict_key in primary_pollutant_exceed_days:
                        # 只有当首要污染物本身超标时才计入
                        if primary_pollutant_indexes.get(dict_key, 0) > 1:
                            primary_pollutant_exceed_days[dict_key] += 1

            # 记录超标详情
            exceed_pollutants = []
            pollutants = {
                'PM2_5': (pm25, pm25_index_old), 'PM10': (pm10, pm10_index_old),
                'SO2': (so2, so2_index_old), 'NO2': (no2, no2_index_old),
                'CO': (co, co_index_old), 'O3_8h': (o3_8h, o3_8h_index_old)
            }
            for name, (conc, index) in pollutants.items():
                if index > 1:
                    exceed_pollutants.append({
                        'name': name, 'concentration': conc, 'index': safe_round(index, 3)
                    })
            exceed_detail = {
                'date': record.get("timestamp", "unknown"),
                'max_index': safe_round(max_single_index_old, 3),
                'exceed_pollutants': exceed_pollutants
            }
            exceed_details.append(exceed_detail)

        # 统计有效天数（只要有一项污染物有数据就算有效天）
        if pm25 > 0 or pm10 > 0 or so2 > 0 or no2 > 0 or co > 0 or o3_8h > 0:
            valid_days += 1

    # 计算平均浓度（按国家标准修约）
    avg_pm25 = apply_rounding(pm25_sum / pm25_valid_count if pm25_valid_count > 0 else 0, 'PM2_5', 'statistical_data_old')
    avg_pm10 = apply_rounding(pm10_sum / pm10_valid_count if pm10_valid_count > 0 else 0, 'PM10', 'statistical_data_old')
    avg_so2 = apply_rounding(so2_sum / total_days, 'SO2', 'statistical_data_old') if total_days > 0 else 0
    avg_no2 = apply_rounding(no2_sum / total_days, 'NO2', 'statistical_data_old') if total_days > 0 else 0
    avg_co = apply_rounding(co_sum / total_days, 'CO', 'statistical_data_old') if total_days > 0 else 0
    avg_o3_8h = apply_rounding(o3_8h_sum / total_days, 'O3_8h', 'statistical_data_old') if total_days > 0 else 0

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
    co_percentile_95 = apply_rounding(calculate_percentile(daily_co_values, 95), 'CO', 'statistical_data_old')
    o3_8h_percentile_90 = apply_rounding(calculate_percentile(daily_o3_8h_values, 90), 'O3_8h', 'statistical_data_old')
    so2_percentile_98 = apply_rounding(calculate_percentile(daily_so2_values, 98), 'SO2', 'statistical_data_old')
    no2_percentile_98 = apply_rounding(calculate_percentile(daily_no2_values, 98), 'NO2', 'statistical_data_old')
    pm10_percentile_95 = apply_rounding(calculate_percentile(daily_pm10_values, 95), 'PM10', 'statistical_data_old')
    pm25_percentile_95 = apply_rounding(calculate_percentile(daily_pm25_values, 95), 'PM2_5', 'statistical_data_old')

    # 计算旧标准综合指数
    old_standard_concentrations = {
        'PM2_5': avg_pm25, 'PM10': avg_pm10, 'SO2': avg_so2,
        'NO2': avg_no2, 'CO': co_percentile_95, 'O3_8h': o3_8h_percentile_90
    }

    # 计算旧标准单项质量指数 Ii = Ci / Si
    pm25_index = safe_round(old_standard_concentrations['PM2_5'] / ANNUAL_STANDARD_LIMITS_OLD['PM2_5'], 3)
    pm10_index = safe_round(old_standard_concentrations['PM10'] / ANNUAL_STANDARD_LIMITS_OLD['PM10'], 3)
    so2_index = safe_round(old_standard_concentrations['SO2'] / ANNUAL_STANDARD_LIMITS_OLD['SO2'], 3)
    no2_index = safe_round(old_standard_concentrations['NO2'] / ANNUAL_STANDARD_LIMITS_OLD['NO2'], 3)
    co_index = safe_round(old_standard_concentrations['CO'] / ANNUAL_STANDARD_LIMITS_OLD['CO'], 3)
    o3_8h_index = safe_round(old_standard_concentrations['O3_8h'] / ANNUAL_STANDARD_LIMITS_OLD['O3_8h'], 3)

    # 根据参数选择综合指数算法权重
    # use_new_composite_algorithm=False（默认）: 旧算法（所有权重均为1）
    # use_new_composite_algorithm=True: 新算法（PM2.5权重3，NO2权重2，O3权重2，其他权重1）
    if use_new_composite_algorithm:
        # 新综合指数算法：PM2.5权重3，NO2权重2，O3权重2，其他权重1
        composite_weights = WEIGHTS
    else:
        # 旧综合指数算法（默认）：所有权重均为1
        composite_weights = {
            'PM2_5': 1,
            'PM10': 1,
            'SO2': 1,
            'NO2': 1,
            'CO': 1,
            'O3_8h': 1
        }

    # 计算加权单项质量指数
    pm25_weighted_index = safe_round(pm25_index * composite_weights['PM2_5'], 3)
    pm10_weighted_index = safe_round(pm10_index * composite_weights['PM10'], 3)
    so2_weighted_index = safe_round(so2_index * composite_weights['SO2'], 3)
    no2_weighted_index = safe_round(no2_index * composite_weights['NO2'], 3)
    co_weighted_index = safe_round(co_index * composite_weights['CO'], 3)
    o3_8h_weighted_index = safe_round(o3_8h_index * composite_weights['O3_8h'], 3)

    # 计算综合指数
    avg_composite_index = safe_round(
        pm25_weighted_index + pm10_weighted_index + so2_weighted_index +
        no2_weighted_index + co_weighted_index + o3_8h_weighted_index, 3
    )

    # 计算达标率和超标率（百分比形式，保留1位小数）
    # valid_days 在循环中已经统计（只要有一项污染物有数据就算有效天）
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

    logger.info(
        "old_standard_city_stats_calculated",
        city=city_name,
        composite_index=avg_composite_index,
        exceed_days=exceed_days,
        compliance_rate=compliance_rate,
        sand_deduction_stats={
            "total_days": total_days,
            "pm25_valid_count": pm25_valid_count,
            "pm10_valid_count": pm10_valid_count
        }
    )

    return {
        "composite_index": avg_composite_index,
        "exceed_days": int(exceed_days),
        "exceed_details": exceed_details,
        "valid_days": int(valid_days),
        "exceed_rate": exceed_rate,
        "compliance_rate": compliance_rate,
        "total_days": int(total_days),
        # 六参数统计指标（直接使用 statistical_data_old 修约后的值，不进行二次修约）
        "SO2": avg_so2,
        "SO2_P98": so2_percentile_98,
        "NO2": avg_no2,
        "NO2_P98": no2_percentile_98,
        "PM10": avg_pm10,
        "PM10_P95": pm10_percentile_95,
        "PM2_5": avg_pm25,
        "PM2_5_P95": pm25_percentile_95,
        # CO和O3只展示百分位数
        "CO_P95": co_percentile_95,
        "O3_8h_P90": o3_8h_percentile_90,
        # 加权单项质量指数
        "single_indexes": {
            "SO2": so2_weighted_index, "NO2": no2_weighted_index,
            "PM10": pm10_weighted_index, "CO": co_weighted_index,
            "PM2_5": pm25_weighted_index, "O3_8h": o3_8h_weighted_index
        },
        # 首要污染物统计
        "primary_pollutant_days": {k: int(v) for k, v in primary_pollutant_days.items()},
        "primary_pollutant_ratio": primary_pollutant_ratio,
        "total_primary_days": int(total_primary_days),
        # 各污染物超标统计
        "exceed_days_by_pollutant": {k: int(v) for k, v in exceed_days_by_pollutant.items()},
        "exceed_rate_by_pollutant": exceed_rate_by_pollutant,
        # 首要污染物超标天统计（某污染物既是首要污染物又超标）
        "primary_pollutant_exceed_days": {k: int(v) for k, v in primary_pollutant_exceed_days.items()}
    }
