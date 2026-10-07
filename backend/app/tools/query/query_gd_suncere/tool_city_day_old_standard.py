"""
广东省城市日数据查询工具（旧标准：十三五/十四五）

查询广东省城市日空气质量数据，支持十三五和十四五两种标准。
"""
from typing import Dict, Any, List, Optional
import structlog

from app.services.gd_suncere_api_client import get_gd_suncere_api_client
from app.agent.context.execution_context import ExecutionContext
from app.utils.data_standardizer import get_data_standardizer
from app.tools.query.query_gd_suncere.tool import (
    QueryGDSuncereDataTool,
    GeoMappingResolver,
    apply_rounding
)


logger = structlog.get_logger()


async def execute_query_city_day_old_standard(
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    plan_type: int = 0,
    time_type: int = 8,
    area_type: int = 2,
    pollutant_codes: Optional[List[str]] = None,
    data_source: int = 1
) -> Dict[str, Any]:
    """
    查询城市日数据（旧标准：十三五/十四五）

    Args:
        cities: 城市名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        context: 执行上下文
        plan_type: 规划类型（0=十四五, 135=十三五）
        time_type: 时间类型（8=任意时间, 3=周报, 4=月报, 5=季报, 7=年报）
        area_type: 区域类型（2=城市, 1=区县, 0=站点）
        pollutant_codes: 污染物代码列表（如 ["so2", "no2", "pm2.5"]）
        data_source: 数据源类型（1=审核实况, 0=原始实况）

    Returns:
        UDF v2.0 标准格式结果
    """
    api_client = get_gd_suncere_api_client()
    standardizer = get_data_standardizer()
    geo_resolver = GeoMappingResolver()

    # 1. 城市名称 -> 编码转换
    city_codes = geo_resolver.resolve_city_codes(cities)
    if not city_codes:
        raise ValueError(f"无法识别城市名称: {cities}")

    # 2. 时间格式转换
    start_time = f"{start_date} 00:00:00"
    end_time = f"{end_date} 23:59:59"

    logger.info(
        "query_city_day_old_standard_start",
        cities=cities,
        city_codes=city_codes,
        start_date=start_date,
        end_date=end_date,
        plan_type=plan_type,
        time_type=time_type,
        data_source=data_source
    )

    try:
        # 3. 调用 API（带自动分页）
        all_records = []
        skip_count = 0
        max_result_count = 40

        while True:
            response = api_client.query_city_day_old_standard(
                city_codes=city_codes,
                start_time=start_time,
                end_time=end_time,
                plan_type=plan_type,
                time_type=time_type,
                area_type=area_type,
                pollutant_codes=pollutant_codes,
                data_source=data_source,
                skip_count=skip_count,
                max_result_count=max_result_count
            )

            if not response.get("success"):
                error_msg = response.get("msg", "Unknown error")
                raise Exception(f"API 查询失败: {error_msg}")

            # 解析响应（路径：result.items 或 result）
            result = response.get("result", {})
            items = result.get("items", []) if isinstance(result, dict) else result

            if not items:
                break

            all_records.extend(items)

            # 检查是否需要继续分页
            total_count = result.get("totalCount", len(items))
            if len(all_records) >= total_count:
                break

            skip_count += max_result_count

        if not all_records:
            logger.warning(
                "query_city_day_old_standard_no_data",
                cities=cities,
                date_range=f"{start_date} to {end_date}"
            )
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": {
                    "tool_name": "query_gd_suncere_city_day_old_standard",
                    "cities": cities,
                    "date_range": f"{start_date} to {end_date}",
                    "plan_type": "十三五" if plan_type == 135 else "十四五",
                    "message": "查询成功但无数据返回"
                },
                "summary": f"未找到 {', '.join(cities)} 在指定时间段的旧标准日报数据"
            }

        logger.info(
            "query_city_day_old_standard_data_received",
            record_count=len(all_records)
        )

        # 4. 数据标准化
        standardized_records = []
        for record in all_records:
            # 字段映射
            standardized = standardizer.standardize([record], schema="air_quality_unified")
            if standardized:
                standardized_records.extend(standardized)

        # 5. 应用修约规则（日数据保留整数）
        for record in standardized_records:
            measurements = record.get("measurements", {})
            for pollutant in ["PM2_5", "PM10", "SO2", "NO2", "O3", "CO"]:
                if pollutant in measurements:
                    raw_value = measurements[pollutant]
                    rounded = apply_rounding(raw_value, pollutant, 'raw_data')
                    # 日数据保留整数（CO 除外保留1位小数）
                    if pollutant == "CO":
                        measurements[pollutant] = round(float(rounded), 1)
                    else:
                        measurements[pollutant] = int(rounded)

        logger.info(
            "query_city_day_old_standard_data_standardized",
            raw_count=len(all_records),
            standardized_count=len(standardized_records)
        )

        # 6. 保存到上下文
        data_id = context.data_manager.save_data(
            data=standardized_records,
            schema="air_quality_unified",
            metadata={
                "source": "gd_suncere_old_standard",
                "plan_type": "十三五" if plan_type == 135 else "十四五",
                "schema_version": "v2.0"
            }
        )

        logger.info(
            "query_city_day_old_standard_data_saved",
            data_id=data_id,
            record_count=len(standardized_records)
        )

        # 7. 构造 UDF v2.0 响应
        preview_data = standardized_records[:24]  # 前24条预览

        return {
            "status": "success",
            "success": True,
            "data": preview_data,
            "metadata": {
                "tool_name": "query_gd_suncere_city_day_old_standard",
                "data_id": data_id,
                "total_records": len(standardized_records),
                "returned_records": len(preview_data),
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "plan_type": "十三五" if plan_type == 135 else "十四五",
                "schema_version": "v2.0",
                "source": "gd_suncere_old_standard"
            },
            "summary": f"成功获取 {', '.join(cities)} 的日数据（{'十三五' if plan_type == 135 else '十四五'}标准）共 {len(standardized_records)} 条，已保存为 {data_id}"
        }

    except Exception as e:
        logger.error(
            "query_city_day_old_standard_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return {
            "status": "failed",
            "success": False,
            "error": str(e),
            "data": None,
            "metadata": {
                "tool_name": "query_gd_suncere_city_day_old_standard",
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "plan_type": "十三五" if plan_type == 135 else "十四五"
            },
            "summary": f"旧标准城市日数据查询失败: {str(e)}"
        }
