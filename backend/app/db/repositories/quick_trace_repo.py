"""
快速溯源分析数据仓库

Quick Trace Analysis Repository for database operations.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import structlog

from app.db.database import async_session
from app.db.models.quick_trace_models import QuickTraceAnalysis

logger = structlog.get_logger()


class QuickTraceRepository:
    """快速溯源分析数据仓库"""

    async def save_analysis(
        self,
        analysis_date: str,
        alert_time: str,
        pollutant: str,
        alert_value: float,
        unit: Optional[str] = None,
        summary_text: Optional[str] = None,
        visuals: Optional[list] = None,
        execution_time_seconds: Optional[float] = None,
        has_trajectory: Optional[bool] = None,
        warning_message: Optional[str] = None,
    ) -> int:
        """
        保存快速溯源分析结果到数据库

        Args:
            analysis_date: 分析日期 (YYYY-MM-DD)
            alert_time: 告警时间 (YYYY-MM-DD HH:MM:SS)
            pollutant: 污染物类型
            alert_value: 告警浓度值
            unit: 浓度单位（可选）
            summary_text: 分析报告（可选）
            visuals: 可视化图表列表（可选）
            execution_time_seconds: 执行耗时（可选）
            has_trajectory: 是否包含轨迹分析（可选）
            warning_message: 警告信息（可选）

        Returns:
            int: 插入记录的ID
        """
        try:
            # 解析日期和时间
            analysis_date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()
            alert_time_obj = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")

            # 构建记录（visuals 直接传递为 Python 对象，SQLAlchemy 会自动处理 JSONB）
            record = {
                "analysis_date": analysis_date_obj,
                "alert_time": alert_time_obj,
                "pollutant": pollutant,
                "alert_value": alert_value,
                "unit": unit,
                "summary_text": summary_text,
                "visuals": visuals,  # 直接传递 Python 对象（list/dict），不转换为 JSON 字符串
                "execution_time_seconds": execution_time_seconds,
                "has_trajectory": has_trajectory,
                "warning_message": warning_message,
            }

            async with async_session() as session:
                stmt = insert(QuickTraceAnalysis).values(record)
                stmt = stmt.on_conflict_do_nothing()  # 如果已存在则不插入

                result = await session.execute(stmt)
                await session.commit()

                # 获取插入的ID
                inserted_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

                logger.info(
                    "quick_trace_analysis_saved",
                    analysis_date=analysis_date,
                    pollutant=pollutant,
                    alert_value=alert_value,
                    inserted_id=inserted_id,
                )

                return inserted_id

        except Exception as e:
            logger.error(
                "quick_trace_analysis_save_failed",
                analysis_date=analysis_date,
                pollutant=pollutant,
                error=str(e),
                exc_info=True
            )
            raise

    async def get_analysis_by_date(
        self,
        analysis_date: str,
        pollutant: Optional[str] = None,
    ) -> Optional[QuickTraceAnalysis]:
        """
        根据分析日期查询分析结果

        Args:
            analysis_date: 分析日期 (YYYY-MM-DD)
            pollutant: 污染物类型（可选）

        Returns:
            QuickTraceAnalysis: 分析结果对象，如果不存在则返回None
        """
        try:
            analysis_date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()

            async with async_session() as session:
                query = select(QuickTraceAnalysis).where(
                    QuickTraceAnalysis.analysis_date == analysis_date_obj
                )

                if pollutant:
                    query = query.where(QuickTraceAnalysis.pollutant == pollutant)

                query = query.order_by(QuickTraceAnalysis.created_at.desc())

                result = await session.execute(query)
                return result.scalars().first()

        except Exception as e:
            logger.error(
                "get_analysis_by_date_failed",
                analysis_date=analysis_date,
                pollutant=pollutant,
                error=str(e)
            )
            return None

    async def get_recent_analyses(
        self,
        limit: int = 10,
        pollutant: Optional[str] = None,
    ) -> list:
        """
        获取最近的分析结果

        Args:
            limit: 返回记录数
            pollutant: 污染物类型（可选）

        Returns:
            list: 分析结果列表
        """
        try:
            async with async_session() as session:
                query = select(QuickTraceAnalysis)

                if pollutant:
                    query = query.where(QuickTraceAnalysis.pollutant == pollutant)

                query = query.order_by(QuickTraceAnalysis.alert_time.desc()).limit(limit)

                result = await session.execute(query)
                return result.scalars().all()

        except Exception as e:
            logger.error(
                "get_recent_analyses_failed",
                limit=limit,
                pollutant=pollutant,
                error=str(e)
            )
            return []
