"""
多站点并发查询辅助模块

提供通用的多站点并发查询功能
"""

import asyncio
from typing import Any, Callable, Dict, List
import structlog

logger = structlog.get_logger()


async def query_multi_stations(
    query_func: Callable,
    station_names: List[str],
    station_codes: List[str],
    **query_params
) -> Dict[str, Any]:
    """
    并发查询多个站点并聚合结果

    Args:
        query_func: 单站点查询函数，签名为 async func(station_name, station_code, **params) -> dict
        station_names: 站点名称列表
        station_codes: 站点编码列表
        **query_params: 查询参数

    Returns:
        {
            "success": True/False,
            "records": [...],  # 聚合的所有站点数据
            "record_count": N,
            "queried_stations": M,
            "successful_stations": [...],  # 成功的站点列表
            "failed_stations": [...]  # 失败的站点列表
        }
    """
    async def query_single(station_name: str, station_code: str) -> Dict[str, Any]:
        """查询单个站点"""
        try:
            result = await query_func(
                station_name=station_name,
                station_code=station_code,
                **query_params
            )

            return {
                "station": station_name,
                "code": station_code,
                "success": result.get("success", False),
                "records": result.get("records", []),
                "record_count": result.get("record_count", 0),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(
                "single_station_query_error",
                station=station_name,
                code=station_code,
                error=str(e),
                exc_info=True
            )
            return {
                "station": station_name,
                "code": station_code,
                "success": False,
                "error": str(e),
                "records": [],
                "record_count": 0
            }

    logger.info(
        "multi_station_query_start",
        stations=station_names,
        codes=station_codes,
        count=len(station_codes)
    )

    # 并发查询所有站点
    tasks = [
        query_single(name, code)
        for name, code in zip(station_names, station_codes)
    ]
    results = await asyncio.gather(*tasks)

    # 聚合结果
    all_records = []
    successful_stations = []
    failed_stations = []

    for result in results:
        if result.get("success"):
            all_records.extend(result.get("records", []))
            successful_stations.append({
                "station": result.get("station"),
                "code": result.get("code"),
                "record_count": result.get("record_count", 0)
            })
        else:
            failed_stations.append({
                "station": result.get("station"),
                "code": result.get("code"),
                "error": result.get("error")
            })

    if not all_records:
        return {
            "success": False,
            "error": f"所有站点查询失败: {len(failed_stations)}个站点",
            "queried_stations": len(station_names),
            "successful_stations": len(successful_stations),
            "failed_stations": failed_stations,
            "records": [],
            "record_count": 0
        }

    logger.info(
        "multi_station_query_complete",
        total_records=len(all_records),
        successful_stations=len(successful_stations),
        failed_stations=len(failed_stations)
    )

    return {
        "success": True,
        "records": all_records,
        "record_count": len(all_records),
        "queried_stations": len(station_names),
        "successful_stations": successful_stations,
        "failed_stations": failed_stations if failed_stations else None
    }
