"""
快速溯源API路由 (Quick Trace API Routes)

提供污染高值告警快速溯源的HTTP接口
"""

from fastapi import APIRouter, HTTPException
from app.schemas.alert import AlertRequest, AlertResponse, HealthResponse
from app.agent.executors.quick_trace_executor import QuickTraceExecutor
import structlog
import time

logger = structlog.get_logger()

# 创建路由器
router = APIRouter()

# 初始化执行器
executor = QuickTraceExecutor()


@router.post(
    "/api/quick-trace/alert",
    response_model=AlertResponse,
    summary="污染高值告警快速溯源",
    description="""
    触发污染高值告警快速溯源分析

    功能:
    1. 自动获取济宁+周边城市的空气质量数据 (前72小时)
    2. 获取当天实时气象数据+历史气象数据(前3天)
    3. 获取未来15天天气预报
    4. 执行后向轨迹分析(72小时, 可跳过)
    5. 生成Markdown格式总结报告

    执行时间: 2-3分钟 (轨迹分析超时则8-15秒)

    参数:
    - city: 城市名称 (如 "济宁市")
    - alert_time: 告警时间 (如 "2026-02-02 12:00:00")
    - pollutant: 告警污染物 (如 "PM2.5")
    - alert_value: 告警浓度值 (如 180.5)

    返回:
    - summary_text: Markdown格式的综合分析报告
    - visuals: 可视化图表列表
    - confidence: 分析置信度
    - execution_time_seconds: 执行耗时
    """
)
async def trigger_pollution_alert_analysis(request: AlertRequest):
    """
    污染高值告警快速溯源API
    """
    start_time = time.time()

    logger.info(
        "quick_trace_alert_started",
        city=request.city,
        alert_time=request.alert_time,
        pollutant=request.pollutant,
        alert_value=request.alert_value
    )

    try:
        # 执行快速溯源分析
        result = await executor.execute(
            city=request.city,
            alert_time=request.alert_time,
            pollutant=request.pollutant,
            alert_value=request.alert_value
        )

        # 计算执行时间
        execution_time = time.time() - start_time

        # 构建响应 (round后可能变成0.0，需要确保>0)
        rounded_time = round(execution_time, 2)
        if rounded_time <= 0:
            rounded_time = 0.01  # 最小10毫秒

        # 保存到数据库
        db_id = None
        if result.get("summary_text"):
            try:
                save_result = await executor.save_report(
                    summary_text=result["summary_text"],
                    city=request.city,
                    alert_time=request.alert_time,
                    pollutant=request.pollutant,
                    alert_value=request.alert_value,
                    visuals=result.get("visuals", []),
                    execution_time_seconds=rounded_time,
                    has_trajectory=result.get("has_trajectory", False),
                    warning_message=result.get("warning_message"),
                )
                db_id = save_result.get("db_id")
            except Exception as save_error:
                logger.warning(
                    "quick_trace_database_save_failed",
                    error=str(save_error)
                )
                # 数据库保存失败不影响API响应

        response = AlertResponse(
            summary_text=result["summary_text"],
            visuals=result.get("visuals", []),
            execution_time_seconds=rounded_time,
            data_ids=[],  # 快速溯源不需要data_ids
            has_trajectory=result.get("has_trajectory", False),
            warning_message=result.get("warning_message"),
            city=request.city,
            alert_time=request.alert_time,
            pollutant=request.pollutant,
            alert_value=request.alert_value
        )

        logger.info(
            "quick_trace_alert_completed",
            city=request.city,
            execution_time=execution_time,
            has_trajectory=response.has_trajectory,
            db_id=db_id
        )

        return response

    except Exception as e:
        logger.error(
            "quick_trace_alert_failed",
            city=request.city,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"快速溯源分析失败: {str(e)}"
        )


@router.get(
    "/api/quick-trace/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="检查快速溯源服务状态"
)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        service="quick_trace_alert",
        version="1.0.0",
        supported_cities=list(executor.CITY_COORDINATES.keys())
    )


@router.get(
    "/api/quick-trace/supported-cities",
    summary="获取支持的城市列表",
    description="返回当前支持分析的城市列表"
)
async def get_supported_cities():
    """获取支持的城市列表"""
    return {
        "service": "quick_trace_alert",
        "supported_cities": list(executor.CITY_COORDINATES.keys()),
        "city_coordinates": executor.CITY_COORDINATES,
        "nearby_cities": {
            city: executor.NEARBY_CITIES
            for city in executor.CITY_COORDINATES.keys()
        }
    }
