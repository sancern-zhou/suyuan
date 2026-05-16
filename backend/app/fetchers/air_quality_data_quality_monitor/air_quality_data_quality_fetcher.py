"""
Air Quality Data Quality Fetcher

定时巡检空气质量监测数据质量，识别疑似数据问题。
"""
from __future__ import annotations

from typing import List
from pathlib import Path
from datetime import datetime

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.air_quality_data_quality_monitor import (
    DataQualityMonitorConfig,
    run_air_quality_data_quality_monitor,
)

logger = structlog.get_logger()


class AirQualityDataQualityFetcher(DataFetcher):
    """
    空气质量数据质量巡检抓取器

    功能：
    - 每小时巡检指定城市最近24小时的站点小时监测数据
    - 按同城站点偏差、趋势一致性、PM2.5/PM10协同变化、NO2/O3规律等规则识别疑似数据质量问题
    - 只在发现疑似问题时生成证据包（quality_package.json）
    - 不需要 Agent 参与，后台自动运行

    输出位置：backend_data_registry/data_quality_issues/{city}/
    """

    # 默认配置
    DEFAULT_CITIES = ["广州", "深圳", "佛山", "东莞"]
    DEFAULT_HOURS = 24
    DEFAULT_STATION_TYPE = "国控"
    DEFAULT_OUTPUT_ROOT = None  # 使用默认路径 backend_data_registry/data_quality_issues/

    def __init__(
        self,
        cities: List[str] | None = None,
        hours: int = DEFAULT_HOURS,
        station_type: str = DEFAULT_STATION_TYPE,
        output_root: Path | None = DEFAULT_OUTPUT_ROOT,
    ):
        """
        初始化数据质量巡检抓取器

        Args:
            cities: 监控城市列表，默认为广州、深圳、佛山、东莞
            hours: 回看小时数，默认24小时
            station_type: 站点类型，默认"国控"
            output_root: 输出目录，默认为 backend_data_registry/data_quality_issues/
        """
        super().__init__(
            name="air_quality_data_quality_fetcher",
            description="空气质量数据质量自动巡检，识别疑似数据问题",
            schedule="0 * * * *",  # 每小时整点运行
            version="1.0.0",
        )

        # 配置参数
        self.cities = cities or self.DEFAULT_CITIES
        self.hours = hours
        self.station_type = station_type
        self.output_root = output_root

        logger.info(
            "air_quality_data_quality_fetcher_initialized",
            cities=self.cities,
            hours=self.hours,
            station_type=self.station_type,
        )

    async def fetch_and_store(self):
        """
        执行数据质量巡检

        工作流程：
        1. 获取指定城市最近N小时的站点小时监测数据
        2. 运行数据质量检查规则
        3. 生成问题清单和统计摘要
        4. 如果发现问题，保存证据包到磁盘
        """
        try:
            # 创建配置
            config = DataQualityMonitorConfig(
                cities=self.cities,
                hours=self.hours,
                station_type=self.station_type,
                output_root=self.output_root,
                end_time=datetime.now(),
                session_id=f"fetcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )

            # 运行巡检
            result = await run_air_quality_data_quality_monitor(
                config=config,
                context=None,  # Fetcher 不需要 ExecutionContext
            )

            # 记录结果
            issue_count = result.get("issue_count", 0)
            package_count = len(result.get("issue_packages", []))

            logger.info(
                "air_quality_data_quality_fetcher_completed",
                cities=self.cities,
                hours=self.hours,
                issue_count=issue_count,
                package_count=package_count,
                output_root=result.get("output_root"),
                summary=result.get("summary"),
            )

            return result

        except Exception as e:
            logger.error(
                "air_quality_data_quality_fetcher_failed",
                cities=self.cities,
                error=str(e),
                exc_info=True,
            )
            raise
